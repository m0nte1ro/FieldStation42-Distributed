import datetime

# schedules are naive local time on the server; a client plays them against the server's clock
# so clients on one channel agree, even a Pi whose clock is wrong until NTP catches up
_offset = datetime.timedelta(0)


def set_server_time(server_time, received_at=None):
    global _offset
    received_at = received_at or datetime.datetime.now()
    _offset = datetime.datetime.fromisoformat(server_time) - received_at


def now():
    return datetime.datetime.now() + _offset
