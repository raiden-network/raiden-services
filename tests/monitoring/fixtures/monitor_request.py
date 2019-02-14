import pytest
from eth_utils import encode_hex

from monitoring_service.states import Channel, HashedBalanceProof, UnsignedMonitorRequest
from raiden_libs.utils import private_key_to_address, sha3
from raiden_libs.utils.signing import eth_sign


@pytest.fixture
def get_monitor_request_for_same_channel(
        get_random_address,
        get_random_privkey,
        token_network,
        ms_database,
):
    keys = [get_random_privkey() for i in range(3)]
    token_network_address = token_network.address
    ms_database.conn.execute(
        "INSERT INTO token_network (address) VALUES (?)",
        [token_network_address],
    )

    channel_id = 1
    balance_hash_data = '0'
    ms_database.upsert_channel(Channel(
        identifier=channel_id,
        token_network_address=token_network_address,
        participant1=private_key_to_address(keys[0]),
        participant2=private_key_to_address(keys[1]),
        settle_timeout=20,
    ))

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

        bp = HashedBalanceProof(  # type: ignore
            channel_identifier=channel_id,
            token_network_address=token_network_address,
            chain_id=1,
            balance_hash=encode_hex(sha3(balance_hash_data.encode())),
            nonce=0,
            additional_hash='0x%064x' % 0,
            priv_key=privkey,
        )
        monitor_request = UnsignedMonitorRequest.from_balance_proof(
            bp,
            reward_amount=0,
        ).sign(privkey_non_closing)

        if bad_key_for_bp:
            monitor_request.closing_signature = encode_hex(
                eth_sign(keys[2], monitor_request.packed_balance_proof_data()),
            )
        if bad_key_for_non_closing:
            monitor_request.non_closing_signature = encode_hex(
                eth_sign(keys[2], monitor_request.packed_non_closing_data()),
            )
        return monitor_request
    return f
