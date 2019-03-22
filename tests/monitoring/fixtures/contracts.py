import pytest


@pytest.fixture
def monitoring_service_contract(monitoring_service_external):
    return monitoring_service_external
