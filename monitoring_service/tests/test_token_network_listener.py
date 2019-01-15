import gevent
import pytest

from monitoring_service.token_network_listener import TokenNetworkListener


@pytest.fixture
def get_token_network_listener(
    web3,
    contracts_manager,
    token_network_registry_contract,
    state_db_sqlite,
):
    def get():
        return TokenNetworkListener(
            web3,
            contracts_manager,
            registry_address=token_network_registry_contract.address,
            sync_start_block=0,
            required_confirmations=1,
            poll_interval=0.001,
            load_syncstate=state_db_sqlite.load_syncstate,
            save_syncstate=state_db_sqlite.save_syncstate,
            get_synced_contracts=state_db_sqlite.get_synced_contracts,
        )
    return get


def test_syncstate_registry(
    web3,
    state_db_sqlite,
    wait_for_blocks,
    get_token_network_listener,
):
    """ Test saving and loading of syncstate """
    old_head = web3.eth.blockNumber
    token_network_listener = get_token_network_listener()
    token_network_listener.start()
    wait_for_blocks(2)
    gevent.sleep(0.1)
    syncstates = state_db_sqlite.conn.execute("SELECT * FROM syncstate").fetchall()
    assert len(syncstates) == 1
    syncstate = syncstates[0]
    assert syncstate['unconfirmed_head_number'] == old_head + 2
    assert syncstate['confirmed_head_number'] == old_head + 1
    token_network_listener.stop()

    token_network_listener = get_token_network_listener()
    listener = token_network_listener.token_network_registry_listener
    assert listener.confirmed_head_number == syncstate['confirmed_head_number']
    assert listener.confirmed_head_hash == syncstate['confirmed_head_hash']
    assert listener.unconfirmed_head_number == syncstate['unconfirmed_head_number']
    assert listener.unconfirmed_head_hash == syncstate['unconfirmed_head_hash']


def test_syncstate_token_network(
    web3,
    state_db_sqlite,
    wait_for_blocks,
    get_token_network_listener,
    register_token_network,
    custom_token,
    token_network_registry_contract,
):
    """ Test saving and loading of syncstate """
    token_network_listener = get_token_network_listener()
    token_network_listener.start()
    register_token_network(custom_token.address)
    old_head = web3.eth.blockNumber
    wait_for_blocks(2)
    gevent.sleep(0.1)
    syncstates = state_db_sqlite.conn.execute(
        "SELECT * FROM syncstate WHERE contract_address != ?",
        [token_network_registry_contract.address],
    ).fetchall()
    assert len(syncstates) == 1
    syncstate = syncstates[0]
    assert syncstate['unconfirmed_head_number'] == old_head + 2
    assert syncstate['confirmed_head_number'] == old_head + 1
    token_network_listener.stop()

    token_network_listener = get_token_network_listener()
    listener = token_network_listener.token_network_listeners[0]
    assert listener.confirmed_head_number == syncstate['confirmed_head_number']
    assert listener.confirmed_head_hash == syncstate['confirmed_head_hash']
    assert listener.unconfirmed_head_number == syncstate['unconfirmed_head_number']
    assert listener.unconfirmed_head_hash == syncstate['unconfirmed_head_hash']
