import time, urllib
from MoinMoin.Page import Page
from MoinMoin import config, wikiutil, search
from MoinMoin.formatter.text_html import Formatter
from MoinMoin.util import MoinMoinNoFooter

def execute(pagename, request, fieldname='value', titlesearch=0):
    _ = request.getText
    start = time.clock()

    # Get titlesearch. It either a hidden field in a search macro form
    # using '0' or '1', or a submit button in the search box, in which
    # case its a localized 'Titles' string.
    try:
        titlesearch = int(request.form.get('titlesearch', [0])[0])
    except ValueError:
        # "Titles" button was clicked in the standard search box.
        titlesearch = 1

    # context is relevant only for full search
    if titlesearch:        
        context = 0      
    else:
        context = int(request.form.get('context', [0])[0])        
    
    # Get other form parameters
    needle = request.form.get(fieldname, [''])[0]
    case = int(request.form.get('case', [0])[0])
    regex = int(request.form.get('regex', [0])[0]) # no interface currently

    max_context = 1 # only show first `max_context` contexts XXX still unused

    # check for sensible search term
    striped = needle.strip()
    if len(striped) <= 1:
        err = _('Please use a more selective search term instead '
                'of {{{"%s"}}}') % needle
        # send http headers
        request.http_headers()
        Page(request, pagename).send_page(request, msg=err) 
        return

    # search the pages
    query = search.QueryParser(case=case, regex=regex,
                               titlesearch=titlesearch).parse_query(needle)
    results = search.searchPages(request, query)

    # directly show a single hit
    # XXX won't work with attachment search
    # improve if we have one...
    if len(results.hits) == 1:
        page = Page(request, results.hits[0].page_name)
        # TODO: remove escape=0 in 1.4
        url = page.url(request, querystr={'highlight': query.highlight_re()},
                       escape=0)
        request.http_redirect(url)
        raise MoinMoinNoFooter

    # send http headers
    request.http_headers()

    # This action generate data using the user language
    request.setContentLanguage(request.lang)

    # Setup for type of search
    if titlesearch:
        title = _('Title Search: "%s"')
        results.sortByPagename()
    else:
        title = _('Full Text Search: "%s"')
        results.sortByWeight() 

    wikiutil.send_title(request, title % needle, form=request.form,
                        pagename=pagename)
    
    # Start content (important for RTL support)
    formatter = Formatter(request)
    request.write(formatter.startContent("content"))

    # First search stats
    request.write(results.stats(request, formatter))

    # Then search results
    info = not titlesearch
    if context:
        output = results.pageListWithContext(request, formatter, info=info,
                                             context=context)
    else:
        output = results.pageList(request, formatter, info=info)        
    request.write(output)

    # End content and send footer
    request.write(formatter.endContent())
    wikiutil.send_footer(request, pagename, editable=0, showactions=0,
                         form=request.form)
