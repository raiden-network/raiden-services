import gevent
from matrix_client.user import User


def geventify_callback(callback, on_spawn=None):
    def inner(*args, **kwargs):
        spawned = gevent.spawn(callback, *args, **kwargs)
        if on_spawn is not None:
            on_spawn(spawned)

    return inner


# Monkey patch matrix User class to provide nicer repr
def user__repr__(self):
    return f'<User id="{self.user_id}">'


User.__repr__ = user__repr__
