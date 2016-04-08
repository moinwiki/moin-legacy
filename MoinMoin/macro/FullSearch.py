# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - FullSearch Macro

    Copyright (c) 2000, 2001, 2002 by J�rgen Hermann <jh@web.de>
    All rights reserved, see COPYING for details.

    [[FullSearch]]
        displays a search dialog, as it always did

    [[FullSearch()]]
        does the same as clicking on the page title, only that
        the result is embedded into the page (note the "()" after
        the macro name, which is an empty argument list)

    [[FullSearch('HelpContents')]]
        embeds a search result into a page, as if you entered
        "HelpContents" into the search dialog

    $Id: FullSearch.py,v 1.10 2003/11/09 21:01:02 thomaswaldmann Exp $
"""

# Imports
import re, urllib
from MoinMoin import config, user, wikiutil

_args_re_pattern = r'((?P<hquote>[\'"])(?P<htext>.+?)(?P=hquote))|'


def execute(macro, text, args_re=re.compile(_args_re_pattern)):
    _ = macro.request.getText

    # if no args given, invoke "classic" behavior
    if text is None:
        return macro._m_search("fullsearch")

    # parse and check arguments
    args = args_re.match(text)
    if not args:
        return '<p><strong class="error">Invalid FullSearch arguments "%s"!</strong></p>' % (text,)

    needle = args.group('htext')
    literal = 0
    if not needle:
        # empty args means to duplicate the "title click" search (backlinks to page),
        # especially useful on "Category" type pages
        needle = macro.formatter.page.page_name
        literal = 1

    # do the search
    pagecount, hits = wikiutil.searchPages(needle, literal=literal, context=0)

    # generate the result
    result = macro.formatter.number_list(1)
    for (count, pagename, dummy) in hits:
        # CNC:2003-05-30
        if not macro.request.user.may.read(pagename):
            continue
        result = result + macro.formatter.listitem(1)
        result = result + wikiutil.link_tag('%s?action=highlight&value=%s' %
            (wikiutil.quoteWikiname(pagename), urllib.quote_plus(needle)),
            pagename)
        result = result + ' . . . . ' + `count` + [
            _(' match'),
            _(' matches')][count != 1]
        result = result + macro.formatter.listitem(0)
    result = result + macro.formatter.number_list(0)

    return result
