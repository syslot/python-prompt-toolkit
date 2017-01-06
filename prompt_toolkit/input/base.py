"""
Abstraction of CLI Input.
"""
from __future__ import unicode_literals

from ..utils import DummyContext
from abc import ABCMeta, abstractmethod
from six import with_metaclass

import os

__all__ = (
    'Input',
    'PipeInput',
)


class Input(with_metaclass(ABCMeta, object)):
    """
    Abstraction for any input.

    An instance of this class can be given to the constructor of a
    :class:`~prompt_toolkit.application.Application` and will also be
    passed to the :class:`~prompt_toolkit.eventloop.base.EventLoop`.
    """
    @abstractmethod
    def fileno(self):
        """
        Fileno for putting this in an event loop.
        """

    @abstractmethod
    def read(self):
        """
        Return text from the input.
        """

    @abstractmethod
    def raw_mode(self):
        """
        Context manager that turns the input into raw mode.
        """

    @abstractmethod
    def cooked_mode(self):
        """
        Context manager that turns the input into cooked mode.
        """


class PipeInput(Input):
    """
    Input that is send through a pipe.
    This is useful if we want to send the input programatically into the
    interface, but still use the eventloop.

    Usage::

        input = PipeInput()
        input.send('inputdata')
    """
    def __init__(self):
        self._r, self._w = os.pipe()

    def fileno(self):
        return self._r

    def read(self):
        return os.read(self._r)

    def send_text(self, data):
        " Send text to the input. "
        os.write(self._w, data.encode('utf-8'))

    def raw_mode(self):
        return DummyContext()

    def cooked_mode(self):
        return DummyContext()

    def close(self):
        " Close pipe fds. "
        os.close(self._r)
        os.close(self._w)
        self._r = None
        self._w = None
