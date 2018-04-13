class MonitoringServiceException(Exception):
    pass


class ServiceNotRegistered(MonitoringServiceException):
    """Raised if MS is not registered in the MS reward SC"""
    pass
