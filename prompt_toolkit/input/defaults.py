from __future__ import unicode_literals
from .base import Input
from ..utils import is_windows
import sys
import io

if is_windows():
    from .win32 import raw_mode, cooked_mode
else:
    from .vt100 import raw_mode, cooked_mode

__all__ = (
    'StdinInput',
)


class StdinInput(Input):
    """
    Simple wrapper around stdin.
    """
    def __init__(self, stdin=None):
        self.stdin = stdin or sys.stdin

        # The input object should be a TTY.
        assert self.stdin.isatty()

        # Test whether the given input object has a file descriptor.
        # (Idle reports stdin to be a TTY, but fileno() is not implemented.)
        try:
            # This should not raise, but can return 0.
            self.stdin.fileno()
        except io.UnsupportedOperation:
            if 'idlelib.run' in sys.modules:
                raise io.UnsupportedOperation(
                    'Stdin is not a terminal. Running from Idle is not supported.')
            else:
                raise io.UnsupportedOperation('Stdin is not a terminal.')

    def __repr__(self):
        return 'StdinInput(stdin=%r)' % (self.stdin,)

    def raw_mode(self):
        return raw_mode(self.stdin.fileno())

    def cooked_mode(self):
        return cooked_mode(self.stdin.fileno())

    def fileno(self):
        return self.stdin.fileno()

    def read(self):
        return self.stdin.read()

