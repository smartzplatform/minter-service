
import os
import fcntl
import errno


class FileLock(object):

    def __init__(self, filename, non_blocking=False, shared=False):
        self._filename = filename
        self._non_blocking = non_blocking
        self._shared = shared
        self._fd = None

    def __enter__(self):
        self.lock()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unlock()

    def lock(self):
        assert self._fd is None
        fd = os.open(self._filename, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o600)

        try:
            operation = ((fcntl.LOCK_SH if self._shared else fcntl.LOCK_EX)
                         | (fcntl.LOCK_NB if self._non_blocking else 0))
            try:
                fcntl.flock(fd, operation)
            except OSError as exc:
                if self._non_blocking and exc.errno in (errno.EWOULDBLOCK, errno.EACCES):
                    raise WouldBlockError(self._filename)
                raise
        except:
            os.close(fd)
            raise
        else:
            self._fd = fd

        return None

    def unlock(self):
        assert self._fd is not None
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None


class WouldBlockError(OSError):

    def __init__(self, filename):
        super().__init__()
        self.errno = errno.EWOULDBLOCK
        self.filename = filename
