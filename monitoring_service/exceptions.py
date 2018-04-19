class MonitoringServiceException(Exception):
    pass


class ServiceNotRegistered(MonitoringServiceException):
    """Raised if MS is not registered in the MS reward SC"""
    pass


class StateDBInvalid(MonitoringServiceException):
    """Raised if state DB metadata do not match current setup"""
