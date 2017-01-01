from __future__ import unicode_literals
from .containers import Layout
from .controls import BufferControl, UIControl
from .utils import find_all_controls

__all__ = (
    'Focus',
)


class Focus(object):
    """
    Keep track of which `UIControl` currently has the focus.
    """
    def __init__(self, layout, focussed_control=None):
        assert isinstance(layout, Layout)
        assert focussed_control is None or isinstance(focussed_control, UIControl)

        if focussed_control is None:
            focussed_control = next(find_all_controls(layout))

        self.layout = layout
        self._stack = [focussed_control]

    @property
    def focussed_control(self):
        """
        Get the `UIControl` to currently has the  focus.
        """
        return self._stack[-1]

    @focussed_control.setter
    def focussed_control(self, control):
        """
        Set the `UIControl` to receive the focus.
        """
        assert isinstance(control, UIControl)

        if control != self.focussed_control:
            self._stack.append(control)

    @property
    def previous_focussed_control(self):
        """
        Get the `UIControl` to previously had the focus.
        """
        try:
            return self._stack[-2]
        except IndexError:
            return self._stack[-1]

    def focus_previous(self):
        """
        Give the focus to the previously focussed control.
        """
        if len(self._stack) > 1:
            self._stack = self._stack[:-1]

#    def focussable_controls(self):
#        """
#        Return a list of `UIControl` objects that are focussable in the current
#        layout.
#        """
#        def get_all():
#            for ui_control in find_all_controls(self.layout):
#                if ui_control.is_focussable(cli):
#
#    def focus_next(self):
#        """
#        Focus the next user control.
#        """
