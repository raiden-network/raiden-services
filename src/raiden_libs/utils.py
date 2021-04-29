from urllib.parse import urlparse
from uuid import UUID

from coincurve import PrivateKey, PublicKey
from eth_utils import keccak

from raiden.network.transport.matrix import AddressReachability, UserPresence
from raiden.network.transport.matrix.client import GMatrixClient
from raiden.network.transport.matrix.utils import DisplayNameCache, address_from_userid
from raiden.utils.typing import Address, Any, Callable, Dict, Optional
from raiden_contracts.utils.type_aliases import PrivateKey as PrivateKeyType
from raiden_libs.user_address import UserAddressManager


def camel_to_snake(input_str: str) -> str:
    return "".join(["_" + c.lower() if c.isupper() else c for c in input_str]).lstrip("_")


def public_key_to_address(public_key: PublicKey) -> Address:
    """Converts a public key to an Ethereum address."""
    key_bytes = public_key.format(compressed=False)
    return Address(keccak(key_bytes[1:])[-20:])


def private_key_to_address(private_key: PrivateKeyType) -> Address:
    """Converts a private key to an Ethereum address."""
    privkey = PrivateKey(private_key)
    return public_key_to_address(privkey.public_key)


def noop_reachability(  # pylint: disable=unused-argument
    address: Address, reachability: AddressReachability
) -> None:
    """A reachability callback is required by the UserAddressManager."""


class MultiClientUserAddressManager(UserAddressManager):
    def __init__(
        self,
        client: GMatrixClient,
        displayname_cache: DisplayNameCache,
        _log_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(client, displayname_cache, noop_reachability, _log_context=_log_context)
        self.server_url_to_listener_id: Dict[str, UUID] = {}

    def start(self) -> None:
        """Start listening for presence updates.

        Should be called before ``.login()`` is called on the underlying client."""
        assert self._listener_id is None, "UserAddressManager.start() called twice"  # type: ignore
        self._stop_event.clear()
        self._listener_id = self.add_client(self._client)

    def add_client(self, client: GMatrixClient) -> UUID:
        server_url = client.api.base_url
        self.server_url_to_listener_id[server_url] = client.add_presence_listener(
            self._create_presence_listener(server_url)
        )
        return self.server_url_to_listener_id[server_url]

    def remove_client(self, client: GMatrixClient) -> None:
        listener_id = self.server_url_to_listener_id.pop(client.api.base_url, None)
        if listener_id is not None:
            client.remove_presence_listener(listener_id)

    def stop(self) -> None:
        self.server_url_to_listener_id = {}
        super().stop()

    def _create_presence_listener(
        self, client_server_url: str
    ) -> Callable[[Dict[str, Any], int], None]:
        def _filter_presence(event: Dict[str, Any], presence_update_id: int) -> None:
            """
            The actual presence listener callback. Filters out all presences from own server.
            Drops presences from other servers. If the client is the "main client",
            also call presence listener on presences of users of homeservers where no client
            exists. This is a fallback if the client could not connect to another server
            """
            sender_server = event["sender"].split(":")[-1]
            receiver_server = urlparse(client_server_url).netloc
            main_client_server = urlparse(self._client.api.base_url).netloc
            other_clients_servers = {
                urlparse(server_url).netloc
                for server_url in self.server_url_to_listener_id
                if server_url != self._client.api.base_url
            }

            # if this comes from the main client's sync consume all presences of users
            # which do not have a client in other clients. If other client for user's
            # homeserver exists, presence will be consumed by other client's sync
            if receiver_server == main_client_server:
                if sender_server not in other_clients_servers:
                    self._presence_listener(event, presence_update_id)

            elif sender_server == receiver_server:
                self._presence_listener(event, presence_update_id)

        return _filter_presence

    def _presence_listener(self, event: Dict[str, Any], presence_update_id: int) -> None:
        """
        Update cached user presence state from Matrix presence events.

        Due to the possibility of nodes using accounts on multiple homeservers a composite
        address state is synthesised from the cached individual user presence states.

        This is a copy from the super class with a slight change.
        Any user will automatically be added to the whitelist whenever the PFS receives
        a presence update. We do this since we can assume that the PFS needs to know
        about all raiden users.
        """
        if self._stop_event.ready():
            return

        user_id = event["sender"]

        if event["type"] != "m.presence" or user_id == self._user_id:
            return

        address = address_from_userid(user_id)

        # not a user authenticated by EthAuthProvider
        if address is None:
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
