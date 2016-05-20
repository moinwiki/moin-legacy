# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - Wiki Utility Functions

    @copyright: 2000 - 2004 by J�rgen Hermann <jh@web.de>
    @license: GNU GPL, see COPYING for details.
"""
    
import os, re, difflib

from MoinMoin import util, version, config
from MoinMoin.util import pysupport


# Exceptions
class InvalidFileNameError(Exception):
    """ Called when we find an invalid file name """ 
    pass

# constants for page names
PARENT_PREFIX = "../"
PARENT_PREFIX_LEN = len(PARENT_PREFIX)
CHILD_PREFIX = "/"
CHILD_PREFIX_LEN = len(CHILD_PREFIX)

#############################################################################
### Getting data from user/Sending data to user
#############################################################################

def decodeWindowsPath(text):
    """ Decode Windows path names correctly. This is needed because many CGI
    servers follow the RFC recommendation and re-encode the path_info variable
    according to the file system semantics.
    
    @param text: the text to decode, string
    @rtype: unicode
    @return: decoded text
    """

    import locale
    import codecs
    cur_charset = locale.getdefaultlocale()[1]
    try:
        return unicode(text, 'utf-8')
    except UnicodeError:
        try:
            return unicode(text, cur_charset, 'replace')
        except LookupError:
            return unicode(text, 'iso-8859-1', 'replace')
    
def decodeUnknownInput(text):
    """ Decode unknown input, like text attachments

    First we try utf-8 because it has special format, and it will decode
    only utf-8 files. Then we try config.charset, then iso-8859-1 using
    'replace'. We will never raise an exception, but may return junk
    data.

    WARNING: Use this function only for data that you view, not for data
    that you save in the wiki.

    @param text: the text to decode, string
    @rtype: unicode
    @return: decoded text (maybe wrong)
    """
    # Shortcut for unicode input
    if isinstance(text, unicode):
        return text
    
    try:
        return unicode(text, 'utf-8')
    except UnicodeError:
        if config.charset not in ['utf-8', 'iso-8859-1']:
            try:
                return unicode(text, config.charset)
            except UnicodeError:
                pass
        return unicode(text, 'iso-8859-1', 'replace')
        

def decodeUserInput(s, charsets=[config.charset]):
    """
    Decodes input from the user.
    
    @param s: the string to unquote
    @param charset: the charset to assume the string is in
    @rtype: unicode
    @return: the unquoted string as unicode
    """
    for charset in charsets:
        try:
            return s.decode(charset)
        except UnicodeError:
            pass
    raise UnicodeError('The string "%s" cannot be decoded.' % s)


# FIXME: better name would be quoteURL, as this is useful for any
# string, not only wiki names.
def quoteWikinameURL(pagename, charset=config.charset):
    """
    Return a simple encoding of filename in plain ascii.

    Warning: will raise UnicodeError if pagename can not be encoded
    using charset. The default config.charset, 'utf-8', can encode any
    character.

    FIXME: isn't it better to use here urllib.quote instead of duplicating
    the code? If we use cgi, urllib is already available. if we do
    duplicate the code from urllib, why we don't use also fast_quote as
    urllib does?

    FIXME: If we don't use urllib.quote, maybe this is cleaner and faster
    to use re, in the same way quoteWikinameFS works.
    
    @param pagename: the original pagename, maybe containing non-ascii chars
    @rtype: string
    @return: the quoted filename, all special chars encoded in (xx)
    """
    safe = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/+-_,\'*'
    pagename = pagename.replace(u' ', u'_') # " " -> "_"
    filename = pagename.encode(charset)
    
    res = list(filename)
    c = None
    for i in range(len(res)):
        prev = c
        c = res[i]
        if c not in safe:
            # FIXME: why are we doing this?
            if c == '.' and prev == '/':
                res[i] = '(%02x)' % ord(c)
            else:
                res[i] = '%%%02x' % ord(c)
    return ''.join(res)


def escape(s, quote=0):
    """ Escape possible html tags
    
    Replace special characters '&', '<' and '>' by SGML entities.
    (taken from cgi.escape so we don't have to include that, even if we
    don't use cgi at all)

    FIXME: should return string or unicode?
    
    @param s: (unicode) string to escape
    @param quote: bool, should transform '\"' to '&quot;'
    @rtype: (unicode) string
    @return: escaped version of s
    """
    if not isinstance(s, (str, unicode)):
        s = str(s)

    # Must first replace &
    s = s.replace("&", "&amp;")

    # Then other...
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    if quote:
        s = s.replace('"', "&quot;")
    return s


########################################################################
### Storage
########################################################################

# FIXME: These functions might be moved to storage module, when we have
# one. Then they will be called transparently whenever a page is saved.

# Precompiled patterns for file name [un]quoting
UNSAFE = re.compile(r'[^a-zA-Z0-9_]+')
QUOTED = re.compile(r'\(([a-fA-F0-9]+)\)')


# FIXME: better name would be quoteWikiname
def quoteWikinameFS(wikiname, charset=config.charset):
    """ Return file system representation of a Unicode WikiName.
            
    Warning: will raise UnicodeError if wikiname can not be encoded using
    charset. The default value of config.charset, 'utf-8' can encode any
    character.
        
    @param wikiname: Unicode string possibly containing non-ascii characters
    @param charset: charset to encode string
    @rtype: string
    @return: quoted name, safe for any file system
    """
    wikiname = wikiname.replace(u' ', u'_') # " " -> "_"
    filename = wikiname.encode(charset)
    
    quoted = []    
    location = 0
    for needle in UNSAFE.finditer(filename):
        # append leading safe stuff
        quoted.append(filename[location:needle.start()])
        location = needle.end()                    
        # Quote and append unsafe stuff           
        quoted.append('(')
        for character in needle.group():
            quoted.append('%02x' % ord(character))
        quoted.append(')')
    
    # append rest of string
    quoted.append(filename[location:])    
    return ''.join(quoted)


# FIXME: better name would be unquoteFilename
def unquoteWikiname(filename, charsets=[config.charset]):
    """ Return Unicode WikiName from quoted file name.
    
    We raise an InvalidFileNameError if we find an invalid name, so the
    wiki could alarm the admin or suggest the user to rename a page.
    Invalid file names should never happen in normal use, but are rather
    cheap to find. 
    
    This function should be used only to unquote file names, not page
    names we receive from the user. These are handled in request by
    urllib.unquote, decodePagename and normalizePagename.
    
    Todo: search clients of unquoteWikiname and check for exceptions. 

    @param filename: string using charset and possibly quoted parts
    @param charset: charset used by string
    @rtype: Unicode String
    @return: WikiName
    """
    ### Temporary fix start ###
    # From some places we get called with Unicode strings
    if isinstance(filename, type(u'')):
        filename = filename.encode(config.charset)
    ### Temporary fix end ###
        
    parts = []    
    start = 0
    for needle in QUOTED.finditer(filename):  
        # append leading unquoted stuff
        parts.append(filename[start:needle.start()])
        start = needle.end()            
        # Append quoted stuff
        group =  needle.group(1)
        # Filter invalid filenames
        if (len(group) % 2 != 0):
            raise InvalidFileNameError(filename) 
        try:
            for i in range(0, len(group), 2):
                byte = group[i:i+2]
                character = chr(int(byte, 16))
                parts.append(character)
        except ValueError:
            # byte not in hex, e.g 'xy'
            raise InvalidFileNameError(filename)
    
    # append rest of string
    if start == 0:
        wikiname = filename
    else:
        parts.append(filename[start:len(filename)])   
        wikiname = ''.join(parts)

    # This looks wrong, because at this stage "()" can be both errors
    # like open "(" without close ")", or unquoted valid characters in
    # the file name. FIXME: check this.
    # Filter invalid filenames. Any left (xx) must be invalid
    #if '(' in wikiname or ')' in wikiname:
    #    raise InvalidFileNameError(filename)
    
    wikiname = decodeUserInput(wikiname, charsets)
    wikiname = wikiname.replace(u'_', u' ') # "_" -> " "
    return wikiname

# time scaling
def timestamp2version(ts):
    """ Convert UNIX timestamp (may be float or int) to our version
        (long) int.
        We don't want to use floats, so we just scale by 1e6 to get
        an integer in usecs. 
    """
    return long(ts*1000000L) # has to be long for py 2.2.x

def version2timestamp(v):
    """ Convert version number to UNIX timestamp (float).
        This must ONLY be used for display purposes.
    """
    return v/1000000.0
    
#############################################################################
### InterWiki
#############################################################################

def split_wiki(wikiurl):
    """
    Split a wiki url.
    
    @param wikiurl: the url to split
    @rtype: tuple
    @return: (tag, tail)
    """
    # !!! use a regex here!
    try:
        wikitag, tail = wikiurl.split(":", 1)
    except ValueError:
        try:
            wikitag, tail = wikiurl.split("/", 1)
        except ValueError:
            wikitag = None
            tail = None

    return (wikitag, tail)


def join_wiki(wikiurl, wikitail):
    """
    Add a page name to an interwiki url.
    
    @param wikiurl: wiki url, maybe including a $PAGE placeholder
    @param wikitail: page name
    @rtype: string
    @return: generated URL of the page in the other wiki
    """
    if wikiurl.find('$PAGE') == -1:
        return wikiurl + wikitail
    else:
        return wikiurl.replace('$PAGE', wikitail)


def resolve_wiki(request, wikiurl):
    """
    Resolve an interwiki link.
    
    @param request: the request object
    @param wikiurl: the InterWiki:PageName link
    @rtype: tuple
    @return: (wikitag, wikiurl, wikitail)
    """
    # load map (once, and only on demand)
    try:
        _interwiki_list = request.cfg._interwiki_list
    except AttributeError:
        _interwiki_list = {}
        lines = []
 
        # order is important here, the local intermap file takes
        # precedence over the shared one, and is thus read AFTER
        # the shared one
        intermap_files = request.cfg.shared_intermap
        if not isinstance(intermap_files, type([])):
            intermap_files = [intermap_files]
        intermap_files.append(os.path.join(request.cfg.data_dir, "intermap.txt"))

        for filename in intermap_files:
            if filename and os.path.isfile(filename):
                f = open(filename, "r")
                lines.extend(f.readlines())
                f.close()

        for line in lines:
            if not line or line[0] == '#': continue
            try:
                line = "%s %s/InterWiki" % (line, request.getScriptname()) 
                wikitag, urlprefix, trash = line.split(None, 2)
            except ValueError:
                pass
            else:
                _interwiki_list[wikitag] = urlprefix

        del lines

        # add own wiki as "Self" and by its configured name
        _interwiki_list['Self'] = request.getScriptname() + '/'
        if request.cfg.interwikiname:
            _interwiki_list[request.cfg.interwikiname] = request.getScriptname() + '/'

        # save for later
        request.cfg._interwiki_list = _interwiki_list

    # split wiki url
    wikitag, tail = split_wiki(wikiurl)

    # return resolved url
    if wikitag and _interwiki_list.has_key(wikitag):
        return (wikitag, _interwiki_list[wikitag], tail, False)
    else:
        return (wikitag, request.getScriptname(), "/InterWiki", True)


#############################################################################
### Page types (based on page names)
#############################################################################

def isSystemPage(request, pagename):
    """ Is this a system page? Uses AllSystemPagesGroup internally.
    
    @param request: the request object
    @param pagename: the page name
    @rtype: bool
    @return: true if page is a system page
    """
    return (request.dicts.has_member('SystemPagesGroup', pagename) or
        isTemplatePage(request, pagename) or
        isFormPage(request, pagename))


def isTemplatePage(request, pagename):
    """ Is this a template page?
    
    @param pagename: the page name
    @rtype: bool
    @return: true if page is a template page
    """
    filter = re.compile(request.cfg.page_template_regex, re.UNICODE)
    return filter.search(pagename) is not None


def isFormPage(request, pagename):
    """ Is this a form page?
    
    @param pagename: the page name
    @rtype: bool
    @return: true if page is a form page
    """
    filter = re.compile(request.cfg.page_form_regex, re.UNICODE)
    return filter.search(pagename) is not None

def isGroupPage(request, pagename):
    """ Is this a name of group page?

    @param pagename: the page name
    @rtype: bool
    @return: true if page is a form page
    """
    filter = re.compile(request.cfg.page_group_regex, re.UNICODE)
    return filter.search(pagename) is not None


def filterCategoryPages(request, pagelist):
    """ Return category pages in pagelist

    WARNING: DO NOT USE THIS TO FILTER THE FULL PAGE LIST! Use
    getPageList with a filter function.
        
    If you pass a list with a single pagename, either that is returned
    or an empty list, thus you can use this function like a `isCategoryPage`
    one.
       
    @param pagelist: a list of pages
    @rtype: list
    @return: only the category pages of pagelist
    """
    func = re.compile(request.cfg.page_category_regex, re.UNICODE).search
    return filter(func, pagelist)


# TODO: we may rename this to getLocalizedPage because it returns page
# that have translations.
def getSysPage(request, pagename):
    """ Get a system page according to user settings and available translations.
    
    We include some special treatment for the case that <pagename> is the
    currently rendered page, as this is the case for some pages used very
    often, like FrontPage, RecentChanges etc. - in that case we reuse the
    already existing page object instead creating a new one.

    @param request: the request object
    @param pagename: the name of the page
    @rtype: Page object
    @return: the page object of that system page, using a translated page,
             if it exists
    """
    from MoinMoin.Page import Page
    i18n_name = request.getText(pagename, formatted=False)
    pageobj = None
    if i18n_name != pagename:
        if request.page and i18n_name == request.page.page_name:
            # do not create new object for current page
            i18n_page = request.page
            if i18n_page.exists():
                pageobj = i18n_page
        else:
            i18n_page = Page(request, i18n_name)
            if i18n_page.exists():
                pageobj = i18n_page

    # if we failed getting a translated version of <pagename>,
    # we fall back to english
    if not pageobj:
        if request.page and pagename == request.page.page_name:
            # do not create new object for current page
            pageobj = request.page
        else:
            pageobj = Page(request, pagename)
    return pageobj


def getFrontPage(request):
    """ Convenience function to get localized front page

    @param request: current request
    @rtype: Page object
    @return localized FrontPage
    """
    return getSysPage(request, request.cfg.page_front_page)
    

# FIXME - move to user class?
def getHomePage(request, username=None):
    """
    Get a user's homepage, or return None for anon users and
    those who have not created a homepage.
    
    @param request: the request object
    @param username: the user's name
    @rtype: Page
    @return: user's homepage object - or None
    """
    from MoinMoin.Page import Page
    # default to current user
    if username is None and request.user.valid:
        username = request.user.name

    # known user?
    if username:
        # Return home page
        page = Page(request, username)
        if page.exists():
            return page

    return None


def AbsPageName(request, context, pagename):
    """
    Return the absolute pagename for a (possibly) relative pagename.

    @param context: name of the page where "pagename" appears on
    @param pagename: the (possibly relative) page name
    @rtype: string
    @return: the absolute page name
    """
    if config.allow_subpages:
        if pagename.startswith(PARENT_PREFIX):
            pagename = '/'.join(filter(None, context.split('/')[:-1] + [pagename[PARENT_PREFIX_LEN:]]))
        elif pagename.startswith(CHILD_PREFIX):
            pagename = context + '/' + pagename[CHILD_PREFIX_LEN:]

    return pagename

def pagelinkmarkup(pagename):
    """ return markup that can be used as link to page <pagename> """
    if isStrictWikiname(pagename): # XXX TODO re.match(Parser.word_rule, pagename)
        return pagename
    else:
        return u'["%s"]' % pagename

#############################################################################
### Plugins
#############################################################################

def importPlugin(cfg, kind, name, function="execute"):
    """ Import wiki or builtin plugin
    
    Returns an object from a plugin module or None if module or
    'function' is not found.

    kind may be one of 'action', 'formatter', 'macro', 'processor',
    'parser' or any other directory that exist in MoinMoin or
    data/plugin

    Wiki plugins will always override builtin plugins. If you want
    specific plugin, use either importWikiPlugin or importName directly.
    
    @param cfg: wiki config instance
    @param kind: what kind of module we want to import
    @param name: the name of the module
    @param function: the function name
    @rtype: callable
    @return: "function" of module "name" of kind "kind", or None
    """
    # Try to import from the wiki
    plugin = importWikiPlugin(cfg, kind, name, function)
    if plugin is None:
        # Try to get the plugin from MoinMoin
        modulename = 'MoinMoin.%s.%s' % (kind, name)
        plugin = pysupport.importName(modulename, function)
        
    return plugin


# Here we cache our plugins until we have a wiki object.
# WARNING: do not access directly in threaded enviromnent!
_wiki_plugins = {}

def importWikiPlugin(cfg, kind, name, function):
    """ Import plugin from the wiki data directory
    
    We try to import only ONCE - then cache the plugin, even if we got
    None. This way we prevent expensive import of existing plugins for
    each call to a plugin.

    @param cfg: wiki config instance
    @param kind: what kind of module we want to import
    @param name: the name of the module
    @param function: the function name
    @rtype: callable
    @return: "function" of module "name" of kind "kind", or None
    """
    global _wiki_plugins

    # Wiki plugins are located under 'wikiconfigname.plugin' module.
    modulename = '%s.plugin.%s.%s' % (cfg.siteid, kind, name)
    key = (modulename, function)
    try:
        # Try cache first - fast!
        plugin = _wiki_plugins[key]
    except KeyError:
        # Try to import from disk and cache result - slow!
        plugin = pysupport.importName(modulename, function)
        _wiki_plugins[key] = plugin

    return plugin

# If we use threads, make this function thread safe
if config.use_threads:
    importWikiPlugin = pysupport.makeThreadSafe(importWikiPlugin)

def builtinPlugins(kind):
    """ Gets a list of modules in MoinMoin.'kind'
    
    @param kind: what kind of modules we look for
    @rtype: list
    @return: module names
    """
    modulename = "MoinMoin." + kind
    plugins = pysupport.importName(modulename, "modules")
    return plugins or []


def wikiPlugins(kind, cfg):
    """ Gets a list of modules in data/plugin/'kind'
    
    @param kind: what kind of modules we look for
    @rtype: list
    @return: module names
    """
    # Wiki plugins are located in wikiconfig.plugin module
    modulename = '%s.plugin.%s' % (cfg.siteid, kind)
    plugins = pysupport.importName(modulename, "modules")
    return plugins or []


def getPlugins(kind, cfg):
    """ Gets a list of plugin names of kind
    
    @param kind: what kind of modules we look for
    @rtype: list
    @return: module names
    """
    # Copy names from builtin plugins - so we dont destroy the value
    all_plugins = builtinPlugins(kind)[:]
    
    # Add extension plugins without duplicates
    for plugin in wikiPlugins(kind, cfg):
        if plugin not in all_plugins:
            all_plugins.append(plugin)

    return all_plugins


#############################################################################
### Parsers
#############################################################################

def getParserForExtension(cfg, extension):
    """
    Returns the Parser class of the parser fit to handle a file
    with the given extension. The extension should be in the same
    format as os.path.splitext returns it (i.e. with the dot).
    Returns None if no parser willing to handle is found.
    The dict of extensions is cached in the config object.

    @param cfg: the Config instance for the wiki in question
    @param extension: the filename extension including the dot
    @rtype: class, None
    @returns: the parser class or None
    """
    ##
    ## this is not a caching until cfg is persistent between requests!!!
    ##
    if not hasattr(cfg, '_EXT_TO_PARSER'):
        import types
        etp, etd = {}, None
        for pname in getPlugins('parser', cfg):
            Parser = importPlugin(cfg, 'parser', pname, 'Parser')
            if Parser is not None:
                if hasattr(Parser, 'extensions'):
                    exts = Parser.extensions
                    if type(exts) == types.ListType:
                        for ext in Parser.extensions:
                            etp[ext] = Parser
                    elif str(exts) == '*':
                        etd = Parser
        # Cache in cfg for current request - this is not thread safe
        # when cfg will be cached per wiki in long running process.
        cfg._EXT_TO_PARSER = etp
        cfg._EXT_TO_PARSER_DEFAULT = etd
        
    return cfg._EXT_TO_PARSER.get(extension, cfg._EXT_TO_PARSER_DEFAULT)


#############################################################################
### Misc
#############################################################################

def parseAttributes(request, attrstring, endtoken=None, extension=None):
    """
    Parse a list of attributes and return a dict plus a possible
    error message.
    If extension is passed, it has to be a callable that returns
    None when it was not interested into the token, '' when all was OK
    and it did eat the token, and any other string to return an error
    message.
    
    @param request: the request object
    @param attrstring: string containing the attributes to be parsed
    @param endtoken: token terminating parsing
    @param extension: extension function -
                      gets called with the current token, the parser and the dict
    @rtype: dict, msg
    @return: a dict plus a possible error message
    """
    import shlex, StringIO

    _ = request.getText

    parser = shlex.shlex(StringIO.StringIO(attrstring))
    parser.commenters = ''
    msg = None
    attrs = {}

    while not msg:
        try:
            key = parser.get_token()
        except ValueError, err:
            msg = str(err)
            break
        if not key: break
        if endtoken and key == endtoken: break

        # call extension function with the current token, the parser, and the dict
        if extension:
            msg = extension(key, parser, attrs)
            if msg == '': continue
            if msg: break

        try:
            eq = parser.get_token()
        except ValueError, err:
            msg = str(err)
            break
        if eq != "=":
            msg = _('Expected "=" to follow "%(token)s"') % {'token': key}
            break

        try:
            val = parser.get_token()
        except ValueError, err:
            msg = str(err)
            break
        if not val:
            msg = _('Expected a value for key "%(token)s"') % {'token': key}
            break

        key = escape(key) # make sure nobody cheats

        # safely escape and quote value
        if val[0] in ["'", '"']:
            val = escape(val)
        else:
            val = '"%s"' % escape(val, 1)

        attrs[key.lower()] = val

    return attrs, msg or ''


def taintfilename(basename):
    """
    Make a filename that is supposed to be a plain name secure, i.e.
    remove any possible path components that compromise our system.
    
    @param basename: (possibly unsafe) filename
    @rtype: string
    @return: (safer) filename
    """
    basename = basename.replace(os.pardir, '_')
    basename = basename.replace(':', '_')
    basename = basename.replace('/', '_')
    basename = basename.replace('\\', '_')
    return basename


def mapURL(request, url):
    """
    Map URLs according to 'cfg.url_mappings'.
    
    @param url: a URL
    @rtype: string
    @return: mapped URL
    """
    # check whether we have to map URLs
    if request.cfg.url_mappings:
        # check URL for the configured prefixes
        for prefix in request.cfg.url_mappings.keys():
            if url.startswith(prefix):
                # substitute prefix with replacement value
                return request.cfg.url_mappings[prefix] + url[len(prefix):]

    # return unchanged url
    return url


def getUnicodeIndexGroup(name):
    """
    Return a group letter for `name`, which must be a unicode string.
    Currently supported: Hangul Syllables (U+AC00 - U+D7AF)
    
    @param name: a string
    @rtype: string
    @return: group letter or None
    """
    c = name[0]
    if u'\uAC00' <= c <= u'\uD7AF': # Hangul Syllables
        return unichr(0xac00 + (int(ord(c) - 0xac00) / 588) * 588)
    else:
        return c


def isStrictWikiname(name, word_re=re.compile(ur"^(?:[%(u)s][%(l)s]+){2,}$" % {'u':config.chars_upper, 'l':config.chars_lower})):
    """
    Check whether this is NOT an extended name.
    
    @param name: the wikiname in question
    @rtype: bool
    @return: true if name matches the word_re
    """
    return word_re.match(name)


def isPicture(url):
    """
    Is this a picture's url?
    
    @param url: the url in question
    @rtype: bool
    @return: true if url points to a picture
    """
    extpos = url.rfind(".")
    return extpos > 0 and url[extpos:].lower() in ['.gif', '.jpg', '.jpeg', '.png']


def link_tag(request, params, text=None, formatter=None, on=None, **kw):
    """ Create a link.

    @param request: the request object
    @param params: parameter string appended to the URL after the scriptname/
    @param text: text / inner part of the <a>...</a> link - does NOT get
                 escaped, so you can give HTML here and it will be used verbatim
    @param formatter: the formatter object to use
    @keyword on: opening/closing tag only
    @keyword attrs: additional attrs (HTMLified string)
    @rtype: string
    @return: formatted link tag
    """
    css_class = kw.get('css_class', None)
    if text is None:
        text = params # default
    if formatter:
        url = "%s/%s" % (request.getScriptname(), params)
        if on != None:
            return formatter.url(on, url, css_class, **kw)
        return (formatter.url(1, url, css_class, **kw) +
                formatter.rawHTML(text) +
                formatter.url(0))
    if on != None and not on:
        return '</a>'
        
    attrs = ''
    if kw.has_key('attrs'):
        attrs += ' ' + kw['attrs']
    if css_class:
        attrs += ' class="%s"' % css_class
    result = '<a%s href="%s/%s">' % (attrs, request.getScriptname(), params)
    if on:
        return result
    else:
        return "%s%s</a>" % (result, text)


def linediff(oldlines, newlines, **kw):
    """
    Find changes between oldlines and newlines.
    
    @param oldlines: list of old text lines
    @param newlines: list of new text lines
    @keyword ignorews: if 1: ignore whitespace
    @rtype: list
    @return: lines like diff tool does output.
    """
    false = lambda s: None 
    if kw.get('ignorews', 0):
        d = difflib.Differ(false)
    else:
        d = difflib.Differ(false, false)

    lines = list(d.compare(oldlines,newlines))
 
    # return empty list if there were no changes
    changed = 0
    for l in lines:
        if l[0] != ' ':
            changed = 1
            break
    if not changed: return []

    if not "we want the unchanged lines, too":
        if "no questionmark lines":
            lines = filter(lambda line : line[0]!='?', lines)
        return lines


    # calculate the hunks and remove the unchanged lines between them
    i = 0              # actual index in lines
    count = 0          # number of unchanged lines
    lcount_old = 0     # line count old file
    lcount_new = 0     # line count new file
    while i < len(lines):
        marker = lines[i][0]
        if marker == ' ':
            count = count + 1
            i = i + 1
            lcount_old = lcount_old + 1
            lcount_new = lcount_new + 1
        elif marker in ['-', '+']:
            if (count == i) and count > 3:
                lines[:i-3] = []
                i = 4
                count = 0
            elif count > 6:
                # remove lines and insert new hunk indicator
                lines[i-count+3:i-3] = ['@@ -%i, +%i @@\n' %
                                        (lcount_old, lcount_new)]
                i = i - count + 8
                count = 0
            else:
                count = 0
                i = i + 1                            
            if marker == '-': lcount_old = lcount_old + 1
            else: lcount_new = lcount_new + 1
        elif marker == '?':
            lines[i:i+1] = []

    # remove unchanged lines a the end
    if count > 3:
        lines[-count+3:] = []
    
    return lines


def pagediff(request, pagename1, rev1, pagename2, rev2, **kw):
    """
    Calculate the "diff" between two page contents.

    @param pagename1: name of first page
    @param rev1: revision of first page
    @param pagename2: name of second page
    @param rev2: revision of second page
    @keyword ignorews: if 1: ignore pure-whitespace changes.
    @rtype: list
    @return: lines of diff output
    """
    from MoinMoin.Page import Page
    lines1 = Page(request, pagename1, rev=rev1).getlines()
    lines2 = Page(request, pagename2, rev=rev2).getlines()
    
    lines = linediff(lines1, lines2, **kw)
    return lines
 

#############################################################################
### Page header / footer
#############################################################################

# FIXME - this is theme code, move to theme
# Could be simplified by using a template

def send_title(request, text, **keywords):
    """
    Output the page header (and title).

    TODO: check all code that call us and add page keyword for the
    current page being rendered.
    
    @param request: the request object
    @param text: the title text
    @keyword link: URL for the title
    @keyword msg: additional message (after saving)
    @keyword pagename: 'PageName'
    @keyword page: the page instance that called us.
    @keyword print_mode: 1 (or 0)
    @keyword media: css media type, defaults to 'screen'
    @keyword allow_doubleclick: 1 (or 0)
    @keyword html_head: additional <head> code
    @keyword body_attr: additional <body> attributes
    @keyword body_onload: additional "onload" JavaScript code
    """
    from MoinMoin.Page import Page
    _ = request.getText
    
    if keywords.has_key('page'):
        page = keywords['page']
        pagename = page.page_name
    else:
        pagename = keywords.get('pagename', '')
        page = Page(request, pagename)
    
    scriptname = request.getScriptname()
    pagename_quoted = quoteWikinameURL(pagename)

    # get name of system pages
    page_front_page = getFrontPage(request).page_name
    page_help_contents = getSysPage(request, 'HelpContents').page_name
    page_title_index = getSysPage(request, 'TitleIndex').page_name
    page_word_index = getSysPage(request, 'WordIndex').page_name
    page_user_prefs = getSysPage(request, 'UserPreferences').page_name
    page_help_formatting = getSysPage(request, 'HelpOnFormatting').page_name
    page_find_page = getSysPage(request, 'FindPage').page_name
    page_home_page = getattr(getHomePage(request), 'page_name', None)
    page_parent_page = getattr(page.getParentPage(), 'page_name', None)
    
    # Prepare the HTML <head> element
    user_head = [request.cfg.html_head]

    # include charset information - needed for moin_dump or any other case
    # when reading the html without a web server
    user_head.append('''<meta http-equiv="Content-Type" content="text/html;charset=%s">\n''' % config.charset)

    meta_keywords = request.getPragma('keywords')
    meta_desc = request.getPragma('description')
    if meta_keywords:
        user_head.append('<meta name="keywords" content="%s">\n' % escape(meta_keywords, 1))
    if meta_desc:
        user_head.append('<meta name="description" content="%s">\n' % escape(meta_desc, 1))

    # search engine precautions / optimization:
    # if it is an action or edit/search, send query headers (noindex,nofollow):
    if request.query_string:
        user_head.append(request.cfg.html_head_queries)
    elif request.request_method == 'POST':
        user_head.append(request.cfg.html_head_posts)
    # if it is a special page, index it and follow the links - we do it
    # for the original, English pages as well as for (the possibly
    # modified) frontpage:
    elif pagename in [page_front_page, request.cfg.page_front_page,
                      page_title_index, ]:
        user_head.append(request.cfg.html_head_index)
    # if it is a normal page, index it, but do not follow the links, because
    # there are a lot of illegal links (like actions) or duplicates:
    else:
        user_head.append(request.cfg.html_head_normal)

    if keywords.has_key('pi_refresh') and keywords['pi_refresh']:
        user_head.append('<meta http-equiv="refresh" content="%(delay)d;URL=%(url)s">' % keywords['pi_refresh'])
    
    # output buffering increases latency but increases throughput as well
    output = []
    # later: <html xmlns=\"http://www.w3.org/1999/xhtml\">
    output.append("""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html>
<head>
%s
%s
%s
""" % (
        ''.join(user_head),
        keywords.get('html_head', ''),
        request.theme.html_head({
            'title': escape(text),
            'sitename': escape(request.cfg.html_pagetitle or request.cfg.sitename),
            'print_mode': keywords.get('print_mode', False),
            'media': keywords.get('media', 'screen'),
        })
    ))

    # Links
    output.append('<link rel="Start" href="%s/%s">\n' % (scriptname, quoteWikinameURL(page_front_page)))
    if pagename:
        output.append('<link rel="Alternate" title="%s" href="%s/%s?action=raw">\n' % (
            _('Wiki Markup'), scriptname, pagename_quoted,))
        output.append('<link rel="Alternate" media="print" title="%s" href="%s/%s?action=print">\n' % (
            _('Print View'), scriptname, pagename_quoted,))

        # !!! currently disabled due to Mozilla link prefetching, see
        # http://www.mozilla.org/projects/netlib/Link_Prefetching_FAQ.html
        #~ all_pages = request.getPageList()
        #~ if all_pages:
        #~     try:
        #~         pos = all_pages.index(pagename)
        #~     except ValueError:
        #~         # this shopuld never happend in theory, but let's be sure
        #~         pass
        #~     else:
        #~         request.write('<link rel="First" href="%s/%s">\n' % (request.getScriptname(), quoteWikinameURL(all_pages[0]))
        #~         if pos > 0:
        #~             request.write('<link rel="Previous" href="%s/%s">\n' % (request.getScriptname(), quoteWikinameURL(all_pages[pos-1])))
        #~         if pos+1 < len(all_pages):
        #~             request.write('<link rel="Next" href="%s/%s">\n' % (request.getScriptname(), quoteWikinameURL(all_pages[pos+1])))
        #~         request.write('<link rel="Last" href="%s/%s">\n' % (request.getScriptname(), quoteWikinameURL(all_pages[-1])))

        if page_parent_page:
            output.append('<link rel="Up" href="%s/%s">\n' % (scriptname, quoteWikinameURL(page_parent_page)))

    # write buffer because we call AttachFile
    request.write(''.join(output))
    output = []

    if pagename:
        from MoinMoin.action import AttachFile
        AttachFile.send_link_rel(request, pagename)

    output.extend([
        '<link rel="Search" href="%s/%s">\n' % (scriptname, quoteWikinameURL(page_find_page)),
        '<link rel="Index" href="%s/%s">\n' % (scriptname, quoteWikinameURL(page_title_index)),
        '<link rel="Glossary" href="%s/%s">\n' % (scriptname, quoteWikinameURL(page_word_index)),
        '<link rel="Help" href="%s/%s">\n' % (scriptname, quoteWikinameURL(page_help_formatting)),
                  ])

    output.append("</head>\n")
    request.write(''.join(output))
    output = []
    request.flush()

    # start the <body>
    bodyattr = []
    if keywords.has_key('body_attr'):
        bodyattr.append(' ')
        bodyattr.append(keywords['body_attr'])

    # Add doubleclick edit action
    if (pagename and keywords.get('allow_doubleclick', 0) and
        not keywords.get('print_mode', 0) and
        request.user.edit_on_doubleclick):
        if request.user.may.write(pagename): # separating this gains speed
            querystr = escape(util.web.makeQueryString({'action': 'edit'}))
            # TODO: remove escape=0 in 1.4
            url = page.url(request, querystr, escape=0)
            bodyattr.append(''' ondblclick="location.href='%s'"''' % url)

    # Set body to the user interface language and direction
    bodyattr.append(' %s' % request.theme.ui_lang_attr())
    
    body_onload = keywords.get('body_onload', '')
    if body_onload:
        bodyattr.append(''' onload="%s"''' % body_onload)
    output.append('\n<body%s>\n' % ''.join(bodyattr))

    # Output -----------------------------------------------------------

    theme = request.theme
    
    # If in print mode, start page div and emit the title
    if keywords.get('print_mode', 0):
        d = {'title_text': text, 'title_link': None, 'page': page,}
        request.themedict = d
        output.append(theme.startPage())
        output.append(theme.title(d))      

    # In standard mode, emit theme.header
    else:
        # prepare dict for theme code:
        d = {
            'theme': theme.name,
            'script_name': scriptname,
            'title_text': text,
            'title_link': keywords.get('link', ''),
            'logo_string': request.cfg.logo_string,
            'site_name': request.cfg.sitename,
            'page': page,
            'pagesize': pagename and page.size() or 0,
            'last_edit_info': pagename and page.lastEditInfo() or '',
            'page_name': pagename or '',
            'page_find_page': page_find_page,
            'page_front_page': page_front_page,
            'page_home_page': page_home_page,
            'page_help_contents': page_help_contents,
            'page_help_formatting': page_help_formatting,
            'page_parent_page': page_parent_page,
            'page_title_index': page_title_index,
            'page_word_index': page_word_index,
            'page_user_prefs': page_user_prefs,
            'user_name': request.user.name,
            'user_valid': request.user.valid,
            'user_prefs': (page_user_prefs, request.user.name)[request.user.valid],
            'msg': keywords.get('msg', ''),
            'trail': keywords.get('trail', None),
            # Discontinued keys, keep for a while for 3rd party theme developers
            'titlesearch': 'use self.searchform(d)',
            'textsearch': 'use self.searchform(d)',
            'navibar': ['use self.navibar(d)'],
            'available_actions': ['use self.request.availableActions(page)'],
        }

        # add quoted versions of pagenames
        newdict = {}
        for key in d:
            if key.startswith('page_'):
                if not d[key] is None:
                    newdict['q_'+key] = quoteWikinameURL(d[key])
                else:
                    newdict['q_'+key] = None
        d.update(newdict)
        request.themedict = d

        # now call the theming code to do the rendering
        output.append(theme.header(d))
    
    # emit it
    request.write(''.join(output))
    output = []
    request.flush()


def send_footer(request, pagename, **keywords):
    """
    Output the page footer.

    @param request: the request object
    @param pagename: WikiName of the page
    @keyword editable: true, when page is editable (default: true)
    @keyword showpage: true, when link back to page is wanted (default: false)
    @keyword print_mode: true, when page is displayed in Print mode
    """
    d = request.themedict
    theme = request.theme

    # Emit end of page in print mode, or complete footer in standard mode
    if keywords.get('print_mode', 0):
        request.write(theme.pageinfo(d['page']))
        request.write(theme.endPage())
    else:
        # This is used only by classic now, kill soon
        d['footer_fragments'] = request._footer_fragments
        request.write(theme.footer(d, **keywords))

    
########################################################################
### Tickets - used by RenamePage and DeletePage
########################################################################

def createTicket(tm = None):
    """Create a ticket using a site-specific secret (the config)"""
    import sha, time, types
    ticket = tm or "%010x" % time.time()
    digest = sha.new()
    digest.update(ticket)

    cfgvars = vars(config)
    for var in cfgvars.values():
        if type(var) is types.StringType:
            digest.update(repr(var))

    return "%s.%s" % (ticket, digest.hexdigest())


def checkTicket(ticket):
    """Check validity of a previously created ticket"""
    timestamp = ticket.split('.')[0]
    ourticket = createTicket(timestamp)
    return ticket == ourticket


