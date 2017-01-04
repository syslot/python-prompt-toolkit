"""
Shortcuts for retrieving input from the user.

If you are using this library for retrieving some input from the user (as a
pure Python replacement for GNU readline), probably for 90% of the use cases,
the :func:`.prompt` function is all you need. It's the easiest shortcut which
does a lot of the underlying work like creating a
:class:`~prompt_toolkit.interface.CommandLineInterface` instance for you.

When is this not sufficient:
    - When you want to have more complicated layouts (maybe with sidebars or
      multiple toolbars. Or visibility of certain user interface controls
      according to some conditions.)
    - When you wish to have multiple input buffers. (If you would create an
      editor like a Vi clone.)
    - Something else that requires more customization than what is possible
      with the parameters of `prompt`.

In that case, study the code in this file and build your own
`CommandLineInterface` instance. It's not too complicated.
"""
from __future__ import unicode_literals

#from .layout.lexers import PygmentsLexer
from .auto_suggest import DynamicAutoSuggest
from .buffer import Buffer, AcceptAction
from .cache import memoized
from .clipboard import DynamicClipboard, InMemoryClipboard
from .completion import DynamicCompleter
from .document import Document
from .enums import DEFAULT_BUFFER, SEARCH_BUFFER, EditingMode, SYSTEM_BUFFER
from .eventloop.base import EventLoop
from .eventloop.defaults import create_event_loop, create_asyncio_event_loop
from .filters import IsDone, HasFocus, RendererHeightIsKnown, to_simple_filter, Condition
from .history import InMemoryHistory, DynamicHistory
from .input import StdinInput
from .interface import CommandLineInterface, Application, AbortAction
from .key_binding.defaults import load_key_bindings_for_prompt
from .key_binding.registry import Registry, DynamicRegistry
from .keys import Keys
from .layout import Window, HSplit, FloatContainer, Float
from .layout.containers import ConditionalContainer
from .layout.controls import BufferControl, TokenListControl
from .layout.dimension import LayoutDimension
from .layout.lexers import DynamicLexer
from .layout.margins import PromptMargin, ConditionalMargin
from .layout.menus import CompletionsMenu, MultiColumnCompletionsMenu
from .layout.processors import PasswordProcessor, ConditionalProcessor, AppendAutoSuggestion, HighlightSearchProcessor, HighlightSelectionProcessor, DisplayMultipleCursors, BeforeInput, ReverseSearchProcessor, ShowArg
from .layout.screen import Char
from .layout.toolbars import ValidationToolbar, SystemToolbar, ArgToolbar, SearchToolbar
from .layout.utils import explode_tokens
from .output.defaults import create_output
from .renderer import print_tokens as renderer_print_tokens
from .styles import DEFAULT_STYLE, Style, DynamicStyle
from .token import Token
from .utils import DummyContext
from .validation import DynamicValidator

from six import text_type, exec_

import textwrap
import threading
import time
import sys

__all__ = (
    'prompt',
    'prompt_async',
    'confirm',
    'print_tokens',
    'clear',
)


def _split_multiline_prompt(get_prompt_tokens):
    """
    Take a `get_prompt_tokens` function and return three new functions instead.
    One that tells whether this prompt consists of multiple lines; one that
    returns the tokens to be shown on the lines above the input; and another
    one with the tokens to be shown at the first line of the input.
    """
    def has_before_tokens(cli):
        for token, char in get_prompt_tokens(cli):
            if '\n' in char:
                return True
        return False

    def before(cli):
        result = []
        found_nl = False
        for token, char in reversed(explode_tokens(get_prompt_tokens(cli))):
            if found_nl:
                result.insert(0, (token, char))
            elif char == '\n':
                found_nl = True
        return result

    def first_input_line(cli):
        result = []
        for token, char in reversed(explode_tokens(get_prompt_tokens(cli))):
            if char == '\n':
                break
            else:
                result.insert(0, (token, char))
        return result

    return has_before_tokens, before, first_input_line


