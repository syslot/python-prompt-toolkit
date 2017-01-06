from __future__ import unicode_literals

from .buffer import Buffer
from .cache import SimpleCache
from .clipboard import Clipboard, InMemoryClipboard
from .enums import EditingMode
from .eventloop.base import EventLoop
from .eventloop.callbacks import EventLoopCallbacks
from .filters import CLIFilter, to_cli_filter
from .filters import Condition, IsSearching
from .input import StdinInput, Input
from .key_binding.defaults import load_key_bindings
from .key_binding.input_processor import InputProcessor, KeyPress
from .key_binding.registry import Registry, BaseRegistry, MergedRegistry, ConditionalRegistry
from .key_binding.vi_state import ViState
from .keys import Keys
from .layout.containers import Container, Window
from .layout.controls import BufferControl, UIControl
from .layout.focus import Focus
from .layout.utils import find_all_controls
from .output import Output
from .output.defaults import create_output
from .renderer import Renderer, print_tokens
from .search_state import SearchState
from .styles import DEFAULT_STYLE, Style
from .utils import Event

from subprocess import Popen
import functools
import os
import signal
import six
import six
import sys
import textwrap
import threading
import time
import types
import weakref

__all__ = (
    'AbortAction',
    'Application',
)


class AbortAction(object):
    """
    Actions to take on an Exit or Abort exception.
    """
    RETRY = 'retry'
    RAISE_EXCEPTION = 'raise-exception'
    RETURN_NONE = 'return-none'

    _all = (RETRY, RAISE_EXCEPTION, RETURN_NONE)


