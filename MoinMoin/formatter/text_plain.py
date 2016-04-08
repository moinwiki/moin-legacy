"""
    MoinMoin - "text/plain" Formatter

    Copyright (c) 2000 by J�rgen Hermann <jh@web.de>
    All rights reserved, see COPYING for details.

    $Id: text_plain.py,v 1.2 2000/12/01 00:12:30 jhermann Exp $
"""

# Imports
import sys
from base import FormatterBase


#############################################################################
### Plain Text Formatter
#############################################################################

class Formatter(FormatterBase):
    """
        Send text data.
    """

    def __init__(self):
        FormatterBase.__init__(self)

    def startDocument(self, pagename):
        line = "*" * (len(pagename)+2) + '\n'
        return "<pre>%s %s \n%s" % (line, pagename, line)

    def endDocument(self):
        return '\n'

    def pagelink(self, pagename):
        return ">>%s<<" % (pagename,)

    def url(self, url, text=None, css=None):
        if text is None:
            return url
        else:
            return '%s [%s]' % (text, url)

    def text(self, text):
        return text

    def rule(self, size=0):
        size = min(size, 10)
        ch = "---~=*+#####"[size]
        return (ch * 79) + '\n'

    def strong(self, on):
        return '*'

    def emphasis(self, on):
        return '/'

    def number_list(self, on, type=None, start=None):
        # !!! remember list state
        return ''

    def bullet_list(self, on):
        # !!! remember list state
        return ''

    def listitem(self, on):
        # !!! return number for ordered lists
        return ' * '

    def code(self, text):
        return '"' + text + '"'

    def preformatted(self, on):
        snip = '---%<'
        snip = snip + ('-' * (78 - len(snip)))
        if on:
            return '\n' + snip
        else:
            return snip + '\n'

    def paragraph(self):
        return '\n'

    def linebreak(self):
        return '\n'

    def heading(self, depth, title):
        return '\n%s\n%s\n%s\n\n' % ('=' * len(title), title, '=' * len(title))

    def table(self, on):
        return ''
