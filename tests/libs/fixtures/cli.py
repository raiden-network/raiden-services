from typing import List

import pytest
from tests.constants import KEYSTORE_PASSWORD


@pytest.fixture
def default_cli_args(keystore_file) -> List[str]:
    return [
        "--keystore-file",
        keystore_file,
        "--password",
        KEYSTORE_PASSWORD,
        "--state-db",
        ":memory:",
        "--accept-disclaimer",
    ]
