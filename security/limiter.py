import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# =========================================================
# PERFORMANCE TEST MODE
# =========================================================

PERFORMANCE_TESTING = (
    os.getenv(
        "PERFORMANCE_TESTING",
        "false"
    ).lower() == "true"
)


# =========================================================
# LIMITER
# =========================================================

limiter = Limiter(

    key_func=get_remote_address,

    default_limits=[
        "500 per day",
        "100 per hour"
    ],

    storage_uri="memory://",

    enabled=not PERFORMANCE_TESTING
)