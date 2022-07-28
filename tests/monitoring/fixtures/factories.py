import pytest
from eth_utils import encode_hex
from raiden_common.messages.monitoring_service import RequestMonitoring
from raiden_common.utils.typing import ChannelID, Nonce, TokenAmount, TokenNetworkAddress

from monitoring_service.states import HashedBalanceProof
from raiden_contracts.tests.utils.address import get_random_privkey
from raiden_contracts.utils.type_aliases import ChainID, PrivateKey
from raiden_libs.utils import private_key_to_address, to_checksum_address
from tests.constants import TEST_CHAIN_ID, TEST_MSC_ADDRESS


@pytest.fixture
def build_request_monitoring():
    non_closing_privkey = PrivateKey(get_random_privkey())
    non_closing_address = private_key_to_address(non_closing_privkey)

    def f(
        chain_id: ChainID = TEST_CHAIN_ID,
        amount: TokenAmount = TokenAmount(50),
        nonce: Nonce = Nonce(1),
        channel_id: ChannelID = ChannelID(1),
    ) -> RequestMonitoring:
        balance_proof = HashedBalanceProof(
            channel_identifier=channel_id,
            token_network_address=TokenNetworkAddress(b"1" * 20),
            chain_id=chain_id,
            nonce=nonce,
            additional_hash="",
            balance_hash=encode_hex(bytes([amount])),
            priv_key=PrivateKey(get_random_privkey()),
        )
        request_monitoring = balance_proof.get_request_monitoring(
            privkey=non_closing_privkey,
            reward_amount=TokenAmount(55),
            monitoring_service_contract_address=TEST_MSC_ADDRESS,
        )

        # usually not a property of RequestMonitoring, but added for convenience in these tests
        request_monitoring.non_closing_signer = to_checksum_address(non_closing_address)
        return request_monitoring

    return f
