import gevent
from matrix_client.user import User


def geventify_callback(callback):
    def inner(*args, **kwargs):
        gevent.spawn(callback, *args, **kwargs)

    return inner


# Monkey patch matrix User class to provide nicer repr
def user__repr__(self):
    return f'<User id="{self.user_id}">'


User.__repr__ = user__repr__