class _RPrompt(Window):
    " The prompt that is displayed on the right side of the Window. "
    def __init__(self, get_tokens):
        super(_RPrompt, self).__init__(
            TokenListControl(get_tokens, align_right=True))


"""
    Create a :class:`.Container` instance for a prompt.

    :param message: Text to be used as prompt.
    :param lexer: :class:`~prompt_toolkit.layout.lexers.Lexer` to be used for
        the highlighting.
    :param is_password: `bool` or :class:`~prompt_toolkit.filters.CLIFilter`.
        When True, display input as '*'.
    :param reserve_space_for_menu: Space to be reserved for the menu. When >0,
        make sure that a minimal height is allocated in the terminal, in order
        to display the completion menu.
    :param get_prompt_tokens: An optional callable that returns the tokens to be
        shown in the menu. (To be used instead of a `message`.)
    :param get_continuation_tokens: An optional callable that takes a
        CommandLineInterface and width as input and returns a list of (Token,
        text) tuples to be used for the continuation.
    :param get_bottom_toolbar_tokens: An optional callable that returns the
        tokens for a toolbar at the bottom.
    :param display_completions_in_columns: `bool` or
        :class:`~prompt_toolkit.filters.CLIFilter`. Display the completions in
        multiple columns.
    :param multiline: `bool` or :class:`~prompt_toolkit.filters.CLIFilter`.
        When True, prefer a layout that is more adapted for multiline input.
        Text after newlines is automatically indented, and search/arg input is
        shown below the input, instead of replacing the prompt.
    :param wrap_lines: `bool` or :class:`~prompt_toolkit.filters.CLIFilter`.
        When True (the default), automatically wrap long lines instead of
        scrolling horizontally.
    """

def _true(value):
    " Test whether `value` is True. In case of a SimpleFilter, call it. "
    return to_simple_filter(value)()


