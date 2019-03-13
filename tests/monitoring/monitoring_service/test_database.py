from monitoring_service.events import ActionMonitoringTriggeredEvent, ScheduledEvent


def test_scheduled_events(ms_database):
    # Add token network used as foreign key
    ms_database.conn.execute(
        "INSERT INTO token_network(address) VALUES (?)",
        ['a'],
    )

    event1 = ScheduledEvent(
        trigger_block_number=23,
        event=ActionMonitoringTriggeredEvent(
            token_network_address='a',
            channel_identifier=1,
            non_closing_participant='b',
        ),
    )

    assert ms_database.scheduled_event_count() == 0
    ms_database.upsert_scheduled_event(event=event1)
    assert ms_database.scheduled_event_count() == 1

    event2 = ScheduledEvent(
        trigger_block_number=24,
        event=ActionMonitoringTriggeredEvent(
            token_network_address='a',
            channel_identifier=1,
            non_closing_participant='b',
        ),
    )

    ms_database.upsert_scheduled_event(event=event2)
    assert ms_database.scheduled_event_count() == 2

    assert len(ms_database.get_scheduled_events(22)) == 0
    assert len(ms_database.get_scheduled_events(23)) == 1
    assert len(ms_database.get_scheduled_events(24)) == 2

    ms_database.remove_scheduled_event(event2)
    assert len(ms_database.get_scheduled_events(22)) == 0
    assert len(ms_database.get_scheduled_events(23)) == 1
    assert len(ms_database.get_scheduled_events(24)) == 1
