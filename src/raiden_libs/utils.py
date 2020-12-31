from urllib.parse import urlparse
from uuid import UUID

from coincurve import PrivateKey, PublicKey
from eth_utils import keccak

from raiden.network.transport.matrix import AddressReachability
from raiden.network.transport.matrix.client import GMatrixClient
from raiden.network.transport.matrix.utils import DisplayNameCache, UserAddressManager
from raiden.utils.typing import Address, Any, Callable, Dict, Optional
from raiden_contracts.utils.type_aliases import PrivateKey as PrivateKeyType


def camel_to_snake(input_str: str) -> str:
    return "".join(["_" + c.lower() if c.isupper() else c for c in input_str]).lstrip("_")


def public_key_to_address(public_key: PublicKey) -> Address:
    """ Converts a public key to an Ethereum address. """
    key_bytes = public_key.format(compressed=False)
    return Address(keccak(key_bytes[1:])[-20:])


def private_key_to_address(private_key: PrivateKeyType) -> Address:
    """ Converts a private key to an Ethereum address. """
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
        server_url_to_other_clients: Dict[str, GMatrixClient],
        displayname_cache: DisplayNameCache,
        _log_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(client, displayname_cache, noop_reachability, _log_context=_log_context)

        # additional listener ids without the one from the main client
        self.server_url_to_other_clients = server_url_to_other_clients
        self._other_client_to_listener_id: Dict[GMatrixClient, Optional[UUID]] = {
            client: None for client in self.server_url_to_other_clients.values()
        }

    @property
    def server_url_to_all_clients(self) -> Dict[str, GMatrixClient]:
        return {**self.server_url_to_other_clients, self._client.api.base_url: self._client}

    def start(self) -> None:
        """Start listening for presence updates.

        Should be called before ``.login()`` is called on the underlying client."""
        assert self._listener_id is None, "UserAddressManager.start() called twice"
        self._stop_event.clear()
        self._listener_id = self._client.add_presence_listener(
            self._create_presence_listener(self._client)
        )

        for client in self.server_url_to_other_clients.values():
            self._other_client_to_listener_id[client] = self._client.add_presence_listener(
                self._create_presence_listener(client)
            )

    def stop(self) -> None:
        for client, listener_id in self._other_client_to_listener_id.items():
            client.remove_presence_listener(listener_id)
        super().stop()

    def _create_presence_listener(
        self, client: GMatrixClient
    ) -> Callable[[Dict[str, Any], int], None]:
        def _filter_presence(event: Dict[str, Any], presence_update_id: int) -> None:
            """
            The actual presence listener callback. Filters out all presences from own server.
            Drops presences from other servers. If the client is the "main client",
            also call presence listener on presences of users of homeservers where no client
            exists. This is a fallback if the client could not connect to another server
            """
            sender_server = event["sender"].split(":")[-1]

            other_clients_servers = {
                urlparse(server_url).netloc
                for server_url in self.server_url_to_other_clients.keys()
            }

            # if this comes from the main client's sync consume all presences of users
            # which do not have a client in other clients. If other client for user's
            # homeserver exists, presence will be consumed by other client's sync
            if client == self._client:
                if sender_server not in other_clients_servers:
                    self._presence_listener(event, presence_update_id)

            elif sender_server == urlparse(client.api.base_url).netloc:
                self._presence_listener(event, presence_update_id)

        return _filter_presence