class Prompt(object):
    """
    Build the Prompt application, which can be used as a GNU Readline replacement.

    :param message: Text to be shown before the prompt.
    :param mulitiline: Allow multiline input. Pressing enter will insert a
                       newline. (This requires Meta+Enter to accept the input.)
    :param wrap_lines: `bool` or :class:`~prompt_toolkit.filters.CLIFilter`.
        When True (the default), automatically wrap long lines instead of
        scrolling horizontally.
    :param is_password: Show asterisks instead of the actual typed characters.
    :param editing_mode: ``EditingMode.VI`` or ``EditingMode.EMACS``.
    :param vi_mode: `bool`, if True, Identical to ``editing_mode=EditingMode.VI``.
    :param complete_while_typing: `bool` or
        :class:`~prompt_toolkit.filters.SimpleFilter`. Enable autocompletion
        while typing.
    :param enable_history_search: `bool` or
        :class:`~prompt_toolkit.filters.SimpleFilter`. Enable up-arrow parting
        string matching.
    :param lexer: :class:`~prompt_toolkit.layout.lexers.Lexer` to be used for
        the syntax highlighting.
    :param validator: :class:`~prompt_toolkit.validation.Validator` instance
        for input validation.
    :param completer: :class:`~prompt_toolkit.completion.Completer` instance
        for input completion.
    :param reserve_space_for_menu: Space to be reserved for displaying the menu.
        (0 means that no space needs to be reserved.)
    :param auto_suggest: :class:`~prompt_toolkit.auto_suggest.AutoSuggest`
        instance for input suggestions.
    :param style: :class:`.Style` instance for the color scheme.
    :param enable_system_bindings: `bool` or
        :class:`~prompt_toolkit.filters.CLIFilter`. Pressing Meta+'!' will show
        a system prompt.
    :param enable_open_in_editor: `bool` or
        :class:`~prompt_toolkit.filters.CLIFilter`. Pressing 'v' in Vi mode or
        C-X C-E in emacs mode will open an external editor.
    :param history: :class:`~prompt_toolkit.history.History` instance.
    :param clipboard: :class:`~prompt_toolkit.clipboard.base.Clipboard` instance.
        (e.g. :class:`~prompt_toolkit.clipboard.in_memory.InMemoryClipboard`)
    :param get_bottom_toolbar_tokens: Optional callable which takes a
        :class:`~prompt_toolkit.interface.CommandLineInterface` and returns a
        list of tokens for the bottom toolbar.
    :param display_completions_in_columns: `bool` or
        :class:`~prompt_toolkit.filters.CLIFilter`. Display the completions in
        multiple columns.
    :param get_title: Callable that returns the title to be displayed in the
        terminal.
    :param mouse_support: `bool` or :class:`~prompt_toolkit.filters.CLIFilter`
        to enable mouse support.
    :param default: The default text to be shown in the input buffer. (This can
        be edited by the user.)
    """
    _fields = (
        'message', 'lexer', 'completer', 'is_password',
        'key_bindings_registry', 'is_password', 'get_bottom_toolbar_tokens',
        'style', 'get_prompt_tokens', 'get_rprompt_tokens', 'multiline',
        'get_continuation_tokens', 'wrap_lines', 'history',
        'enable_history_search', 'complete_while_typing', 'on_abort',
        'on_exit', 'display_completions_in_columns', 'mouse_support',
        'auto_suggest', 'clipboard', 'get_title', 'validator')

    def __init__(self,
            message='',
            loop=None,
            multiline=False,
            wrap_lines=True,
            is_password=False,
            vi_mode=False,
            editing_mode=EditingMode.EMACS,
            complete_while_typing=True,
            enable_history_search=False,
            lexer=None,
            enable_system_bindings=False,
            enable_open_in_editor=False,
            validator=None,
            completer=None,
            reserve_space_for_menu=8,
            auto_suggest=None,
            style=None,
            history=None,
            clipboard=None,
            get_prompt_tokens=None,
            get_continuation_tokens=None,
            get_rprompt_tokens=None,
            get_bottom_toolbar_tokens=None,
            display_completions_in_columns=False,
            get_title=None,
            mouse_support=False,
            extra_input_processors=None,
            key_bindings_registry=None,
            on_abort=AbortAction.RAISE_EXCEPTION,
            on_exit=AbortAction.RAISE_EXCEPTION,
            erase_when_done=False,

            input=None,
            output=None):
        assert isinstance(message, text_type), 'Please provide a unicode string.'
        assert loop is None or isinstance(loop, EventLoop)
        assert get_bottom_toolbar_tokens is None or callable(get_bottom_toolbar_tokens)
        assert get_prompt_tokens is None or callable(get_prompt_tokens)
        assert get_rprompt_tokens is None or callable(get_rprompt_tokens)
        assert not (message and get_prompt_tokens)
        assert style is None or isinstance(style, Style)

        # Defaults.
        loop = loop or create_event_loop()

        output = output or create_output()  # XXX: true_color=true_color))
        input = input or StdinInput(sys.stdin)

        history = history or InMemoryHistory()
        clipboard = clipboard or InMemoryClipboard()

        # Default key bindings.
        if key_bindings_registry is None:
            key_bindings_registry = load_key_bindings_for_prompt(
                enable_system_bindings=enable_system_bindings,
                enable_open_in_editor=enable_open_in_editor)

        # Ensure backwards-compatibility, when `vi_mode` is passed.
        if vi_mode:
            editing_mode = EditingMode.VI

        # Store all settings in this class.
        self.loop = loop
        self.input = input
        self.output = output

        # Store all settings in this class.
        for name in self._fields:
            if name not in ('on_abort', 'on_exit'):
                value = locals()[name]
                setattr(self, name, value)

        self.application, self._default_buffer, self.cli = self._create_application(
            editing_mode, on_abort, on_exit, erase_when_done)

    def _create_application(self, editing_mode, on_abort, on_exit, erase_when_done):
        # Create functions that will dynamically split the prompt. (If we have
        # a multiline prompt.)
        has_before_tokens, get_prompt_tokens_1, get_prompt_tokens_2 = \
            _split_multiline_prompt(self._get_prompt_tokens)

        @memoized(20)
        def dyncond(attr_name):
            """
            Dynamically take this setting from this 'Prompt' class.
            `attr_name` represents an attribute name of this class. Its value
            can either be a boolean or a `SimpleFilter`.

            This returns something that can be used as either a `SimpleFilter`
            or `CLIFilter`.
            """
            @Condition
            def dynamic_condition(*a):
                value = getattr(self, attr_name)
                return to_simple_filter(value)()
            return dynamic_condition

        # Create buffers list.
        default_buffer = Buffer(
            name=DEFAULT_BUFFER,
            loop=self.loop,
                # Make sure that complete_while_typing is disabled when
                # enable_history_search is enabled. (First convert to
                # SimpleFilter, to avoid doing bitwise operations on bool
                # objects.)
            complete_while_typing=Condition(lambda:
                _true(self.complete_while_typing) and not
                _true(self.enable_history_search)),
            enable_history_search=dyncond('enable_history_search'),
            is_multiline=dyncond('multiline'),
            validator=DynamicValidator(lambda: self.validator),
            completer=DynamicCompleter(lambda: self.completer),
            history=DynamicHistory(lambda: self.history),
            auto_suggest=DynamicAutoSuggest(lambda: self.auto_suggest),
            accept_action=AcceptAction.RETURN_DOCUMENT)
