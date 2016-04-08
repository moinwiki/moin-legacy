# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - User Forms

    Copyright (c) 2001, 2002 by J�rgen Hermann <jh@web.de>
    All rights reserved, see COPYING for details.

    $Id: wikiform.py,v 1.8 2003/11/09 21:00:52 thomaswaldmann Exp $
"""

# Imports
import cgi, string
from MoinMoin import wikiutil
from MoinMoin.Page import Page


#############################################################################
### Form definitions
#############################################################################

_required_attributes = ['type', 'name', 'label']

def parseDefinition(request, fielddef, fieldlist):
    """ Parse a form field definition and return the HTML markup for it
    """
    _ = request.getText

    row = '<tr><td nowrap valign="top">&nbsp;<b>%s</b>&nbsp;</td><td>%s</td></tr>\n'
    fields, msg = wikiutil.parseAttributes(request, fielddef)

    if not msg:
        for required in _required_attributes:
            if not fields.has_key(required):
                msg = _('Required attribute "%(attrname)s" missing')  % {
                    'attrname': required}
                break

    if msg:
        # create visible error
        result = row % (msg, fielddef)
    elif fields['type'] == '"caption"':
        # create a centered, bold italic caption
        result = '<tr><td colspan="2" align="center"><i><b>%s</b></I></td></tr>\n' % (
            fields['label'][1:-1])
    else:
        # for submit buttons, use `label` as the value
        if fields['type'] == '"submit"':
            fields['value'] = fields['label']
            fields['label'] = ''

        # make sure user cannot use a system name
        fields['name'] = '"form_' + fields['name'][1:]
        fieldlist.append(fields['name'][1:-1])

        wrapper = ('<input', '>\n')
        if fields['type'] == '"textarea"':
            wrapper = ('<textarea', '></textarea>\n')

        result = wrapper[0]
        for key, val in fields.items():
            if key == 'label': continue
            result = '%s %s=%s' % (result, key, val)
        result = result + wrapper[1]

        #result = result + cgi.escape(`fields`)

        if fields['type'] == '"submit"':
            result = '<tr><td colspan="2" align="center">%s</td></tr>\n' % result
        else:
            result = row % (fields['label'][1:-1], result)

    return result


def _get_formvalues(form):
    result = {}
    for key in form.keys():
        if key[:5] != 'form_': continue

        val = string.replace(form.getvalue(key, "<empty>"), '\r', '')
        if type(val) is type([]):
            # Multiple username fields specified
            val = string.join(val, "|")

        result[key] = val

    return result


def do_formtest(pagename, request):
    """ Test a user defined form.
    """
    _ = request.getText

    msg = _('Submitted form data:') + '<ul>\n'
    for key, val in _get_formvalues(request.form).items():
        msg = msg + '<li><em>%s</em> = %s</li>\n' % (
            string.upper(key), repr(cgi.escape(val))
        )
    msg = msg + '</ul>\n'

    Page(pagename).send_page(request, msg=msg)
