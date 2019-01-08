import logging
import random

from raiden_libs.utils import private_key_to_address

log = logging.getLogger(__name__)


def use_random_state(function):
    def wrap(self, *args, **kwargs):
        random.setstate(self.random_state)
        ret = function(self, *args, **kwargs)
        self.random_state = random.getstate()
        return ret
    return wrap


class SeededRandomizer:
    def __init__(self, seed):
        random.seed(seed)
        self.random_state = random.getstate()


class RandomAddressDB(SeededRandomizer):
    def __init__(self, seed, initial_addrs=10):
        super().__init__(seed)
        self._addrs = [
            self.get_addr() for _ in range(initial_addrs)
        ]

    @use_random_state
    def get_addr(self):
        return private_key_to_address(hex(random.randint(1, 2**256)))

    def generate_addr(self):
        addr = self.get_addr()
        self._addrs.append(addr)
        return addr

    @use_random_state
    def get_random_addr(self):
        return random.choice(self._addrs)

    @property
    def addrs(self):
        return self._addrs


class RandomChannelDB(SeededRandomizer):
    def __init__(self, seed):
        super().__init__(seed)
        self.address_db = RandomAddressDB(seed)
        self.channel_db = list()

    def new_channel(self):
        p1, p2 = self.get_random_participants()
        channel = {
            'channel_address': self.get_random_address(),
            'participant1': p1,
            'participant2': p2,
            'nonce': self.random_nonce(),
        }
        self.channel_db.append(channel)
        return channel

    @use_random_state
    def random_nonce(self):
        nonce = random.randint(1, 0xffff)
        return nonce

    @use_random_state
    def get_random_address(self):
        return random.choice(self.address_db.addrs)

    @use_random_state
    def get_random_participants(self):
        """Get pair of random participants"""
        fuse = 10
        while fuse != 0:
            node1 = self.get_random_address()
            node2 = self.get_random_address()
            if node1 != node2:
                return (node1, node2)
            fuse -= 1
        log.fatal('fuse blew up!')
        assert fuse
