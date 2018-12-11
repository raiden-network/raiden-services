import logging
import random

import click
import gevent

from monitoring_service.messages import BalanceProof
from monitoring_service.tools.eventgen import EventGenerator
from monitoring_service.tools.random_channel import SeededRandomizer, use_random_state
from monitoring_service.transport import MatrixTransport

log = logging.getLogger(__name__)


class MockClient(SeededRandomizer):
    def __init__(self, transport, seed, channel_db):
        super().__init__(seed)
        self.transport = transport
        self.sleep_mu = 5
        self.sleep_sigma = 0.9
        self.channel_db = channel_db

    def generate_msg(self):
        if len(self.channel_db.channel_db) == 0:
            return
        channel = random.choice(self.channel_db.channel_db)
        return BalanceProof(
            channel['channel_address'],
            channel['participant1'],
            channel['participant2']
        )

    @use_random_state
    def get_balance_proof(self, address):
        return hex(random.randint(0, 2**32))

    @use_random_state
    def run(self):
        self.transport.connect()

        while True:
            msg = self.generate_msg()
            if msg is not None:
                self.transport.send_message(msg)
            sleep_for = random.normalvariate(self.sleep_mu, self.sleep_sigma)
            log.debug('sleeping for %fs before submitting another BP' % (sleep_for))
            gevent.sleep(sleep_for)


@click.command()
@click.option(
    '--monitoring-channel',
    default='#monitor_test:transport01.raiden.network',
    help='Location of the monitoring channel to connect to'
)
@click.option(
    '--matrix-homeserver',
    default='https://transport01.raiden.network',
    help='Matrix username'
)
@click.option(
    '--matrix-username',
    default=None,
    required=True,
    help='Matrix username'
)
@click.option(
    '--matrix-password',
    default=None,
    required=True,
    help='Matrix password'
)
@click.option(
    '--seed',
    default=0,
    help='initial seed'
)
@click.option(
    '--monitor-host',
    default='http://localhost:5001',
    help='monitor RPC endpoint'
)
@click.option(
    '--private-key',
    required=True,
    type=str
)
def main(monitoring_channel,
         matrix_homeserver,
         matrix_username,
         matrix_password,
         seed,
         monitor_host,
         private_key
         ):
    event_generator = EventGenerator(monitor_host, seed)
    transport = MatrixTransport(
        matrix_homeserver,
        matrix_username,
        matrix_password,
        monitoring_channel
    )
    transport.privkey = private_key
    mock_client = MockClient(transport, seed, event_generator.db)
    event_generator.start()
    mock_client.run()


if __name__ == "__main__":
    gevent.monkey.patch_all()
    logging.basicConfig(level=logging.DEBUG)
    main()
