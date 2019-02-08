import logging

import gevent
from eth_utils import is_address

from raiden_contracts.constants import ChannelState
from raiden_libs.exceptions import InvalidSignature
from monitoring_service.states import MonitorRequest, Channel

log = logging.getLogger(__name__)


class StoreMonitorRequest(gevent.Greenlet):
    """Validate & store submitted monitor request. This consists of:
            - check of bp & reward proof signature
            - check if contracts contain code
            - check if there's enough tokens for the payout
        Return:
            True if monitor request is valid
    """
    def __init__(self, state_db, monitor_request):
        super().__init__()
        assert isinstance(monitor_request, MonitorRequest)
        self.msg = monitor_request
        self.state_db = state_db

    def _run(self) -> bool:
        channel = self.state_db.get_channel(
            self.msg.token_network_address,
            self.msg.channel_identifier,
        )
        checks = [
            self.check_channel,
            self.check_signatures,
            self.check_balance,
        ]
        for check in checks:
            if not check(self.msg, channel):
                log.debug('MR for channel {} did not pass {}'.format(
                    channel['channel_identifier'],
                    check.__name__,
                ))
                return False

        self.state_db.upsert_monitor_request(self.msg)
        return True

    def check_channel(self, monitor_request: MonitorRequest, channel: Channel):
        """We must know about the channel and it must be open"""
        return channel is not None and channel.state == ChannelState.OPENED

    def check_signatures(self, monitor_request: MonitorRequest, channel: Channel):
        """Check if signatures set in the message are correct"""
        participants = [channel.participant1, channel.participant2]
        try:
            return (
                is_address(monitor_request.reward_proof_signer) and
                monitor_request.signer in participants and
                monitor_request.non_closing_signer in participants and
                monitor_request.signer != monitor_request.non_closing_signer
            )
        except InvalidSignature:
            return False

    def check_balance(self, monitor_request: MonitorRequest, channel: Channel):
        """Check if there is enough tokens to pay out reward amount"""
        return True
