
def deserialize(message: dict):
    from .balance_proof import BalanceProof
    type_to_class = {
        'BalanceProof': BalanceProof
    }

    message_type = message['header']['type']
    assert message_type in type_to_class
    cls = type_to_class[message_type]
    return cls.deserialize(message['body'])