class Application(object):
    """
    The main Application class!
    This glues everything together.

    :param layout: A :class:`~prompt_toolkit.layout.containers.Container` instance.
    :param key_bindings_registry:
        :class:`~prompt_toolkit.key_binding.registry.BaseRegistry` instance for
        the key bindings.
    :param clipboard: :class:`~prompt_toolkit.clipboard.base.Clipboard` to use.
    :param on_abort: What to do when Control-C is pressed.
    :param on_exit: What to do when Control-D is pressed.
    :param use_alternate_screen: When True, run the application on the alternate screen buffer.
    :param get_title: Callable that returns the current title to be displayed in the terminal.
    :param erase_when_done: (bool) Clear the application output when it finishes.
    :param reverse_vi_search_direction: Normally, in Vi mode, a '/' searches
        forward and a '?' searches backward. In readline mode, this is usually
        reversed.
    :param focussed_control: The `UIControl` object that gets the initially the focus.

    Filters:

    :param mouse_support: (:class:`~prompt_toolkit.filters.CLIFilter` or
        boolean). When True, enable mouse support.
    :param paste_mode: :class:`~prompt_toolkit.filters.CLIFilter` or boolean.
    :param editing_mode: :class:`~prompt_toolkit.enums.EditingMode`.

    Callbacks (all of these should accept a
    :class:`~prompt_toolkit.application.Application` object as input.)

    :param on_input_timeout: Called when there is no input for x seconds.
                    (Fired when any eventloop.onInputTimeout is fired.)
    :param on_start: Called when reading input starts.
    :param on_stop: Called when reading input ends.
    :param on_reset: Called during reset.
    :param on_render: Called right after rendering.
    :param on_invalidate: Called when the UI has been invalidated.

    I/O:

    :param eventloop: The :class:`~prompt_toolkit.eventloop.base.EventLoop` to
                      be used when `run` is called. The easiest way to create
                      an eventloop is by calling
                      :meth:`~prompt_toolkit.shortcuts.create_eventloop`.
    :param input: :class:`~prompt_toolkit.input.Input` instance.
    :param output: :class:`~prompt_toolkit.output.Output` instance. (Probably
                   Vt100_Output or Win32Output.)
    """
    def __init__(self, layout=None,
                 style=None,
                 key_bindings_registry=None, clipboard=None,
                 on_abort=AbortAction.RAISE_EXCEPTION, on_exit=AbortAction.RAISE_EXCEPTION,
                 use_alternate_screen=False, mouse_support=False,
                 get_title=None,

                 paste_mode=False,
                 editing_mode=EditingMode.EMACS,
                 erase_when_done=False,
                 reverse_vi_search_direction=False,
                 focussed_control=None,

                 on_input_timeout=None, on_start=None, on_stop=None,
                 on_reset=None, on_render=None, on_invalidate=None,

                 # I/O.
                 loop=None, input=None, output=None):

        paste_mode = to_cli_filter(paste_mode)
        mouse_support = to_cli_filter(mouse_support)
        reverse_vi_search_direction = to_cli_filter(reverse_vi_search_direction)

        assert isinstance(layout, Container)
        assert key_bindings_registry is None or isinstance(key_bindings_registry, BaseRegistry)
        assert clipboard is None or isinstance(clipboard, Clipboard)
        assert on_abort in AbortAction._all
        assert on_exit in AbortAction._all
        assert isinstance(use_alternate_screen, bool)
        assert get_title is None or callable(get_title)
        assert isinstance(paste_mode, CLIFilter)
        assert isinstance(editing_mode, six.string_types)
        assert on_input_timeout is None or callable(on_input_timeout)
        assert style is None or isinstance(style, Style)
        assert isinstance(erase_when_done, bool)
        assert focussed_control is None or isinstance(focussed_control, UIControl)

        assert on_start is None or callable(on_start)
        assert on_stop is None or callable(on_stop)
        assert on_reset is None or callable(on_reset)
        assert on_render is None or callable(on_render)
        assert on_invalidate is None or callable(on_invalidate)

        assert isinstance(loop, EventLoop), 'Passing an eventloop is required.'
        assert output is None or isinstance(output, Output)
        assert input is None or isinstance(input, Input)

        self.style = style or DEFAULT_STYLE

        if key_bindings_registry is None:
            key_bindings_registry = load_key_bindings()

        if get_title is None:
            get_title = lambda: None

        self.layout = layout
        self.key_bindings_registry = key_bindings_registry
        self.clipboard = clipboard or InMemoryClipboard()
        self.on_abort = on_abort
        self.on_exit = on_exit
        self.use_alternate_screen = use_alternate_screen
        self.mouse_support = mouse_support
        self.get_title = get_title

        self.paste_mode = paste_mode
        self.editing_mode = editing_mode
        self.erase_when_done = erase_when_done
        self.reverse_vi_search_direction = reverse_vi_search_direction

        # Events.
        self.on_input_timeout = Event(self, on_input_timeout)
        self.on_invalidate = Event(self, on_invalidate)
        self.on_render = Event(self, on_render)
        self.on_reset = Event(self, on_reset)
        self.on_start = Event(self, on_start)
        self.on_stop = Event(self, on_stop)

        # I/O.
        self.loop = loop
        self.output = output or create_output()
        self.input = input or StdinInput(sys.stdin)

        self.focus = Focus(layout, focussed_control)

        # List of 'extra' functions to execute before a Application.run.
        self.pre_run_callables = []

        self._is_running = False
        self._done_callback = None

        #: Quoted insert. This flag is set if we go into quoted insert mode.
        self.quoted_insert = False

        #: Vi state. (For Vi key bindings.)
        self.vi_state = ViState()

        #: The `Renderer` instance.
        # Make sure that the same stdout is used, when a custom renderer has been passed.
        self.renderer = Renderer(
            self.style,
            self.output,
            use_alternate_screen=use_alternate_screen,
            mouse_support=mouse_support)

        #: Render counter. This one is increased every time the UI is rendered.
        #: It can be used as a key for caching certain information during one
        #: rendering.
        self.render_counter = 0

        #: List of which user controls have been painted to the screen. (The
        #: visible controls.)
        self.rendered_user_controls = []

        #: When there is high CPU, postpone the renderering max x seconds.
        #: '0' means: don't postpone. '.5' means: try to draw at least twice a second.
        self.max_render_postpone_time = 0  # E.g. .5

        # Invalidate flag. When 'True', a repaint has been scheduled.
        self._invalidated = False
        self._invalidate_events = []  # Collection of 'invalidate' Event objects.

        #: The `InputProcessor` instance.
        self.input_processor = InputProcessor(_CombinedRegistry(self), weakref.ref(self))

        # Pointer to sub CLI. (In chain of CLI instances.)
        self._sub_cli = None  # None or other Application instance.

        # Trigger initialize callback.
        self.reset()

    @property
    def focussed_control(self):
        " Get the `UIControl` to has the focus. "  # This is a shortcut.
        return self.focus.focussed_control

    @focussed_control.setter
    def focussed_control(self, ui_control):
        " Set `UIControl` to receive the focus. "  # This is a shortcut.
        assert isinstance(ui_control, UIControl)
        self.focus.focussed_control = ui_control

    @property
    def focussed_window(self):
        " Return the `Window` object that is currently focussed. "
        for item in self.layout.walk():
            if isinstance(item, Window) and item.content == self.focussed_control:
                return item

    @focussed_window.setter
    def focussed_window(self, value):
        " Set the `Window` object to be currently focussed. "
        assert isinstance(value, Window)
        self.focussed_control = value.content

    @property
    def current_buffer(self):
        """
        The currently focussed :class:`~.Buffer`.

        (This returns a dummy :class:`.Buffer` when none of the actual buffers
        has the focus. In this case, it's really not practical to check for
        `None` values or catch exceptions every time.)
        """
        ui_control = self.focussed_control
        if isinstance(ui_control, BufferControl):
            return ui_control.buffer
        else:
            return Buffer(loop=self.loop)  # Dummy buffer.

    @property
    def current_search_state(self):
        """
        Return the current `SearchState`. (The one for the focussed
        `BufferControl`.)
        """
        ui_control = self.focus.focussed_control
        if isinstance(ui_control, BufferControl):
            return ui_control.search_state
        else:
            return SearchState()  # Dummy search state.  (Don't return None!)

    @property
    def terminal_title(self):
        """
        Return the current title to be displayed in the terminal.
        When this in `None`, the terminal title remains the original.
        """
        result = self.get_title()

        # Make sure that this function returns a unicode object,
        # and not a byte string.
        assert result is None or isinstance(result, six.text_type)
        return result

    def reset(self):
        """
        Reset everything, for reading the next input.
        """
        # Notice that we don't reset the buffers. (This happens just before
        # returning, and when we have multiple buffers, we clearly want the
        # content in the other buffers to remain unchanged between several
        # calls of `run`. (And the same is true for the focus stack.)

        self._exit_flag = False
        self._abort_flag = False

        self._return_value = None

        self.renderer.reset()
        self.input_processor.reset()
        self.layout.reset()
        self.vi_state.reset()

        # Trigger reset event.
        self.on_reset.fire()

    def invalidate(self):
        """
        Thread safe way of sending a repaint trigger to the input event loop.
        """
        # Never schedule a second redraw, when a previous one has not yet been
        # executed. (This should protect against other threads calling
        # 'invalidate' many times, resulting in 100% CPU.)
        if self._invalidated:
            return
        else:
            self._invalidated = True

        # Trigger event.
        self.on_invalidate.fire()

        if self.loop is not None:
            def redraw():
                self._invalidated = False
                self._redraw()

            # Call redraw in the eventloop (thread safe).
            # Usually with the high priority, in order to make the application
            # feel responsive, but this can be tuned by changing the value of
            # `max_render_postpone_time`.
            if self.max_render_postpone_time:
                _max_postpone_until = time.time() + self.max_render_postpone_time
            else:
                _max_postpone_until = None

            self.loop.call_from_executor(
                redraw, _max_postpone_until=_max_postpone_until)

    def _redraw(self):
        """
        Render the command line again. (Not thread safe!) (From other threads,
        or if unsure, use :meth:`.Application.invalidate`.)
        """
        # Only draw when no sub application was started.
        if self._is_running and self._sub_cli is None:
            # Clear the 'rendered_ui_controls' list. (The `Window` class will
            # populate this during the next rendering.)
            self.rendered_user_controls = []

            # Render
            self.render_counter += 1
            self.renderer.render(self, self.layout, is_done=self.is_done)

            # Fire render event.
            self.on_render.fire()

            self._update_invalidate_events()

    def _update_invalidate_events(self):
        """
        Make sure to attach 'invalidate' handlers to all invalidate events in
        the UI.
        """
        # Remove all the original event handlers. (Components can be removed
        # from the UI.)
        for ev in self._invalidate_events:
            ev -= self.invalidate

        # Gather all new events.
        # TODO: probably, we want a better more universal way of invalidation
        #       event propagation. (Any control should be able to invalidate
        #       itself.)
        def gather_events():
            for c in find_all_controls(self.layout):
                if isinstance(c, BufferControl):
                    yield c.buffer.on_completions_changed
                    yield c.buffer.on_suggestion_set

        self._invalidate_events = list(gather_events())

        # Attach invalidate event handler.
        for ev in self._invalidate_events:
            ev += lambda sender: self.invalidate()

    def _on_resize(self):
        """
        When the window size changes, we erase the current output and request
        again the cursor position. When the CPR answer arrives, the output is
        drawn again.
        """
        # Erase, request position (when cursor is at the start position)
        # and redraw again. -- The order is important.
        self.renderer.erase(leave_alternate_screen=False, erase_title=False)
        self.renderer.request_absolute_cursor_position()
        self._redraw()

    def _pre_run(self, pre_run=None):
        " Called during `run`. "
        if pre_run:
            pre_run()

        # Process registered "pre_run_callables" and clear list.
        for c in self.pre_run_callables:
            c()
        del self.pre_run_callables[:]

    def run(self, pre_run=None, _done=None):
        """
        Read input from the command line.
        This runs the eventloop until a return value has been set.

        :param pre_run: Callable that is called right after the reset has taken
            place. This allows custom initialisation.
        """
        assert pre_run is None or callable(pre_run)
        assert _done is None or callable(_done)

        try:
            self._is_running = True
            self._done_callback = _done or self.loop.stop

            self.on_start.fire()
            self.reset()

            # Call pre_run.
            self._pre_run(pre_run)

            # Run eventloop in raw mode.
            with self.input.raw_mode():
                self.renderer.request_absolute_cursor_position()
                self._redraw()

                self.loop.run(self.input, self.create_eventloop_callbacks())
        finally:
            # Clean up renderer. (This will leave the alternate screen, if we use
            # that.)

            # If exit/abort haven't been called set, but another exception was
            # thrown instead for some reason, make sure that we redraw in exit
            # mode.
            if not self.is_done:
                self._exit_flag = True
                self._redraw()

            self.renderer.reset()
            self.on_stop.fire()
            self._is_running = False

        # Return result.
        return self.return_value()

    try:
        # The following `run_async` function is compiled at runtime
        # because it contains syntax which is not supported on older Python
        # versions. (A 'return' inside a generator.)
        six.exec_(textwrap.dedent('''
        async def run_async(self, pre_run=None, _done=None):
            """
            Same as `run`, but this returns a coroutine.

            This is only available on Python >3.5, with asyncio.
            """
            assert pre_run is None or callable(pre_run)

            try:
                self._is_running = True
                self._done_callback = _done or self.loop.stop

                self.on_start.fire()
                self.reset()

                # Call pre_run.
                self._pre_run(pre_run)

                with self.input.raw_mode():
                    self.renderer.request_absolute_cursor_position()
                    self._redraw()

                    await self.loop.run_as_coroutine(
                            self.input, self.create_eventloop_callbacks())

                return self.return_value()
            finally:
                if not self.is_done:
                    self._exit_flag = True
                    self._redraw()

                self.renderer.reset()
                self.on_stop.fire()
                self._is_running = False
        '''))
    except SyntaxError:
        # Python2, or early versions of Python 3.
        def run_async(self, pre_run=None):
            """
            Same as `run`, but this returns a coroutine.

            This is only available on Python >3.5, with asyncio.
            """
            raise NotImplementedError

    def run_sub_application(self, application, done_callback=None,
                            _from_application_generator=False):
        """
        Run a sub :class:`~prompt_toolkit.application.Application`.

        This will suspend the main application and display the sub application
        until that one returns a value. The value is returned by calling
        `done_callback` with the result.

        The sub application will share the same I/O of the main application.
        That means, it uses the same input and output channels and it shares
        the same event loop.

        .. note:: Technically, it gets another Eventloop instance, but that is
            only a proxy to our main event loop. The reason is that calling
            'stop' --which returns the result of an application when it's
            done-- is handled differently.
        """
        assert isinstance(application, Application)
        assert done_callback is None or callable(done_callback)

        if self._sub_cli is not None:
            raise RuntimeError('Another sub application started already.')

        # Erase current application.
        if not _from_application_generator:
            self.renderer.erase()

        # Callback when the sub app is done.
        def done():
            # Redraw sub app in done state.
            # and reset the renderer. (This reset will also quit the alternate
            # screen, if the sub application used that.)
            application._redraw()
            if application.erase_when_done:
                application.renderer.erase()
            application.renderer.reset()
            application._is_running = False  # Don't render anymore.

            self._sub_cli = None

            # Restore main application.
            if not _from_application_generator:
                self.renderer.request_absolute_cursor_position()
                self._redraw()

            # Deliver result.
            if done_callback:
                done_callback(application.return_value())

        # Make sure that when the sub app is finished, it won't terminate the
        # event loop, but instead call this callback.
        application._done_callback = done

        # Allow rendering of sub app.
        application._is_running = True

        application._redraw()
        self._sub_cli = application

    def exit(self):
        """
        Set exit. When Control-D has been pressed.
        """
        on_exit = self.on_exit
        self._exit_flag = True
        self._redraw()

        if on_exit == AbortAction.RAISE_EXCEPTION:
            def eof_error():
                raise EOFError()
            self._set_return_callable(eof_error)

        elif on_exit == AbortAction.RETRY:
            self.reset()
            self.renderer.request_absolute_cursor_position()
            self.current_buffer.reset()

        elif on_exit == AbortAction.RETURN_NONE:
            self.set_return_value(None)

    def abort(self):
        """
        Set abort. When Control-C has been pressed.
        """
        on_abort = self.on_abort
        self._abort_flag = True
        self._redraw()

        if on_abort == AbortAction.RAISE_EXCEPTION:
            def keyboard_interrupt():
                raise KeyboardInterrupt()
            self._set_return_callable(keyboard_interrupt)

        elif on_abort == AbortAction.RETRY:
            self.reset()
            self.renderer.request_absolute_cursor_position()
            self.current_buffer.reset()

        elif on_abort == AbortAction.RETURN_NONE:
            self.set_return_value(None)

    def set_return_value(self, document):
        """
        Set a return value. The eventloop can retrieve the result it by calling
        `return_value`.
        """
        self._set_return_callable(lambda: document)
        self._redraw()  # Redraw in "done" state, after the return value has been set.

    def _set_return_callable(self, value):
        assert callable(value)
        self._return_value = value

        # Stop main application.
        if self._done_callback:
            self._done_callback()

    def run_in_terminal(self, func, render_cli_done=False):
        """
        Run function on the terminal above the prompt.

        What this does is first hiding the prompt, then running this callable
        (which can safely output to the terminal), and then again rendering the
        prompt which causes the output of this function to scroll above the
        prompt.

        :param func: The callable to execute.
        :param render_cli_done: When True, render the interface in the
                'Done' state first, then execute the function. If False,
                erase the interface first.

        :returns: the result of `func`.
        """
        # Draw interface in 'done' state, or erase.
        if render_cli_done:
            self._return_value = True
            self._redraw()
            self.renderer.reset()  # Make sure to disable mouse mode, etc...
        else:
            self.renderer.erase()
        self._return_value = None

        # Run system command.
        with self.input.cooked_mode():
            result = func()

        # Redraw interface again.
        self.renderer.reset()
        self.renderer.request_absolute_cursor_position()
        self._redraw()

        return result

    def run_application_generator(self, coroutine, render_cli_done=False):  # TODO: check this!
        """
        EXPERIMENTAL
        Like `run_in_terminal`, but takes a generator that can yield Application instances.

        Example:

            def f():
                yield Application1(...)
                print('...')
                yield Application2(...)
            app.run_in_terminal_async(f)

        The values which are yielded by the given coroutine are supposed to be
        `Application` instances that run in the current CLI, all other code is
        supposed to be CPU bound, so except for yielding the applications,
        there should not be any user interaction or I/O in the given function.
        """
        # Draw interface in 'done' state, or erase.
        if render_cli_done:
            self._return_value = True
            self._redraw()
            self.renderer.reset()  # Make sure to disable mouse mode, etc...
        else:
            self.renderer.erase()
        self._return_value = None

        # Loop through the generator.
        g = coroutine()
        assert isinstance(g, types.GeneratorType)

        def step_next(send_value=None):
            " Execute next step of the coroutine."
            try:
                # Run until next yield, in cooked mode.
                with self.input.cooked_mode():
                    result = g.send(send_value)
            except StopIteration:
                done()
            except:
                done()
                raise
            else:
                # Process yielded value from coroutine.
                assert isinstance(result, Application)
                self.run_sub_application(result, done_callback=step_next,
                                         _from_application_generator=True)

        def done():
            # Redraw interface again.
            self.renderer.reset()
            self.renderer.request_absolute_cursor_position()
            self._redraw()

        # Start processing coroutine.
        step_next()

    def run_system_command(self, command):  # XXX: check this!
        """
        Run system command (While hiding the prompt. When finished, all the
        output will scroll above the prompt.)

        :param command: Shell command to be executed.
        """
        def wait_for_enter():
            """
            Create a sub application to wait for the enter key press.
            This has two advantages over using 'input'/'raw_input':
            - This will share the same input/output I/O.
            - This doesn't block the event loop.
            """
            from .shortcuts import Prompt

            registry = Registry()

            @registry.add_binding(Keys.ControlJ)
            @registry.add_binding(Keys.ControlM)
            def _(event):
                event.app.set_return_value(None)

            prompt = Prompt(
                message='Press ENTER to continue...',
                extra_key_bindings=registry,
                include_default_key_bindings=False)
            self.run_sub_application(prompt.app)

        def run():
            # Try to use the same input/output file descriptors as the one,
            # used to run this application.
            try:
                input_fd = self.input.fileno()
            except AttributeError:
                input_fd = sys.stdin.fileno()
            try:
                output_fd = self.output.fileno()
            except AttributeError:
                output_fd = sys.stdout.fileno()

            # Run sub process.
            # XXX: This will still block the event loop.
            p = Popen(command, shell=True,
                      stdin=input_fd, stdout=output_fd)
            p.wait()

            # Wait for the user to press enter.
            wait_for_enter()

        self.run_in_terminal(run)

    def suspend_to_background(self, suspend_group=True):
        """
        (Not thread safe -- to be called from inside the key bindings.)
        Suspend process.

        :param suspend_group: When true, suspend the whole process group.
            (This is the default, and probably what you want.)
        """
        # Only suspend when the opperating system supports it.
        # (Not on Windows.)
        if hasattr(signal, 'SIGTSTP'):
            def run():
                # Send `SIGSTP` to own process.
                # This will cause it to suspend.

                # Usually we want the whole process group to be suspended. This
                # handles the case when input is piped from another process.
                if suspend_group:
                    os.kill(0, signal.SIGTSTP)
                else:
                    os.kill(os.getpid(), signal.SIGTSTP)

            self.run_in_terminal(run)

    def print_tokens(self, tokens, style=None):
        """
        Print a list of (Token, text) tuples to the output.
        (When the UI is running, this method has to be called through
        `run_in_terminal`, otherwise it will destroy the UI.)

        :param style: Style class to use. Defaults to the active style in the CLI.
        """
        print_tokens(self.output, tokens, style or self.style)

    @property
    def is_exiting(self):
        " ``True`` when the exit flag as been set. "
        return self._exit_flag

    @property
    def is_aborting(self):
        " ``True`` when the abort flag as been set. "
        return self._abort_flag

    @property
    def is_returning(self):
        " ``True`` when a return value has been set. "
        return self._return_value is not None

    def return_value(self):
        """
        Get the return value. Not that this method can throw an exception.
        """
        # Note that it's a method, not a property, because it can throw
        # exceptions.
        if self._return_value:
            return self._return_value()

    @property
    def is_done(self):
        return self.is_exiting or self.is_aborting or self.is_returning

    def stdout_proxy(self, raw=False):
        """
        Create an :class:`_StdoutProxy` class which can be used as a patch for
        `sys.stdout`. Writing to this proxy will make sure that the text
        appears above the prompt, and that it doesn't destroy the output from
        the renderer.

        :param raw: (`bool`) When True, vt100 terminal escape sequences are not
                    removed/escaped.
        """
        return _StdoutProxy(self, raw=raw)

    def patch_stdout_context(self, raw=False, patch_stdout=True, patch_stderr=True):
        """
        Return a context manager that will replace ``sys.stdout`` with a proxy
        that makes sure that all printed text will appear above the prompt, and
        that it doesn't destroy the output from the renderer.

        :param patch_stdout: Replace `sys.stdout`.
        :param patch_stderr: Replace `sys.stderr`.
        """
        return _PatchStdoutContext(
            self.stdout_proxy(raw=raw),
            patch_stdout=patch_stdout, patch_stderr=patch_stderr)

    def create_eventloop_callbacks(self):
        return _InterfaceEventLoopCallbacks(self)