#            initial_document=Document(default))

        search_buffer = Buffer(name=SEARCH_BUFFER, loop=self.loop)
        system_buffer = Buffer(name=SYSTEM_BUFFER, loop=self.loop)

        # Create processors list.
        input_processors = [
            ConditionalProcessor(
                # By default, only highlight search when the search
                # input has the focus. (Note that this doesn't mean
                # there is no search: the Vi 'n' binding for instance
                # still allows to jump to the next match in
                # navigation mode.)
                HighlightSearchProcessor(preview_search=True),
                HasFocus(search_buffer)),
            HighlightSelectionProcessor(),
            ConditionalProcessor(AppendAutoSuggestion(), HasFocus(default_buffer) & ~IsDone()),
            ConditionalProcessor(PasswordProcessor(), dyncond('is_password')),
            DisplayMultipleCursors(),
        ]

#        if extra_input_processors:  # XXX: make dynamic!
#            input_processors.extend(extra_input_processors)

        # For single line mode, show the prompt before the input.
        input_processors.extend([
            ConditionalProcessor(BeforeInput(get_prompt_tokens_2), ~dyncond('multiline')),
            ConditionalProcessor(ShowArg(), ~dyncond('multiline')),
        ])

        # Create bottom toolbars.
        bottom_toolbar = ConditionalContainer(
            Window(TokenListControl(lambda cli: self.get_bottom_toolbar_tokens(cli),
                                    default_char=Char(' ', Token.Toolbar)),
                                    height=LayoutDimension.exact(1)),
            filter=~IsDone() & RendererHeightIsKnown() &
                    Condition(lambda cli: self.get_bottom_toolbar_tokens is not None))

        search_toolbar = SearchToolbar(search_buffer)
        search_buffer_control = BufferControl(
            buffer=search_buffer,
            input_processors=[
                ReverseSearchProcessor(),
            ])

        def get_search_buffer_control():  # TODO: if 'multiline' changes while asking for input. automatically focus the other control while searching.
            " Return the UIControl to be focussed when searching start. "
            if to_simple_filter(self.multiline)():
                return search_toolbar.control
            else:
                return search_buffer_control

        default_buffer_control = BufferControl(
            buffer=default_buffer,
            get_search_buffer_control=get_search_buffer_control,
            input_processors=input_processors,
            lexer=DynamicLexer(lambda: self.lexer),
            # Enable preview_search, we want to have immediate feedback
            # in reverse-i-search mode.
            preview_search=True)

        # Build the layout.
        layout = HSplit([
            # The main input, with completion menus floating on top of it.
            FloatContainer(
                HSplit([
                    ConditionalContainer(
                        Window(
                            TokenListControl(get_prompt_tokens_1),
                            dont_extend_height=True),
                        Condition(has_before_tokens)
                    ),
                    ConditionalContainer(
                        Window(default_buffer_control,
                            get_height=self._get_default_buffer_control_height,
                            left_margins=[
                                # In multiline mode, use the window margin to display
                                # the prompt and continuation tokens.
                                ConditionalMargin(
                                    PromptMargin(get_prompt_tokens_2, self._get_continuation_tokens),
                                    filter=dyncond('multiline'),
                                )
                            ],
                            wrap_lines=dyncond('wrap_lines'),
                        ),
                        Condition(lambda cli:
                            cli.focussed_control != search_buffer_control),
                    ),
                    ConditionalContainer(
                        Window(search_buffer_control),
                        Condition(lambda cli:
                            cli.focussed_control == search_buffer_control),
                    ),
                ]),
                [
                    # Completion menus.
                    Float(xcursor=True,
                          ycursor=True,
                          content=CompletionsMenu(
                              max_height=16,
                              scroll_offset=1,
                              extra_filter=HasFocus(default_buffer) &
                                  ~dyncond('display_completions_in_columns'),
                    )),
                    Float(xcursor=True,
                          ycursor=True,
                          content=MultiColumnCompletionsMenu(
                              show_meta=True,
                              extra_filter=HasFocus(default_buffer) &
                                  dyncond('display_completions_in_columns'),
                    )),
                    # The right prompt.
                    Float(right=0, top=0, hide_when_covering_content=True,
                          content=_RPrompt(self._get_rprompt_tokens)),
                ]
            ),
            ValidationToolbar(),
            SystemToolbar(system_buffer),

            # In multiline mode, we use two toolbars for 'arg' and 'search'.
            ConditionalContainer(ArgToolbar(), dyncond('multiline')),
            ConditionalContainer(search_toolbar, dyncond('multiline')),
            bottom_toolbar,
        ])

        # Create application
        application = Application(
            layout=layout,
            focussed_control=default_buffer_control,
            style=DynamicStyle(lambda: self.style or DEFAULT_STYLE),
            clipboard=DynamicClipboard(lambda: self.clipboard),
            key_bindings_registry=DynamicRegistry(lambda: self.key_bindings_registry),
            get_title=self._get_title,
            mouse_support=dyncond('mouse_support'),
            editing_mode=editing_mode,
            erase_when_done=erase_when_done,
            reverse_vi_search_direction=True,
            on_abort=on_abort,
            on_exit=on_exit)

        # Create CommandLineInterface.
        cli = CommandLineInterface(
            application=application,
            eventloop=self.loop,
            input=self.input,
            output=self.output)

        return application, default_buffer, cli

    def prompt(self, message=None, 
            patch_stdout=False, true_color=False, refresh_interval=0, vi_mode=None,
            # When any of these arguments are passed, this value is overwritten for the current prompt.
            lexer=None, completer=None, is_password=None,
            key_bindings_registry=None, get_bottom_toolbar_tokens=None,
            style=None, get_prompt_tokens=None, get_rprompt_tokens=None, multiline=None,
            get_continuation_tokens=None, wrap_lines=None, history=None,
            enable_history_search=None, on_abort=None, on_exit=None,
            complete_while_typing=None, display_completions_in_columns=None,
            auto_suggest=None, validator=None, clipboard=None,
            mouse_support=None, get_title=None):

        # Backup original settings.
        backup = dict((name, getattr(self, name)) for name in self._fields)

        # Take settings from 'prompt'-arguments.
        for name in self._fields:
            value = locals()[name]
            if value is not None:
                setattr(self, name, value)

        if vi_mode:
            self.editing_mode = EditingMode.VI

        try:
            return _run_application(self.cli,
                patch_stdout=patch_stdout,
                #return_asyncio_coroutine=return_asyncio_coroutine,
                true_color=true_color,
                refresh_interval=refresh_interval,
                loop=self.loop)
        finally:
            # Restore original settings.
            for name in self._fields:
                setattr(self, name, backup[name])

    @property
    def on_abort(self):
        return self.application.on_abort

    @on_abort.setter
    def on_abort(self, value):
        self.application.on_abort = value

    @property
    def on_exit(self):
        return self.application.on_exit

    @on_exit.setter
    def on_exit(self, value):
        self.application.on_exit = value

    @property
    def editing_mode(self):
        return self.application.editing_mode

    @editing_mode.setter
    def editing_mode(self, value):
        self.application.editing_mode = value

    def _get_default_buffer_control_height(self, cli):
        # If there is an autocompletion menu to be shown, make sure that our
        # layout has at least a minimal height in order to display it.
        reserve_space_for_menu = (self.reserve_space_for_menu if self.completer is not None else 0)

        if reserve_space_for_menu and not cli.is_done:
            buff = self._default_buffer

            # Reserve the space, either when there are completions, or when
            # `complete_while_typing` is true and we expect completions very
            # soon.
            if buff.complete_while_typing() or buff.complete_state is not None:
                return LayoutDimension(min=reserve_space_for_menu)

        return LayoutDimension()

    def _get_prompt_tokens(self, cli):
        if self.get_prompt_tokens is None:
            return [(Token.Prompt, self.message or '')]
        else:
            return self.get_prompt_tokens(cli)

    def _get_rprompt_tokens(self, cli):
        if self.get_rprompt_tokens:
            return self.get_rprompt_tokens(cli)
        return []

    def _get_continuation_tokens(self, cli, width):
        if self.get_continuation_tokens:
            return self.get_continuation_tokens(cli, width)
        return []

    def _get_title(self):
        if self.get_title is None:
            return
        else:
            return self.get_title()

    def prompt_async(self): pass


    def close(self):
        self.loop.close()


