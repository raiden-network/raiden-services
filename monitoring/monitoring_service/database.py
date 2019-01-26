from typing import List, Optional

from monitoring_service.states import Channel, MonitoringServiceState, MonitorRequest


class Database:
    def __init__(self):
        self.channels: List[Channel] = []
        self.monitor_requests: List[MonitorRequest] = []
        self.ms_state: MonitoringServiceState = None

    def upsert_channel(self, channel: Channel):
        try:
            index = self.channels.index(channel)
            self.channels[index] = channel
        except ValueError:
            self.channels.append(channel)

    def get_channel(self, token_network_address: str, channel_id: int) -> Optional[Channel]:
        for c in self.channels:
            if c.token_network_address == token_network_address and c.identifier == channel_id:
                return c

        return None

    def update_state(self, state: MonitoringServiceState):
        self.ms_state = state

    def upsert_monitor_request(self, request: MonitorRequest):
        try:
            index = self.monitor_requests.index(request)
            self.monitor_requests[index] = request
        except ValueError:
            self.monitor_requests.append(request)

    def get_monitor_request(
            self,
            token_network_address: str,
            channel_id: int,
    ) -> Optional[MonitorRequest]:
        for mr in self.monitor_requests:
            if (
                mr.token_network_address == token_network_address and
                mr.channel_identifier == channel_id
            ):
                return mr

        return None

    def __repr__(self):
        return '<DB [{}]>'.format(', '.join(str(e) for e in self.channels))
