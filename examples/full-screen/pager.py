#!/usr/bin/env python
"""
"""
from __future__ import unicode_literals

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.eventloop.defaults import create_event_loop
from prompt_toolkit.interface import CommandLineInterface
from prompt_toolkit.key_bindings.defaults import load_key_bindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, TokenListControl
from prompt_toolkit.layout.dimension import LayoutDimension as D
from prompt_toolkit.layout.lexers import PygmentsLexer
from prompt_toolkit.layout.processors import HighlightSearchProcessor
from prompt_toolkit.layout.screen import Char
from prompt_toolkit.styles import PygmentsStyle
from prompt_toolkit.token import Token

from pygments.lexers import PythonLexer

loop = create_event_loop()

def get_statusbar_tokens(cli):
    return [
        (Token.Status, './pager.py %s' % (default_buffer.document.cursor_position_row + 1)),
    ]


default_buffer = Buffer(name=DEFAULT_BUFFER, loop=loop, is_multiline=True)

# Load source in default buffer.
with open('./pager.py', 'rb') as f:
    default_buffer.text = f.read().decode('utf-8')


buffer_control = BufferControl(
    buffer=default_buffer,
    lexer=PygmentsLexer(PythonLexer),
    input_processors=[HighlightSearchProcessor(preview_search=True)])


layout = HSplit([
    # The top toolbar.
    Window(content=TokenListControl(
        get_statusbar_tokens, default_char=Char(token=Token.Status)),
        height=D.exact(1)),

    # The main content.
    Window(content=buffer_control),

    #SearchToolbar(),
])


# Key bindings.
registry = load_key_bindings(enable_search=True, enable_extra_page_navigation=True)

@registry.add_binding(Keys.ControlC)
@registry.add_binding('q')
def _(event):
    " Quit. "
    event.cli.set_return_value(None)


style = PygmentsStyle.from_defaults({
    Token.Status: 'bg:#444444 #ffffff',
})

# create application.
application = Application(
    layout=layout,
    key_bindings_registry=registry,

    mouse_support=True,
    style=style,
    focussed_control=buffer_control,

    # Using an alternate screen buffer means as much as: "run full screen".
    # It switches the terminal to an alternate screen.
    use_alternate_screen=True)


def run():
    try:
        cli = CommandLineInterface(application=application, eventloop=loop)
        cli.run(reset_current_buffer=False)

    finally:
        loop.close()

if __name__ == '__main__':
    run()