# The default prompt function.
_prompt = None
def prompt(*a, **kw):
    global _prompt
    if _prompt is None:
        _prompt = Prompt()
    return _prompt.prompt(*a, **kw)
prompt.__doc__ = Prompt.prompt.__doc__

def _old_prompt(message='', **kwargs):
    """
    Get input from the user and return it.

    This is a wrapper around a lot of ``prompt_toolkit`` functionality and can
    be a replacement for `raw_input`. (or GNU readline.)

    If you want to keep your history across several calls, create one
    :class:`~prompt_toolkit.history.History` instance and pass it every time.

    This function accepts many keyword arguments. Except for the following,
    they are a proxy to the arguments of :func:`.create_prompt_application`.

    :param patch_stdout: Replace ``sys.stdout`` by a proxy that ensures that
            print statements from other threads won't destroy the prompt. (They
            will be printed above the prompt instead.)
    :param return_asyncio_coroutine: When True, return a asyncio coroutine. (Python >3.3)
    :param true_color: When True, use 24bit colors instead of 256 colors.
    :param refresh_interval: (number; in seconds) When given, refresh the UI
        every so many seconds.
    """
    patch_stdout = kwargs.pop('patch_stdout', False)
    return_asyncio_coroutine = kwargs.pop('return_asyncio_coroutine', False)
    true_color = kwargs.pop('true_color', False)
    refresh_interval = kwargs.pop('refresh_interval', 0)
    eventloop = kwargs.pop('eventloop', None)

    if return_asyncio_coroutine:
        eventloop = create_asyncio_eventloop()
    else:
        eventloop = eventloop or create_eventloop()

    application = create_prompt_application(message, eventloop, **kwargs)