class _InterfaceEventLoopCallbacks(EventLoopCallbacks):
    """
    Callbacks on the :class:`.Application` object, to which an
    eventloop can talk.
    """
    def __init__(self, app):
        assert isinstance(app, Application)
        self.app = app

    @property
    def _active_app(self):
        " Return the active `Application`. "
        app = self.app

        # If there is a sub CLI. That one is always active.
        while app._sub_cli:
            app = app._sub_cli

        return app

    def terminal_size_changed(self):
        " Report terminal size change. This will trigger a redraw. "
        self._active_app._on_resize()

    def input_timeout(self):
        app = self._active_app
        app.on_input_timeout.fire()

    def feed_key(self, key_press):
        " Feed a key press to the Application. "
        assert isinstance(key_press, KeyPress)
        app = self._active_app

        # Feed the key and redraw.
        # (When the CLI is in 'done' state, it should return to the event loop
        # as soon as possible. Ignore all key presses beyond this point.)
        if not app.is_done:
            app.input_processor.feed(key_press)
            app.input_processor.process_keys()


class _PatchStdoutContext(object):
    def __init__(self, new_stdout, patch_stdout=True, patch_stderr=True):
        self.new_stdout = new_stdout
        self.patch_stdout = patch_stdout
        self.patch_stderr = patch_stderr

    def __enter__(self):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

        if self.patch_stdout:
            sys.stdout = self.new_stdout
        if self.patch_stderr:
            sys.stderr = self.new_stdout

    def __exit__(self, *a, **kw):
        if self.patch_stdout:
            sys.stdout = self.original_stdout

        if self.patch_stderr:
            sys.stderr = self.original_stderr


