from monitoring_service.tools.register_ms import monitor_registration


def test_registry_script(web3, monitoring_service_contract, generate_raiden_client):
    """Test MS registration script"""
    c1 = generate_raiden_client()

    assert monitor_registration(
        web3,
        monitoring_service_contract.address,
        c1.address,
        c1.privkey
    ) is True
