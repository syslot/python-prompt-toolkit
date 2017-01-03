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
from .buffer import Buffer, AcceptAction
from .document import Document
from .enums import DEFAULT_BUFFER, SEARCH_BUFFER, EditingMode, SYSTEM_BUFFER
from .eventloop.base import EventLoop
from .eventloop.defaults import create_event_loop, create_asyncio_event_loop
from .filters import IsDone, HasFocus, RendererHeightIsKnown, to_simple_filter, to_cli_filter, Condition
from .history import InMemoryHistory
from .interface import CommandLineInterface, Application, AbortAction
from .key_binding.defaults import load_key_bindings_for_prompt
from .key_binding.registry import Registry
from .keys import Keys
from .layout import Window, HSplit, FloatContainer, Float
from .layout.containers import ConditionalContainer
from .layout.controls import BufferControl, TokenListControl
from .layout.dimension import LayoutDimension
from .layout.margins import PromptMargin, ConditionalMargin
from .layout.menus import CompletionsMenu, MultiColumnCompletionsMenu
from .layout.processors import PasswordProcessor, ConditionalProcessor, AppendAutoSuggestion, HighlightSearchProcessor, HighlightSelectionProcessor, DisplayMultipleCursors, BeforeInput, ReverseSearchProcessor, ShowArg
#from .layout.prompt import DefaultPrompt
from .layout.screen import Char
from .layout.lexers import DynamicLexer
from .layout.toolbars import ValidationToolbar, SystemToolbar, ArgToolbar, SearchToolbar
from .layout.utils import explode_tokens
from .output.defaults import create_output
from .renderer import print_tokens as renderer_print_tokens
from .styles import DEFAULT_STYLE, Style, DynamicStyle
from .token import Token
from .utils import DummyContext
from .completion import DynamicCompleter

from six import text_type, exec_

import textwrap
import threading
import time

