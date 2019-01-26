from gevent import monkey
monkey.patch_all()
import requests # noqa
from old.server import MonitoringService

__all__ = [
    'MonitoringService',
]
