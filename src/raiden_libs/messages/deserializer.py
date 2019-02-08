from typing import Any, Dict


def deserialize(message: Dict) -> Any:
    from .balance_proof import BalanceProof
    from monitoring_service.states import MonitorRequest
    type_to_class = {
        'BalanceProof': BalanceProof,
        'MonitorRequest': MonitorRequest,
    }

    message_type = message.pop('message_type')
    assert message_type in type_to_class
    cls = type_to_class[message_type]
    return cls.deserialize(message)  # type: ignore
