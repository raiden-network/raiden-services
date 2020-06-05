from typing import Any, Dict, Optional


class ApiException(Exception):
    """An exception that can be returned via the REST API"""

    msg: str = "Unknown Error"
    http_code: int = 400
    error_code: int = 0
    error_details: Optional[Dict[str, Any]] = None

    def __init__(self, msg: Optional[str] = None, **details: Any):
        super().__init__(msg)
        if msg:
            self.msg = msg
        self.error_details = details

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.error_details})"
