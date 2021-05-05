from collections import defaultdict
from datetime import datetime
from typing import Callable, Dict, Iterable, Optional
from uuid import UUID

import structlog
from eth_utils import to_checksum_address, to_normalized_address
from gevent.event import Event
from matrix_client.errors import MatrixRequestError
from matrix_client.user import User
from structlog._config import BoundLoggerLazyProxy

from raiden.api.v1.encoding import CapabilitiesSchema
from raiden.network.transport.matrix.client import GMatrixClient, node_address_from_userid
from raiden.network.transport.matrix.utils import (
    UNKNOWN_REACHABILITY_STATE,
    USER_PRESENCE_TO_ADDRESS_REACHABILITY,
    AddressReachability,
    DisplayNameCache,
    ReachabilityState,
    UserPresence,
    address_from_userid,
    validate_userid_signature,
)
from raiden.utils.typing import Address, Any, FrozenSet, Set, Union

log = structlog.get_logger(__name__)


class UserAddressManager:
    """Matrix user <-> eth address mapping and user / address reachability helper.

    In Raiden the smallest unit of addressability is a node with an associated Ethereum address.
    In Matrix it's a user. Matrix users are (at the moment) bound to a specific homeserver.
    Since we want to provide resiliency against unavailable homeservers a single Raiden node with
    a single Ethereum address can be in control over multiple Matrix users on multiple homeservers.

    Therefore we need to perform a many-to-one mapping of Matrix users to Ethereum addresses.
    Each Matrix user has a presence state (ONLINE, OFFLINE).
    One of the preconditions of running a Raiden node is that there can always only be one node
    online for a particular address at a time.
    That means we can synthesize the reachability of an address from the user presence states.

    This helper internally tracks both the user presence and address reachability for addresses
    that have been marked as being 'interesting' (by calling the `.add_address()` method).
    Additionally it provides the option of passing callbacks that will be notified when
    presence / reachability change.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(
        self,
        client: GMatrixClient,
        displayname_cache: DisplayNameCache,
        address_reachability_changed_callback: Callable[[Address, AddressReachability], None],
        user_presence_changed_callback: Optional[Callable[[User, UserPresence], None]] = None,
        _log_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._client = client
        self._displayname_cache = displayname_cache
        self._address_reachability_changed_callback = address_reachability_changed_callback
        self._user_presence_changed_callback = user_presence_changed_callback
        self._stop_event = Event()

        self._reset_state()

        self._log_context = _log_context
        self._log = None
        self._listener_id: Optional[UUID] = None
        self._capabilities_schema = CapabilitiesSchema()

    def start(self) -> None:
        """Start listening for presence updates.

        Should be called before ``.login()`` is called on the underlying client."""
        assert self._listener_id is None, "UserAddressManager.start() called twice"
        self._stop_event.clear()
        self._listener_id = self._client.add_presence_listener(self._presence_listener)

    def stop(self) -> None:
        """Stop listening on presence updates."""
        assert self._listener_id is not None, "UserAddressManager.stop() called before start"
        self._stop_event.set()
        self._client.remove_presence_listener(self._listener_id)
        self._listener_id = None
        self._log = None
        self._reset_state()

    @property
    def known_addresses(self) -> Set[Address]:
        """Return all addresses we keep track of"""
        # This must return a copy of the current keys, because the container
        # may be modified while these values are used. Issue: #5240
        return set(self._address_to_userids)

    def is_address_known(self, address: Address) -> bool:
        """Is the given ``address`` reachability being monitored?"""
        return address in self._address_to_userids

    def add_address(self, address: Address) -> None:
        """Add ``address`` to the known addresses that are being observed for reachability."""
        # Since _address_to_userids is a defaultdict accessing the key creates the entry
        _ = self._address_to_userids[address]

    def add_userid_for_address(self, address: Address, user_id: str) -> None:
        """Add a ``user_id`` for the given ``address``.

        Implicitly adds the address if it was unknown before.
        """
        self._address_to_userids[address].add(user_id)

    def add_userids_for_address(self, address: Address, user_ids: Iterable[str]) -> None:
        """Add multiple ``user_ids`` for the given ``address``.

        Implicitly adds any addresses if they were unknown before.
        """
        self._address_to_userids[address].update(user_ids)

    def get_userids_for_address(self, address: Address) -> Set[str]:
        """Return all known user ids for the given ``address``."""
        if not self.is_address_known(address):
            return set()
        return self._address_to_userids[address]

    def get_userid_presence(self, user_id: str) -> UserPresence:
        """Return the current presence state of ``user_id``."""
        return self._userid_to_presence.get(user_id, UserPresence.UNKNOWN)

    def get_address_reachability(self, address: Address) -> AddressReachability:
        """Return the current reachability state for ``address``."""
        return self._address_to_reachabilitystate.get(
            address, UNKNOWN_REACHABILITY_STATE
        ).reachability

    def get_address_reachability_state(self, address: Address) -> ReachabilityState:
        """Return the current reachability state for ``address``."""
        return self._address_to_reachabilitystate.get(address, UNKNOWN_REACHABILITY_STATE)

    def get_address_capabilities(self, address: Address) -> str:
        """Return the protocol capabilities for ``address``."""
        return self._address_to_capabilities.get(address, "mxc://")

    def force_user_presence(self, user: User, presence: UserPresence) -> None:
        """Forcibly set the ``user`` presence to ``presence``.

        This method is only provided to cover an edge case in our use of the Matrix protocol and
        should **not** generally be used.
        """
        self._userid_to_presence[user.user_id] = presence

    def populate_userids_for_address(self, address: Address, force: bool = False) -> None:
        """Populate known user ids for the given ``address`` from the server directory.

        If ``force`` is ``True`` perform the directory search even if there
        already are known users.
        """
        if force or not self.get_userids_for_address(address):
            self.add_userids_for_address(
                address,
                (
                    user.user_id
                    for user in self._client.search_user_directory(to_normalized_address(address))
                    if self._validate_userid_signature(user)
                ),
            )

    def track_address_presence(
        self, address: Address, user_ids: Optional[Union[Set[str], FrozenSet[str]]] = None
    ) -> None:
        """
        Update synthesized address presence state.

        Triggers callback (if any) in case the state has changed.
        """
        # Is this address already tracked for all given user_ids?
        if user_ids is None:
            user_ids = frozenset()
        state_known = (
            self.get_address_reachability_state(address).reachability
            != AddressReachability.UNKNOWN
        )
        no_new_user_ids = user_ids.issubset(self._address_to_userids[address])
        if state_known and no_new_user_ids:
            return

        # Update presence
        self.add_userids_for_address(address, user_ids)
        userids_to_presence = {}
        for uid in user_ids:
            presence = self._fetch_user_presence(uid)
            userids_to_presence[uid] = presence
            # We assume that this is only used when no presence has been set,
            # yet. So let's use a presence_update_id that's smaller than the
            # usual ones, which start at 0.
            self._set_user_presence(uid, presence, presence_update_id=-1)

        log.debug(
            "Fetched user presences",
            address=to_checksum_address(address),
            userids_to_presence=userids_to_presence,
        )

        self._maybe_address_reachability_changed(address)

    def query_capabilities_for_user_id(self, user_id: str) -> str:
        """This pulls the `avatar_url` for a given user/user_id and parses the capabilities."""
        try:
            avatar_url = self._client.api.get_avatar_url(user_id)
            if avatar_url is not None:
                return avatar_url
        except MatrixRequestError:
            log.debug("Could not fetch capabilities", user_id=user_id)
        return self._capabilities_schema.load({})["capabilities"]

    def get_reachability_from_matrix(self, user_ids: Iterable[str]) -> AddressReachability:
        """Get the current reachability without any side effects

        Since his does not even do any caching, don't use it for the normal
        communication between participants in a channel.
        """
        for uid in user_ids:
            presence = self._fetch_user_presence(uid)
            if USER_PRESENCE_TO_ADDRESS_REACHABILITY[presence] == AddressReachability.REACHABLE:
                return AddressReachability.REACHABLE

        return AddressReachability.UNREACHABLE

    def _maybe_address_reachability_changed(self, address: Address) -> None:
        # A Raiden node may have multiple Matrix users, this happens when
        # Raiden roams from a Matrix server to another. This loop goes over all
        # these users and uses the "best" presence. IOW, if there is at least one
        # Matrix user that is reachable, then the Raiden node is considered
        # reachable.
        userids = self._address_to_userids[address].copy()
        presence_to_uid = defaultdict(list)
        for uid in userids:
            presence_to_uid[self._userid_to_presence.get(uid)].append(uid)
        composite_presence = set(presence_to_uid.keys())

        new_presence = UserPresence.UNKNOWN
        for presence in UserPresence.__members__.values():
            if presence in composite_presence:
                new_presence = presence
                break

        new_address_reachability = USER_PRESENCE_TO_ADDRESS_REACHABILITY[new_presence]

        prev_reachability_state = self.get_address_reachability_state(address)
        if new_address_reachability == prev_reachability_state.reachability:
            return
        # for capabilities, we get the "first" uid that showed the `new_presence`
        present_uid = presence_to_uid[new_presence].pop()
        capabilities = self.query_capabilities_for_user_id(present_uid)
        now = datetime.now()

        self.log.debug(
            "Changing address reachability state",
            address=to_checksum_address(address),
            prev_state=prev_reachability_state.reachability,
            state=new_address_reachability,
            last_change=prev_reachability_state.time,
            change_after=now - prev_reachability_state.time,
        )

        self._address_to_reachabilitystate[address] = ReachabilityState(
            new_address_reachability, now
        )
        self._address_to_capabilities[address] = capabilities
        self._address_reachability_changed_callback(address, new_address_reachability)

    def _presence_listener(self, event: Dict[str, Any], presence_update_id: int) -> None:
        """
        Update cached user presence state from Matrix presence events.

        Due to the possibility of nodes using accounts on multiple homeservers a composite
        address state is synthesised from the cached individual user presence states.
        """
        if self._stop_event.ready():
            return

        user_id = event["sender"]

        if event["type"] != "m.presence" or user_id == self._user_id:
            return

        address = address_from_userid(user_id)

        # Not a user we've whitelisted, skip. This needs to be on the top of
        # the function so that we don't request they displayname of users that
        # are not important for the node. The presence is updated for every
        # user on the first sync, since every Raiden node is a member of a
        # broadcast room. This can result in thousands requests to the Matrix
        # server in the first sync which will lead to slow startup times and
        # presence problems.
        if address is None or not self.is_address_known(address):
            return

        user = self._user_from_id(user_id, event["content"].get("displayname"))

        if not user:
            return

        self._displayname_cache.warm_users([user])
        # If for any reason we cannot resolve the displayname, then there was a server error.
        # Any properly logged in user that joined a room, will have a displayname.
        # A reason for not resolving it could be rate limiting by the other server.
        if user.displayname is None:
            new_state = UserPresence.SERVER_ERROR
            self._set_user_presence(user_id, new_state, presence_update_id)
            return

        address = self._validate_userid_signature(user)
        if not address:
            return

        self.add_userid_for_address(address, user_id)

        new_state = UserPresence(event["content"]["presence"])

        self._set_user_presence(user_id, new_state, presence_update_id)
        self._maybe_address_reachability_changed(address)

    def _reset_state(self) -> None:
        self._address_to_userids: Dict[Address, Set[str]] = defaultdict(set)
        self._address_to_reachabilitystate: Dict[Address, ReachabilityState] = dict()
        self._address_to_capabilities: Dict[Address, str] = dict()
        self._userid_to_presence: Dict[str, UserPresence] = dict()
        self._userid_to_presence_update_id: Dict[str, int] = dict()

    @property
    def _user_id(self) -> str:
        user_id = getattr(self._client, "user_id", None)
        assert user_id, f"{self.__class__.__name__}._user_id accessed before client login"
        return user_id

    def _user_from_id(self, user_id: str, display_name: Optional[str] = None) -> Optional[User]:
        try:
            return User(self._client.api, user_id, display_name)
        except ValueError:
            log.error("Matrix server returned an invalid user_id.")
        return None

    def _fetch_user_presence(self, user_id: str) -> UserPresence:
        try:
            presence = UserPresence(self._client.get_user_presence(user_id))
        except MatrixRequestError:
            # The following exception will be raised if the local user and the
            # target user do not have a shared room:
            #
            #   MatrixRequestError: 403:
            #   {"errcode":"M_FORBIDDEN","error":"You are not allowed to see their presence."}
            presence = UserPresence.UNKNOWN
            log.exception("Could not fetch user presence")

        return presence

    def _set_user_presence(
        self, user_id: str, presence: UserPresence, presence_update_id: int
    ) -> None:
        user = self._user_from_id(user_id)
        if not user:
            return

        # -1 is used in track_address_presence, so we use -2 as a default.
        if self._userid_to_presence_update_id.get(user_id, -2) >= presence_update_id:
            # We've already received a more recent presence (or the same one)
            return

        old_presence = self._userid_to_presence.get(user_id)
        if old_presence == presence:
            # This can happen when force_user_presence is used. For most other
            # cased the presence_update_id check will return first.
            return

        self._userid_to_presence[user_id] = presence
        self._userid_to_presence_update_id[user_id] = presence_update_id
        self.log.debug(
            "Changing user presence state",
            user_id=user_id,
            prev_state=old_presence,
            state=presence,
        )
        if self._user_presence_changed_callback:
            self._displayname_cache.warm_users([user])
            self._user_presence_changed_callback(user, presence)

    @staticmethod
    def _validate_userid_signature(user: User) -> Optional[Address]:
        return validate_userid_signature(user)

    @property
    def log(self) -> BoundLoggerLazyProxy:
        if self._log:
            return self._log  # type: ignore

        context = self._log_context or {}

        # Only cache the logger once the user_id becomes available
        if hasattr(self._client, "user_id"):
            context["current_user"] = self._user_id
            context["node"] = node_address_from_userid(self._user_id)

            bound_log = log.bind(**context)
            self._log = bound_log
            return bound_log

        # Apply  the `_log_context` even if the user_id is not yet available
        return log.bind(**context)
