import random

from eth_utils import decode_hex

from monitoring_service.states import (
    Channel,
    HashedBalanceProof,
    MonitorRequest,
    OnChainUpdateStatus,
)
from raiden.constants import UINT256_MAX
from raiden.tests.utils.factories import make_transaction_hash
from raiden.utils.typing import (
    BlockNumber,
    BlockTimeout,
    ChainID,
    ChannelID,
    Nonce,
    Optional,
    TokenAddress,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_contracts.constants import ChannelState
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.utils import private_key_to_address
from tests.constants import TEST_MSC_ADDRESS

DEFAULT_TOKEN_NETWORK_ADDRESS = TokenNetworkAddress(bytes([1] * 20))
DEFAULT_TOKEN_ADDRESS = TokenAddress(bytes([9] * 20))
DEFAULT_CHANNEL_IDENTIFIER = ChannelID(3)
DEFAULT_PRIVATE_KEY1 = PrivateKey(decode_hex("0x" + "1" * 64))
DEFAULT_PRIVATE_KEY2 = PrivateKey(decode_hex("0x" + "2" * 64))
DEFAULT_PARTICIPANT1 = private_key_to_address(DEFAULT_PRIVATE_KEY1)
DEFAULT_PARTICIPANT2 = private_key_to_address(DEFAULT_PRIVATE_KEY2)
DEFAULT_PRIVATE_KEY_OTHER = PrivateKey(decode_hex("0x" + "3" * 64))
DEFAULT_PARTICIPANT_OTHER = private_key_to_address(DEFAULT_PRIVATE_KEY_OTHER)
DEFAULT_REWARD_AMOUNT = TokenAmount(1)
DEFAULT_SETTLE_TIMEOUT = BlockTimeout(100)


def create_signed_monitor_request(
    chain_id: ChainID = ChainID(61),
    nonce: Nonce = Nonce(5),
    reward_amount: TokenAmount = DEFAULT_REWARD_AMOUNT,
    closing_privkey: PrivateKey = DEFAULT_PRIVATE_KEY1,
    nonclosing_privkey: PrivateKey = DEFAULT_PRIVATE_KEY2,
) -> MonitorRequest:
    bp = HashedBalanceProof(
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        chain_id=chain_id,
        balance_hash="",
        nonce=nonce,
        additional_hash="",
        priv_key=closing_privkey,
    )
    monitor_request = bp.get_monitor_request(
        privkey=nonclosing_privkey, reward_amount=reward_amount, msc_address=TEST_MSC_ADDRESS
    )

    # Some signature correctness checks
    assert monitor_request.signer == private_key_to_address(closing_privkey)
    assert monitor_request.non_closing_signer == private_key_to_address(nonclosing_privkey)
    assert monitor_request.reward_proof_signer == private_key_to_address(nonclosing_privkey)

    return monitor_request


def create_channel(update_status: Optional[OnChainUpdateStatus] = None) -> Channel:
    return Channel(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        identifier=DEFAULT_CHANNEL_IDENTIFIER,
        participant1=DEFAULT_PARTICIPANT1,
        participant2=DEFAULT_PARTICIPANT2,
        settle_timeout=random.randint(0, UINT256_MAX),
        state=random.choice(list(ChannelState)),
        closing_block=BlockNumber(random.randint(0, UINT256_MAX)),
        closing_participant=DEFAULT_PARTICIPANT1,
        monitor_tx_hash=make_transaction_hash(),
        claim_tx_hash=make_transaction_hash(),
        update_status=update_status,
    )
