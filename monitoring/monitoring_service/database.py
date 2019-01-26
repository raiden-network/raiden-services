from typing import List, Optional

from monitoring_service.states import Channel, MonitoringServiceState


class Database:
    def __init__(self):
        self.channels: List[Channel] = []
        self.ms_state: MonitoringServiceState = None

    def upsert_channel(self, channel: Channel):
        try:
            index = self.channels.index(channel)
            self.channels[index] = channel
        except ValueError:
            self.channels.append(channel)

    def get_channel(self, channel_id: int) -> Optional[Channel]:
        for c in self.channels:
            if c.identifier == channel_id:
                return c

        return None

    def update_state(self, state: MonitoringServiceState):
        self.ms_state = state

    def __repr__(self):
        return '<DB [{}]>'.format(', '.join(str(e) for e in self.channels))
