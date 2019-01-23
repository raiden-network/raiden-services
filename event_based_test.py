from dataclasses import dataclass, field
from pprint import pprint
from typing import Optional, List
from collections import deque


@dataclass
class MonitorRequest:
    reward: int = 0


@dataclass
class Channel:
    channel_identifier: int
    channel_state: int = 0
    on_chain_confirmation: bool = True
    monitor_request: Optional[MonitorRequest] = None


class DB:
    def __init__(self):
        self.channels: List[Channel] = []

    def store_channel(self, channel: Channel):
        try:
            index = self.channels.index(channel)
            self.channels[index] = channel
        except ValueError:
            self.channels.append(channel)

    def get_channel(self, channel_id: int) -> Optional[Channel]:
        for c in self.channels:
            if c.channel_identifier == channel_id:
                return c

        return None

    def __repr__(self):
        return '<DB [{}]>'.format(', '.join(str(e) for e in self.channels))


class Event:
    pass


@dataclass
class BlockchainChannelOpenEvent(Event):
    channel_id: int


@dataclass
class BlockchainChannelClosedEvent(Event):
    channel_id: int


@dataclass
class NewBlockEvent(Event):
    block_number: int


@dataclass
class OffchainMonitorRequest(Event):
    channel_id: int
    reward: int


@dataclass
class ActionMonitoringTriggeredEvent(Event):
    channel_id: int


@dataclass
class BCListener:
    """ This is pull-based instead of push-based."""

    registry_address: str = ''
    network_addresses: List[str] = field(default_factory=list)

    def get_events(self, from_block, to_block) -> List[Event]:
        e1 = BlockchainChannelOpenEvent(channel_id=1)
        e2 = BlockchainChannelClosedEvent(channel_id=1)
        e3 = BlockchainChannelClosedEvent(channel_id=2)

        return [e1, e2, e3]


class MatrixListener:
    def get_events(self):
        e1 = OffchainMonitorRequest(channel_id=1, reward=5)
        e2 = OffchainMonitorRequest(channel_id=2, reward=1)

        return [e1, e2]


@dataclass
class MSState:
    db: DB
    bcl: BCListener
    ml: MatrixListener
    latest_known_block: int = 0
    event_queue: deque = deque()


class EventHandler:
    def handle_event(self, event: Event):
        raise NotImplementedError


@dataclass
class ChannelOpenEventHandler(EventHandler):
    state: MSState

    def handle_event(self, event: Event):
        if isinstance(event, BlockchainChannelOpenEvent):
            self.state.db.store_channel(
                Channel(event.channel_id)
            )


@dataclass
class ChannelClosedEventHandler(EventHandler):
    state: MSState

    def handle_event(self, event: Event):
        if isinstance(event, BlockchainChannelClosedEvent):
            channel = self.state.db.get_channel(event.channel_id)

            if channel and channel.on_chain_confirmation:
                print('Trying to monitor channel: ', channel.channel_identifier)
                channel.channel_state = 1

                # trigger the monitoring action by an event
                e = ActionMonitoringTriggeredEvent(channel.channel_identifier)
                s.event_queue.append(e)

                self.state.db.store_channel(channel)
            else:
                print('Closing channel not confirmed')


@dataclass
class NewBlockEventHandler(EventHandler):
    state: MSState

    def handle_event(self, event: Event):
        if isinstance(event, NewBlockEvent):
            print('Received new block', event.block_number)
            self.state.latest_known_block = event.block_number
            # TODO: save this


@dataclass
class ActionMonitoringTriggeredEventHandler(EventHandler):
    state: MSState

    def handle_event(self, event: Event):
        if isinstance(event, ActionMonitoringTriggeredEvent):
            print('Triggering check if monitoring necessary')


@dataclass
class MonitorRequestEventHandler(EventHandler):
    state: MSState

    def handle_event(self, event: Event):
        if isinstance(event, OffchainMonitorRequest):
            channel = self.state.db.get_channel(event.channel_id)

            request = MonitorRequest(reward=event.reward)
            if channel:
                channel.monitor_request = request

                self.state.db.store_channel(channel)
            else:
                # channel has not been confirmed on BC yet
                # wait for PC confirmation
                c = Channel(
                    event.channel_id,
                    on_chain_confirmation=False,
                    monitor_request=request
                )
                self.state.db.store_channel(c)


db = DB()
bcl = BCListener()
ml = MatrixListener()
s = MSState(db, bcl, ml)
eh1 = ChannelOpenEventHandler(s)
eh2 = MonitorRequestEventHandler(s)
eh3 = ChannelClosedEventHandler(s)
eh4 = NewBlockEventHandler(s)
eh5 = ActionMonitoringTriggeredEventHandler(s)

handlers = {
    BlockchainChannelOpenEvent: eh1,
    BlockchainChannelClosedEvent: eh3,
    OffchainMonitorRequest: eh2,
    NewBlockEvent: eh4,
    ActionMonitoringTriggeredEvent: eh5,
}


def loop():
    new_block = 100
    if new_block > s.latest_known_block:
        events = s.bcl.get_events(s.latest_known_block, new_block)

        s.event_queue.extend(events)
        # this will save the new state
        s.event_queue.append(NewBlockEvent(new_block))

    update_matrix = True
    if update_matrix:
        events = s.ml.get_events()

        s.event_queue.extend(events)

    # Process all events
    while len(s.event_queue) > 0:
        print('>---------------')
        print(f'> {len(s.event_queue)} events in queue')
        event = s.event_queue.popleft()
        print('> Current event:', event)

        handler: EventHandler = handlers[type(event)]
        handler.handle_event(event)
        pprint(db.channels)


loop()

# Open questions
# how to trigger event on certain block numbers?
#   - idea: internal mapping: block number -> event
#           gets activated by NewBlockEvent
# error handling?
#   - idea: return errors when handling events