__all__ = (
    'prompt',
    'prompt_async',
    'create_confirm_application',
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
    def __init__(self, get_tokens=None):
        get_tokens = get_tokens or (lambda cli: [])

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


class Prompt(object):
    """
    Create an :class:`~Application` instance for a prompt.

    (It is meant to cover 90% of the prompt use cases, where no extreme
    customization is required. For more complex input, it is required to create
    a custom :class:`~Application` instance.)

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
            accept_action=AcceptAction.RETURN_DOCUMENT,
            erase_when_done=False,
            default=''):
        assert isinstance(message, text_type), 'Please provide a unicode string.'
        assert loop is None or isinstance(loop, EventLoop)
        assert get_bottom_toolbar_tokens is None or callable(get_bottom_toolbar_tokens)
        assert get_prompt_tokens is None or callable(get_prompt_tokens)
        assert get_rprompt_tokens is None or callable(get_rprompt_tokens)
        assert not (message and get_prompt_tokens)
        assert style is None or isinstance(style, Style)

        # Eventloop.
        loop = loop or create_event_loop()

        display_completions_in_columns = to_cli_filter(display_completions_in_columns)
        multiline = to_simple_filter(multiline)

        history = history or InMemoryHistory()
        initial_document=Document(default)

        # ** Key bindings. **
        if key_bindings_registry is None:
            key_bindings_registry = load_key_bindings_for_prompt(
                enable_system_bindings=enable_system_bindings,
                enable_open_in_editor=enable_open_in_editor)

        # Ensure backwards-compatibility, when `vi_mode` is passed.
        if vi_mode:
            editing_mode = EditingMode.VI

        # Make sure that complete_while_typing is disabled when enable_history_search
        # is enabled. (First convert to SimpleFilter, to avoid doing bitwise operations
        # on bool objects.)
        complete_while_typing = to_simple_filter(complete_while_typing)
        enable_history_search = to_simple_filter(enable_history_search)
        multiline = to_simple_filter(multiline)

        complete_while_typing = complete_while_typing & ~enable_history_search

        if style is None:
            style = DEFAULT_STYLE

        multiline2 = Condition(lambda cli: multiline())

        has_before_tokens, get_prompt_tokens_1, get_prompt_tokens_2 = \
            _split_multiline_prompt(self._get_prompt_tokens)

        # Create buffers list.
        default_buffer = Buffer(
            name=DEFAULT_BUFFER,
            eventloop=loop,
            enable_history_search=enable_history_search,
            complete_while_typing=complete_while_typing,
            is_multiline=multiline,
            history=(history or InMemoryHistory()),
            validator=validator,
            completer=DynamicCompleter(lambda: self.completer),
            auto_suggest=auto_suggest,
            accept_action=accept_action,
            initial_document=initial_document)

        search_buffer = Buffer(
            name=SEARCH_BUFFER,
            eventloop=loop)

        system_buffer = Buffer(
            name=SYSTEM_BUFFER,
            eventloop=loop)

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
            ConditionalProcessor(PasswordProcessor(), is_password),
            DisplayMultipleCursors(),
        ]

        if extra_input_processors:
            input_processors.extend(extra_input_processors)

        # For single line mode, show the prompt before the input.
        input_processors.extend([
            ConditionalProcessor(BeforeInput(get_prompt_tokens_2), ~multiline2),
            ConditionalProcessor(ShowArg(), ~multiline2),
        ])

        # Create bottom toolbar.
        if get_bottom_toolbar_tokens:
            toolbars = [ConditionalContainer(
                Window(TokenListControl(get_bottom_toolbar_tokens,
                                        default_char=Char(' ', Token.Toolbar)),
                                        height=LayoutDimension.exact(1)),
                filter=~IsDone() & RendererHeightIsKnown())]
        else:
            toolbars = []

        search_toolbar = SearchToolbar(search_buffer)
        search_buffer_control = BufferControl(
            buffer=search_buffer,
            input_processors=[
                ReverseSearchProcessor(),
            ])

        def get_search_buffer_control():
            if multiline():
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

        # Create and return Container instance.
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
                                    PromptMargin(get_prompt_tokens_2, get_continuation_tokens),
                                    filter=multiline2
                                )
                            ],
                            wrap_lines=wrap_lines,
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
                                           ~display_completions_in_columns)),
                    Float(xcursor=True,
                          ycursor=True,
                          content=MultiColumnCompletionsMenu(
                              extra_filter=HasFocus(default_buffer) &
                                           display_completions_in_columns,
                              show_meta=True)),

                    # The right prompt.
                    Float(right=0, top=0, hide_when_covering_content=True,
                          content=_RPrompt(get_rprompt_tokens)),
                ]
            ),
            ValidationToolbar(),
            SystemToolbar(system_buffer),

            # In multiline mode, we use two toolbars for 'arg' and 'search'.
            ConditionalContainer(ArgToolbar(), multiline2),
            ConditionalContainer(search_toolbar, multiline2),
        ] + toolbars)

        # Create application
        self.application = Application(
            layout=layout,
            focussed_control=default_buffer_control,
            style=DynamicStyle(lambda: self.style),
            clipboard=clipboard,
            key_bindings_registry=key_bindings_registry,
            get_title=get_title,
            mouse_support=mouse_support,
            editing_mode=editing_mode,
            erase_when_done=erase_when_done,
            reverse_vi_search_direction=True,
            on_abort=on_abort,
            on_exit=on_exit)

        self._default_buffer =  default_buffer
        self.loop = loop
        self.reserve_space_for_menu = reserve_space_for_menu
        self.message = message
        self.get_prompt_tokens = get_prompt_tokens
        self.style = style
        self.lexer = lexer
        self.completer = completer

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
            return [(Token.Prompt, self.message)]
        else:
            return self.get_prompt_tokens(cli)

    def prompt(self, message, patch_stdout=False, true_color=False, refresh_interval=0,
            # When any of these arguments are passed, this value is overwritten for the current prompt.
            lexer=None, completer=None):
        self.message = message

        if lexer is not None: self.lexer = lexer
        if completer is not None: self.completer = completer

        try:
            return _run_application(self.application,
                patch_stdout=patch_stdout,
                #return_asyncio_coroutine=return_asyncio_coroutine,
                true_color=true_color,
                refresh_interval=refresh_interval,
                loop=self.loop)
        finally:
            # TODO: restore original settings.
            pass

    def prompt_async(self): pass


    def close(self):
        self.loop.close()


# The default prompt function.
_prompt = Prompt()
prompt = _prompt.prompt  # XXX: TODO: only create the Prompt() instance the first time that this function is used. We should not do I/O during import!

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



def _run_application(
        application, patch_stdout=False, return_asyncio_coroutine=False,
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
    assert isinstance(application, Application)
    assert isinstance(loop, EventLoop)

    # Create CommandLineInterface.
    cli = CommandLineInterface(
        application=application,
        eventloop=loop,
        output=create_output(true_color=true_color))

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
