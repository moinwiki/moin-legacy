"""
    MoinMoin - "text/html" Formatter

    Copyright (c) 2000 by J�rgen Hermann <jh@web.de>
    All rights reserved, see COPYING for details.

    $Id: text_html.py,v 1.4 2000/12/01 00:12:30 jhermann Exp $
"""

# Imports
import cgi, sys
from base import FormatterBase
from MoinMoin import wikiutil
from MoinMoin.Page import Page


#############################################################################
### HTML Formatter
#############################################################################

class Formatter(FormatterBase):
    """
        Send HTML data.
    """

    def __init__(self):
        FormatterBase.__init__(self)

    def pagelink(self, pagename):
        return Page(pagename).link_to()

    def url(self, url, text=None, css=None):
        if text is None: text = url

        if wikiutil.isPicture(url):
            return '<img src="%s" border="0">' % (url,)
        else:
            str = '<a'
            if css: str = '%s class="%s"' % (str, css)
            str = '%s href="%s">%s</a>' % (str, cgi.escape(url, 1), text)
            return str

    def text(self, text):
        return cgi.escape(text)

    def rule(self, size=0):
        if size:
            return '<hr size="%d">\n' % (size,)
        else:
            return '<hr>\n'

    def strong(self, on):
        return ['<b>', '</b>'][not on]

    def emphasis(self, on):
        return ['<em>', '</em>'][not on]

    def number_list(self, on, type=None, start=None):
        if not on: return '</ol>'

        result = '<ol'
        if type: result = result + ' type="%s"' % (type,)
        if start: result = result + ' start="%d"' % (start,)
        
        return result + '>'

    def bullet_list(self, on):
        return ['<ul>', '</ul>'][not on]

    def listitem(self, on):
        return ['<li>', '</li>'][not on]

    def code(self, text):
        return '<tt class="wiki">%s</tt>' % (cgi.escape(text),)

    def preformatted(self, on):
        return ['<pre class="code">', '</pre>'][not on]

    def paragraph(self):
        return '<p>'

    def linebreak(self):
        return '\n'

    def heading(self, depth, title):
        return '<H%d>%s</H%d>\n' % (depth, title, depth)

    def table(self, on):
        return ['<table class="wiki" border="1" cellspacing="0" cellpadding="3">', '</table>'][not on]

    def anchordef(self, name):
        return '<a name="%s">' % name

    def anchorlink(self, name, text):
        return '<a href="#%s">%s</a>' % (name, text)
