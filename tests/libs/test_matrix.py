import pytest
from eth_utils import encode_hex

from monitoring_service.states import HashedBalanceProof
from raiden.exceptions import InvalidProtocolMessage
from raiden.utils import ChannelID
from raiden.utils.typing import ChainID, Nonce, TokenAmount
from raiden_contracts.tests.utils import EMPTY_LOCKSROOT
from raiden_libs.matrix import message_from_dict


def test_message_from_dict(token_network, get_accounts, get_private_key):
    c1, c2 = get_accounts(2)

    balance_proof_c2 = HashedBalanceProof(
        token_network_address=token_network.address,
        channel_identifier=ChannelID(1),
        chain_id=ChainID(1),
        nonce=Nonce(2),
        additional_hash="0x%064x" % 0,
        transferred_amount=TokenAmount(1),
        locked_amount=TokenAmount(0),
        locksroot=encode_hex(EMPTY_LOCKSROOT),
        priv_key=get_private_key(c2),
    )

    request_monitoring = balance_proof_c2.get_request_monitoring(
        privkey=get_private_key(c1), reward_amount=TokenAmount(1)
    )

    message_json = request_monitoring.to_dict()

    # Test happy path
    message = message_from_dict(message_json)
    assert message == request_monitoring

    # Test unknown message type
    message_json["type"] = "SomeNonexistantMessage"
    with pytest.raises(InvalidProtocolMessage) as excinfo:
        message_from_dict(message_json)

    assert 'Invalid message type (data["type"]' in str(excinfo.value)

    # Test non-existant message type
    del message_json["type"]
    with pytest.raises(InvalidProtocolMessage) as excinfo:
        message_from_dict(message_json)

    assert "Invalid message data. Can not find the data type" in str(excinfo.value)
