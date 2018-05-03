import gevent


def geventify_callback(callback):
    def inner(*args, **kwargs):
        gevent.spawn(callback, *args, **kwargs)

    return inner
