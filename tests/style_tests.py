from __future__ import unicode_literals
from prompt_toolkit.styles import Attrs, style_from_dict
from prompt_toolkit.token import Token

import unittest


class StyleFromDictTest(unittest.TestCase):
    def test_style_from_dict(self):
        style = style_from_dict({
            Token.A: '#ff0000 bold underline italic',
            Token.B: 'bg:#00ff00 blink reverse',
        })

        expected = Attrs(color='ff0000', bgcolor=None, bold=True,
                         underline=True, italic=True, blink=False, reverse=False)
        assert style.get_attrs_for_token(Token.A) == expected

        expected = Attrs(color=None, bgcolor='00ff00', bold=False,
                         underline=False, italic=False, blink=True, reverse=True)
        assert style.get_attrs_for_token(Token.B) == expected

    def test_style_inheritance(self):
        style = style_from_dict({
            Token: '#ff0000',
            Token.A.B.C: 'bold',
            Token.A.B.C.D: 'red',
            Token.A.B.C.D.E: 'noinherit blink'
        })

        expected = Attrs(color='ff0000', bgcolor=None, bold=True,
                         underline=False, italic=False, blink=False, reverse=False)
        assert style.get_attrs_for_token(Token.A.B.C) == expected

        expected = Attrs(color='red', bgcolor=None, bold=True,
                         underline=False, italic=False, blink=False, reverse=False)
        assert style.get_attrs_for_token(Token.A.B.C.D) == expected

        expected = Attrs(color=None, bgcolor=None, bold=False,
                         underline=False, italic=False, blink=True, reverse=False)
        assert style.get_attrs_for_token(Token.A.B.C.D.E) == expected