def _run_application(cli,
        patch_stdout=False, return_asyncio_coroutine=False,
        true_color=False, refresh_interval=0, loop=None):
    """
    Run a prompt toolkit application.

    :param patch_stdout: Replace ``sys.stdout`` by a proxy that ensures that
            print statements from other threads won't destroy the prompt. (They
            will be printed above the prompt instead.)
    :param return_asyncio_coroutine: When True, return a asyncio coroutine. (Python >3.3)
    :param true_color: When True, use 24bit colors instead of 256 colors.
    :param refresh_interval: (number; in seconds) When given, refresh the UI
        every so many seconds.
    """
    assert isinstance(loop, EventLoop)

    # Set up refresh interval.
    if refresh_interval:
        done = [False]
        def start_refresh_loop(cli):
            def run():
                while not done[0]:
                    time.sleep(refresh_interval)
                    cli.request_redraw()
            t = threading.Thread(target=run)
            t.daemon = True
            t.start()

        def stop_refresh_loop(cli):
            done[0] = True

        cli.on_start += start_refresh_loop
        cli.on_stop += stop_refresh_loop

    # Replace stdout.
    patch_context = cli.patch_stdout_context(raw=True) if patch_stdout else DummyContext()

    # Read input and return it.
    if return_asyncio_coroutine:
        # Create an asyncio coroutine and call it.
        exec_context = {'patch_context': patch_context, 'cli': cli,
                        'Document': Document}
        exec_(textwrap.dedent('''
        def prompt_coro():
            # Inline import, because it slows down startup when asyncio is not
            # needed.
            import asyncio

            @asyncio.coroutine
            def run():
                with patch_context:
                    result = yield from cli.run_async()

                if isinstance(result, Document):  # Backwards-compatibility.
                    return result.text
                return result
            return run()
        '''), exec_context)

        return exec_context['prompt_coro']()
    else:
        with patch_context:
            result = cli.run()

        if isinstance(result, Document):  # Backwards-compatibility.
            return result.text
        return result


