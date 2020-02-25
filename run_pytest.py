# This is necessary because otherwise gevent complains that 
# `patch_all` was called to late

from gevent import monkey  # isort:skip # noqa
monkey.patch_all()  # isort:skip # noqa

import pytest
pytest.main()
