import contextlib
import fcntl
import os


@contextlib.contextmanager
def schedule_write_lock(lock_path="runtime/schedule.lock"):
    # the server's schedule agent, web builds and the CLI run in different processes,
    # so only a lock on a shared file stops two of them extending the same schedule at once
    lock_dir = os.path.dirname(lock_path)
    if lock_dir:
        os.makedirs(lock_dir, exist_ok=True)
    with open(lock_path, "a") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