def prompt_async(message='', **kwargs):
    """
    Similar to :func:`.prompt`, but return an asyncio coroutine instead.
    """
    kwargs['return_asyncio_coroutine'] = True
    return prompt(message, **kwargs)


def create_confirm_application(message):
    """
    Create a confirmation `Application` that returns True/False.
    """
    registry = Registry()

    @registry.add_binding('y')
    @registry.add_binding('Y')
    def _(event):
        event.cli.buffers[DEFAULT_BUFFER].text = 'y'
        event.cli.set_return_value(True)

    @registry.add_binding('n')
    @registry.add_binding('N')
    @registry.add_binding(Keys.ControlC)
    def _(event):
        event.cli.buffers[DEFAULT_BUFFER].text = 'n'
        event.cli.set_return_value(False)

    return create_prompt_application(message, key_bindings_registry=registry)


def confirm(message='Confirm (y or n) '):
    """
    Display a confirmation prompt.
    """
    assert isinstance(message, text_type)

    app = create_confirm_application(message)
    return _run_application(app)


def print_tokens(tokens, style=None, true_color=False, file=None):
    """
    Print a list of (Token, text) tuples in the given style to the output.
    E.g.::

        style = style_from_dict({
            Token.Hello: '#ff0066',
            Token.World: '#884444 italic',
        })
        tokens = [
            (Token.Hello, 'Hello'),
            (Token.World, 'World'),
        ]
        print_tokens(tokens, style=style)

    :param tokens: List of ``(Token, text)`` tuples.
    :param style: :class:`.Style` instance for the color scheme.
    :param true_color: When True, use 24bit colors instead of 256 colors.
    :param file: The output file. This can be `sys.stdout` or `sys.stderr`.
    """
    if style is None:
        style = DEFAULT_STYLE
    assert isinstance(style, Style)

    output = create_output(true_color=true_color, stdout=file)
    renderer_print_tokens(output, tokens, style)


def clear():
    """
    Clear the screen.
    """
    out = create_output()
    out.erase_screen()
    out.cursor_goto(0, 0)
    out.flush()