class _StdoutProxy(object):
    """
    Proxy for stdout, as returned by
    :class:`Application.stdout_proxy`.
    """
    def __init__(self, app, raw=False):
        assert isinstance(app, Application)
        assert isinstance(raw, bool)

        self._lock = threading.RLock()
        self._cli = app
        self._raw = raw
        self._buffer = []

        self.errors = sys.__stdout__.errors
        self.encoding = sys.__stdout__.encoding

    def _do(self, func):
        if self._cli._is_running:
            run_in_terminal = functools.partial(self._cli.run_in_terminal, func)
            self._cli.loop.call_from_executor(run_in_terminal)
        else:
            func()

    def _write(self, data):
        """
        Note: print()-statements cause to multiple write calls.
              (write('line') and write('\n')). Of course we don't want to call
              `run_in_terminal` for every individual call, because that's too
              expensive, and as long as the newline hasn't been written, the
              text itself is again overwritter by the rendering of the input
              command line. Therefor, we have a little buffer which holds the
              text until a newline is written to stdout.
        """
        if '\n' in data:
            # When there is a newline in the data, write everything before the
            # newline, including the newline itself.
            before, after = data.rsplit('\n', 1)
            to_write = self._buffer + [before, '\n']
            self._buffer = [after]

            def run():
                for s in to_write:
                    if self._raw:
                        self._cli.output.write_raw(s)
                    else:
                        self._cli.output.write(s)
            self._do(run)
        else:
            # Otherwise, cache in buffer.
            self._buffer.append(data)

    def write(self, data):
        with self._lock:
            self._write(data)

    def _flush(self):
        def run():
            for s in self._buffer:
                if self._raw:
                    self._cli.output.write_raw(s)
                else:
                    self._cli.output.write(s)
            self._buffer = []
            self._cli.output.flush()
        self._do(run)

    def flush(self):
        """
        Flush buffered output.
        """
        with self._lock:
            self._flush()


