import pytest
from eth_utils import decode_hex, encode_hex

from raiden_contracts.constants import MessageTypeId
from raiden_libs.messages import BalanceProof, MonitorRequest
from raiden_libs.utils import private_key_to_address, sha3
from raiden_libs.utils.signing import eth_sign


@pytest.fixture
def get_monitor_request_for_same_channel(
        get_random_address,
        get_random_privkey,
        token_network,
        state_db_sqlite,
):
    keys = [get_random_privkey() for i in range(3)]
    token_network_address = token_network.address

    channel_id = 1
    balance_hash_data = '0'
    state_db_sqlite.store_new_channel(
        channel_id,
        token_network_address,
        private_key_to_address(keys[0]),
        private_key_to_address(keys[1]),
    )

    def f(
            user=None,
            reward_amount=0,
            bad_key_for_bp=False,
            bad_key_for_non_closing=False,
    ):
        if user == 0:
            privkey = keys[0]
            privkey_non_closing = keys[1]
        else:
            privkey = keys[1]
            privkey_non_closing = keys[0]
        balance_proof = BalanceProof(
            channel_id,
            token_network_address,
            balance_hash=encode_hex(sha3(balance_hash_data.encode())),
        )
        balance_proof.signature = encode_hex(eth_sign(
            privkey if not bad_key_for_bp else keys[2],
            balance_proof.serialize_bin(),
        ))
        non_closing_signature = encode_hex(eth_sign(
            privkey_non_closing if not bad_key_for_non_closing else keys[2],
            balance_proof.serialize_bin(msg_type=MessageTypeId.BALANCE_PROOF_UPDATE) +
            decode_hex(balance_proof.signature),
        ))

        monitor_request = MonitorRequest(
            balance_proof,
            non_closing_signature,
            reward_amount=reward_amount,
            monitor_address=get_random_address(),
        )
        monitor_request.reward_proof_signature = encode_hex(
            eth_sign(privkey, monitor_request.serialize_reward_proof()),
        )
        return monitor_request
    return f
