from gevent import monkey
monkey.patch_all()
import requests # noqa
from monitoring_service.server import MonitoringService

__all__ = [
    'MonitoringService',
]