class _CombinedRegistry(BaseRegistry):
    """
    The `Registry` of key bindings for a `Application`.
    This merges the global key bindings with the one of the current user
    control.
    """
    def __init__(self, app):
        self.app = app
        self._cache = SimpleCache()

    def _create_registry(self, current_control, visible_controls):
        """
        Create a `Registry` object that merges the `Registry` from the
        `UIControl` with the other user controls and the global registry.
        """
        # Collect key bindings of other visible user controls.
        key_bindings = [c.get_key_bindings(self.app) for c in visible_controls]
        key_bindings = [b.registry for b in key_bindings if b is not None]

        others_registry = MergedRegistry(
            [self.app.key_bindings_registry] + key_bindings)

        ui_key_bindings = current_control.get_key_bindings(self.app)

        if ui_key_bindings is None:
            # No bindings for this user control. Just return everything else.
            return others_registry
        else:
            # Bindings for this user control found.
            # Keep the 'modal' parameter into account.
            @Condition
            def is_not_modal(app):
                return not ui_key_bindings.modal

            return MergedRegistry([
                ConditionalRegistry(others_registry, is_not_modal),
                ui_key_bindings.registry,
            ])

    @property
    def _registry(self):
        current_control = self.app.focussed_control
        visible_controls = self.app.rendered_user_controls
        visible_controls = list(find_all_controls(self.app.layout))#self.app.rendered_user_controls
        key = current_control, frozenset(visible_controls)

        return self._cache.get(
            key, lambda: self._create_registry(current_control, visible_controls))

    def get_bindings_for_keys(self, keys):
        return self._registry.get_bindings_for_keys(keys)

    def get_bindings_starting_with_keys(self, keys):
        return self._registry.get_bindings_starting_with_keys(keys)
