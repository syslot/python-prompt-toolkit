from __future__ import unicode_literals
from prompt_toolkit.utils import is_windows

__all__ = (
    'create_event_loop',
    'create_asyncio_event_loop',
)


def create_event_loop(inputhook=None, recognize_win32_paste=True):
    """
    Create and return an
    :class:`~prompt_toolkit.eventloop.base.EventLoop` instance for a
    :class:`~prompt_toolkit.interface.CommandLineInterface`.
    """
    if is_windows():
        from prompt_toolkit.eventloop.win32 import Win32EventLoop as Loop
        return Loop(inputhook=inputhook, recognize_paste=recognize_win32_paste)
    else:
        from prompt_toolkit.eventloop.posix import PosixEventLoop as Loop
        return Loop(inputhook=inputhook)


def create_asyncio_event_loop(loop=None):
    """
    Returns an asyncio :class:`~prompt_toolkit.eventloop.EventLoop` instance
    for usage in a :class:`~prompt_toolkit.interface.CommandLineInterface`. It
    is a wrapper around an asyncio loop.

    :param loop: The asyncio eventloop (or `None` if the default asyncioloop
                 should be used.)
    """
    # Inline import, to make sure the rest doesn't break on Python 2. (Where
    # asyncio is not available.)
    if is_windows():
        from prompt_toolkit.eventloop.asyncio_win32 import Win32AsyncioEventLoop as AsyncioEventLoop
    else:
        from prompt_toolkit.eventloop.asyncio_posix import PosixAsyncioEventLoop as AsyncioEventLoop

    return AsyncioEventLoop(loop)
