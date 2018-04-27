import pytest
from eth_tester.validation.common import validate_positive_integer
from eth_tester.exceptions import ValidationError


def patched_validate_signature_v(value):
    validate_positive_integer(value)
    if value not in {0, 1, 27, 28, 37, 38}:
        raise ValidationError(
            "The `v` portion of the signature must be 0, 1, 27, 28, 37 or 38, not %d"
            % value
        )


@pytest.fixture(autouse=True)
def patch_validate_signature_v():
    import eth_tester.validation.outbound as outbound
    outbound.validate_signature_v = patched_validate_signature_v
    outbound.TRANSACTION_VALIDATORS['v'] = patched_validate_signature_v
