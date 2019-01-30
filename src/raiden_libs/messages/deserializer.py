from typing import Dict


def deserialize(message: Dict):
    from .balance_proof import BalanceProof
    from .monitor_request import MonitorRequest
    from .fee_info import FeeInfo
    from .paths_request import PathsRequest
    from .paths_reply import PathsReply
    type_to_class = {
        'BalanceProof': BalanceProof,
        'MonitorRequest': MonitorRequest,
        'FeeInfo': FeeInfo,
        'PathsRequest': PathsRequest,
        'PathsReply': PathsReply,
    }

    message_type = message.pop('message_type')
    assert message_type in type_to_class
    cls = type_to_class[message_type]
    return cls.deserialize(message)  # type: ignore
