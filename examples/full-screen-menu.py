#!/usr/bin/env python
"""
"""
from __future__ import unicode_literals

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.interface import CommandLineInterface
from prompt_toolkit.key_binding.manager import KeyBindingManager
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.containers import VSplit, HSplit, Window, FloatContainer, Float
from prompt_toolkit.layout.controls import BufferControl, FillControl, TokenListControl
from prompt_toolkit.layout.dimension import LayoutDimension as D
from prompt_toolkit.layout.screen import Char
from prompt_toolkit.shortcuts import create_eventloop
from prompt_toolkit.token import Token
from prompt_toolkit.styles import style_from_dict


layout = VSplit([
    Window(content=BufferControl(buffer_name=DEFAULT_BUFFER)),
    Window(width=D.exact(1),
           content=FillControl('|', token=Token.Line)),
    Window(content=BufferControl(buffer_name='RESULT')),
])

def get_menu_tokens(cli):
    return [
        (Token.MenuBar, ' '),
        (Token.Menu, 'File'),
        (Token.MenuBar, ' Edit '),
        (Token.MenuBar, ' Info '),
    ]

def file_menu():
    def get_tokens(cli):
        return [
            (Token.Menu, ' Open \n'),
            (Token.Menu, ' Save \n'),
            (Token.Menu, ' Save as '),
        ]

    return Window(TokenListControl(get_tokens, default_char=Char(token=Token.Menu)))


def dialog():
    def get_title_tokens(cli):
        return [
            (Token.DialogTitle, ' About '),
        ]

    def get_body_tokens(cli):
        return [
            (Token.DialogBody, ' Example application\n'),
            (Token.DialogBody, ' demonstration a rich console UI.')
        ]

    return HSplit([
        Window(TokenListControl(get_title_tokens, default_char=Char(token=Token.DialogTitle))),
        Window(TokenListControl(get_body_tokens, default_char=Char(token=Token.DialogBody))),
    ])

def with_shadow(container):
    return


layout = FloatContainer(
    content=HSplit([
        # The titlebar.
        Window(height=D.exact(1),
               content=TokenListControl(get_menu_tokens,
                    default_char=Char(token=Token.MenuBar))),

        # Horizontal separator.
        Window(height=D.exact(1),
               content=FillControl('-', token=Token.Line)),

        # The 'body', like defined above.
        layout,
    ]),
    floats=[
        Float(top=1, left=1, content=file_menu()),
        Float(content=dialog()),
    ]
)

manager = KeyBindingManager()  # Start with the `KeyBindingManager`.


@manager.registry.add_binding(Keys.ControlC, eager=True)
@manager.registry.add_binding(Keys.ControlQ, eager=True)
def _(event):
    event.cli.set_return_value(None)


buffers={
    DEFAULT_BUFFER: Buffer(is_multiline=True),
    'RESULT': Buffer(is_multiline=True),
}

def default_buffer_changed(cli):
    buffers['RESULT'].text = buffers[DEFAULT_BUFFER].text[::-1]


buffers[DEFAULT_BUFFER].on_text_changed += default_buffer_changed

style = {
        Token.MenuBar: 'bg:#0000ff #ffff00',
        Token.Menu: 'bg:#008888 #ffff00',
        Token.DialogTitle: 'bg:#444444 #ffffff',
        Token.DialogBody: 'bg:#888888',
}


application = Application(
    layout=layout,
    buffers=buffers,
    key_bindings_registry=manager.registry,
    style=style_from_dict(style),

    # Let's add mouse support!
    mouse_support=True,

    # Using an alternate screen buffer means as much as: "run full screen".
    # It switches the terminal to an alternate screen.
    use_alternate_screen=True)


# 4. Run the application
#    -------------------


    eventloop = create_eventloop()

    try:
        cli = CommandLineInterface(application=application, eventloop=eventloop)

        cli.run()

    finally:
        eventloop.close()

if __name__ == '__main__':
    run()


a = Textfield()
a.text

"""


from prompt_toolkit.fullscreen import MenuContainer

TextField(),

MenuContainer(
    menu=MenuList([
        MenuItem(name='File', items=[
            MenuItem(name='Open', shortcut=Key.CtrlO)
            MenuItem(name='Save', shortcut=Key.CtrlS, enabled=False),
        ]),
        MenuItem(name='Edit', items=[
            MenuItem(name='Cut', shortcut=Key.CtrlO),
            MenuItem(name='Copy', shortcut=Key.CtrlC),
        ]),
    ],
    VSplit([
        BufferWidget(),
        TextField(),
        TextField(),
        TextField(),
    ])
)

Proposal for better full screen application support
===================================================

Problem
-------

Currently, the architecture of prompt-toolkit is mainly focussed around the
design of REPLs. (Readline replacements.) Creating a rich full screen console
UI is difficult for several reasons.

- The definition of key bindings is completely independent from the definition
  of the user controls. A key binding is usually active if a 'Buffer' object
  has the focus.

- Defining a 'Buffer' also happens independent of the creation of a user control.

- The focus is defined in terms of a 'Buffer' that receives the key strokes,
  this is indepedent of the UI control. This also means that if the same
  'Buffer' is displayed in several UI controls. (E.g. as happens in Pyvim),
  there is no clear way to say which control should actually display the
  cursor.

We want this to be together. If a new "widget" is added to the UI, it should be
possible to contain this in one component that knows about the required
'Buffer' objects, the key bindings and the visualisation.

Solution
--------

The 'Container' class should be extended with the following methods. (Which can
be proxied to the UIControl if we want.):
    get_focussed_buffer()  # Returns a Buffer() object.
    get_key_bindings()  # Returns a Registry() object.

The set of active key bindings is defined as the global set of key bindings +
the key bindings from the specific UI control.

This also means that an InputProcessor should have a method get_buffers(), if
it can display other buffers, like the search buffer, in front.

What happens if we start searching?
- In some way, we should deliver the focus to the search buffer.
  We should keep in mind that not all widgets will share the same search buffer.
  Options:
  * Each buffer should have a function `get_search_buffer`. That returns the
    Buffer (by name/instance?) that has to be focussed when searching.
  * focus(buffer_name) should focus the widget that displays this buffer.


Widget generates:
    - collection of Buffer objects.
    - collection of key bindings.

What happens if we press '/' to start searching.
We want to focus a search buffer and display that.
How do I transfer the focus to the other widget? When it's displayed in another
widget. (Maybe it's the same container that has the focus, but it returns
another get_focussed_buffer. Then while drawing, the other will )
Maybe every widget should have a get_buffers() method with returns a
dictionary. If a certain buffer is focussed, and it appears in this container,
then that widget is focussed.



Use 'leave mark' to mark menu positions. Floats can then be attached to such a 'mark'.

"""





