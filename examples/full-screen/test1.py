#!/usr/bin/env python
"""
"""
from __future__ import unicode_literals

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.interface import CommandLineInterface
from prompt_toolkit.key_binding.registry import Registry
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.containers import VSplit, HSplit, Window, FloatContainer, Float
from prompt_toolkit.layout.controls import BufferControl, FillControl, TokenListControl, UIControl, UIContent, UIControlKeyBindings
from prompt_toolkit.layout.lexers import PygmentsLexer
from prompt_toolkit.layout.dimension import LayoutDimension as D
from prompt_toolkit.layout.screen import Char
from prompt_toolkit.shortcuts import create_eventloop
from prompt_toolkit.token import Token
from prompt_toolkit.styles import style_from_dict, style_from_pygments
from prompt_toolkit.search_state import SearchState
from prompt_toolkit.layout.processors import HighlightSearchProcessor

from pygments.lexers import HtmlLexer, CssLexer
from pygments.styles import get_style_by_name

class CustomControl(UIControl):
    def __init__(self, symbol):
        self.symbol = symbol
        self.text = ''

    def create_content(self, cli, width, height):
        if cli.focussed_control == self:
            token = Token.Focussed
        else:
            token = Token

        def create_line(num):
            if num == 0:
                return [(token, self.text)]
            return [(token, self.symbol * width)]
        return UIContent(create_line, line_count=height)

    def get_key_bindings(self, cli):
        registry = Registry()

        @registry.add_binding('t')
        def _(event):
            self.text += 't'

        @registry.add_binding(Keys.Backspace)
        def _(event):
            self.text = self.text[:-1]

        return UIControlKeyBindings(registry)

loop = create_eventloop()

c1 = CustomControl('x')
c2 = CustomControl('o')

search = Buffer(eventloop=loop)
b = Buffer(eventloop=loop,is_multiline=True)

input_processors = [
    HighlightSearchProcessor(preview_search=True),
]

c5 = BufferControl(buffer=search)
c3 = BufferControl(buffer=b, input_processors=input_processors, lexer=PygmentsLexer(HtmlLexer), search_buffer_control=c5)
c4 = BufferControl(buffer=b, input_processors=input_processors, lexer=PygmentsLexer(CssLexer), search_buffer_control=c5)

layout = VSplit([
    Window(content=c1),
    Window(content=c2),
    Window(content=c3),
    Window(content=c4),
    Window(content=c5),
])


registry = load_key_bindings(enable_search=True)  # Start with the `KeyBindingManager`.


@registry.add_binding(Keys.ControlC, eager=True)
@registry.add_binding(Keys.ControlQ, eager=True)
def _(event):
    event.cli.set_return_value(None)

@registry.add_binding(Keys.Tab, eager=True)
def _(event):
    " Change focus. "
    cli = event.cli
    controls = [c1, c2, c3]
    new_index = (controls.index(cli.focussed_control) + 1) % len(controls)
    cli.focussed_control = controls[new_index]


style = {
    Token.Focussed: 'bg:#0000ff #ffff00',
    #Token: 'bg:#000000 #ffffff',
}


application = Application(
    layout=layout,
    key_bindings_registry=registry,
    style=style_from_pygments(get_style_by_name('default'), style),

    # Let's add mouse support!
    mouse_support=True,

    # Using an alternate screen buffer means as much as: "run full screen".
    # It switches the terminal to an alternate screen.
    use_alternate_screen=True)


# 4. Run the application
#    -------------------

def run():

    try:
        cli = CommandLineInterface(application=application, eventloop=loop)
        cli.run()
    finally:
        loop.close()

if __name__ == '__main__':
    run()
