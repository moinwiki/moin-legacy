# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - Page class

    @copyright: 2000-2004 by J�rgen Hermann <jh@web.de>
    @license: GNU GPL, see COPYING for details.
"""

import StringIO, os, re, urllib, random, codecs

from MoinMoin import config, caching, user, util, wikiutil
from MoinMoin.logfile import eventlog
from MoinMoin.util import filesys, web

class Page:
    """Page - Manage an (immutable) page associated with a WikiName.
       To change a page's content, use the PageEditor class.
    """

    # Header regular expression, used to get header boundaries
    header_re = r'(^#+.*(?:\n\s*)+)+'

    def __init__(self, request, page_name, **keywords):
        """
        Create page object.

        Note that this is a 'lean' operation, since the text for the page
        is loaded on demand. Thus, things like `Page(name).link_to()` are
        efficient.

        @param page_name: WikiName of the page
        @keyword rev: number of older revision
        @keyword formatter: formatter instance
        @keyword include_self: if 1, include current user (default: 0)
        """
        self.rev = keywords.get('rev', 0) # revision of this page
        self.is_rootpage = keywords.get('is_rootpage', 0) # is this __init__ of rootpage?
        self.include_self = keywords.get('include_self', 0)
        self.request = request
        self.cfg = request.cfg

        self.page_name = page_name

        # XXX uncomment to see how many pages we create....
        #import sys, traceback
        #print >>sys.stderr, "page %s" % repr(page_name)
        #traceback.print_stack(limit=4, file=sys.stderr)

        if keywords.has_key('formatter'):
            self.formatter = keywords.get('formatter')
            self.default_formatter = 0
        else:
            self.default_formatter = 1

        self._raw_body = None
        self._raw_body_modified = 0
        self.hilite_re = None
        self.language = None

        self.reset()

    def reset(self):
        """ Reset page state """
        page_name = self.page_name
        # page_name quoted for file system usage, needs to be reset to
        # None when pagename changes

        qpagename = wikiutil.quoteWikinameFS(page_name)
        self.page_name_fs = qpagename

        # the normal and the underlay path used for this page
        if not self.cfg.data_underlay_dir is None:
            underlaypath = os.path.join(self.cfg.data_underlay_dir, "pages", qpagename)
        else:
            underlaypath = None
        if self.is_rootpage: # we have no request.rootpage yet!
            if not page_name:
                normalpath = self.cfg.data_dir
            else:
                raise NotImplementedError(
                    "TODO: handle other values of rootpage (not used yet)")
        else:
            normalpath = self.request.rootpage.getPagePath("pages", qpagename,
                                                           check_create=0, use_underlay=0)

        # TUNING - remember some essential values

        # does the page come from normal page storage (0) or from
        # underlay dir (1) (can be used as index into following lists)
        self._underlay = None

        # path to normal / underlay page dir
        self._pagepath = [normalpath, underlaypath]

        # path to normal / underlay page file
        self._pagefile = [normalpath, underlaypath]

        # *latest* revision of this page XXX needs to be reset to None
        # when current rev changes
        self._current_rev = [None, None]

        # does a page in _pagepath (current revision) exist?  XXX needs
        # to be reset when rev is created/deleted
        self._exists = [None, None]

    def get_current_from_pagedir(self, pagedir):
        """ get the current revision number from an arbitrary pagedir.
            does not modify page object's state, uncached, direct disk access.
            @param pagedir: the pagedir with the 'current' file to read
            @return: int currentrev
        """
        revfilename = os.path.join(pagedir, 'current')
        try:
            revfile = open(revfilename)
            revstr = revfile.read().strip()
            revfile.close()
            rev = int(revstr)
        except:
            rev = 99999999 # XXX
        return rev

    def get_rev_dir(self, pagedir, rev=0):
        """
        get a revision of a page from an arbitrary pagedir.
        does not modify page object's state, uncached, direct disk access.
        @param pagedir: the path to the pagedir
        @param rev: int revision to get (default is 0 and means the current
                    revision (in this case, the real revint is returned)
        @return: (str pagefilename, int realrevint, bool exists)
        """
        if rev == 0:
            rev = self.get_current_from_pagedir(pagedir)

        revstr = '%08d' % rev
        pagefile = os.path.join(pagedir, 'revisions', revstr)
        exists = os.path.exists(pagefile)
        return pagefile, rev, exists

    def get_rev(self, use_underlay=-1, rev=0):
        """
        get a revision of this page
        @param use_underlay: -1 == auto, 0 == normal, 1 == underlay
        @param rev: int revision to get (default is 0 and means the current
                    revision (in this case, the real revint is returned)
        @return: (str pagefilename, int realrevint, bool exists)
        """
        if use_underlay == -1:
            if self._underlay is not None and self._pagepath[self._underlay] is not None:
                underlay = self._underlay
                pagedir = self._pagepath[underlay]
            else:
                underlay, pagedir = self.getPageStatus(check_create=0)
        else:
            underlay, pagedir = use_underlay, self._pagepath[use_underlay]

        if rev == 0:
            if self._current_rev[underlay] is None:
                realrev = self.get_current_from_pagedir(pagedir)
                self._current_rev[underlay] = realrev # XXX XXX
            else:
                realrev = self._current_rev[underlay]

            _exists = self._exists[underlay]
            _realrev = self._current_rev[underlay]
            _pagefile = self._pagefile[underlay]
            if _pagefile is not None and \
               _realrev is not None and _exists is not None:
                return _pagefile, _realrev, _exists
        else:
            realrev = rev

        pagefile, realrev, exists = self.get_rev_dir(pagedir, realrev)
        if rev == 0:
            self._exists[underlay] = exists # XXX XXX
            self._current_rev[underlay] = realrev # XXX XXX
            self._pagefile[underlay] = pagefile # XXX XXX

        return pagefile, realrev, exists

    def current_rev(self):
        pagefile, rev, exists = self.get_rev()
        return rev

    def get_real_rev(self):
        """Returns the real revision number of this page. A rev=0 is
        translated to the current revision.

        @returns: revision number > 0
        @rtype: int
        """
        if self.rev == 0:
            return self.current_rev()
        return self.rev

    def getPageBasePath(self, use_underlay):
        """
        Get full path to a page-specific storage area. `args` can
        contain additional path components that are added to the base path.

        @param use_underlay: force using a specific pagedir, default '-1'
                                '-1' = automatically choose page dir
                                '1' = use underlay page dir
                                '0' = use standard page dir
        @rtype: string
        @return: the full path to the storage area
        """
        standardpath, underlaypath = self._pagepath
        if underlaypath is None:
            use_underlay = 0

        # self is a NORMAL page
        if not self is self.request.rootpage:
            if use_underlay == -1: # automatic
                if self._underlay is None:
                    underlay, path = 0, standardpath
                    pagefile, rev, exists = self.get_rev(use_underlay=0)
                    if not exists:
                        pagefile, rev, exists = self.get_rev(use_underlay=1)
                        if exists:
                            underlay, path = 1, underlaypath
                    self._underlay = underlay # XXX XXX
                else:
                    underlay = self._underlay
                    path = self._pagepath[underlay]
            else: # normal or underlay
                underlay, path = use_underlay, self._pagepath[use_underlay]

        # self is rootpage
        else:
            # our current rootpage is not a toplevel, but under another page
            if self.page_name:
                # this assumes flat storage of pages and sub pages on same level
                if use_underlay == -1: # automatic
                    if self._underlay is None:
                        underlay, path = 0, standardpath
                        pagefile, rev, exists = self.get_rev(use_underlay=0)
                        if not exists:
                            pagefile, rev, exists = self.get_rev(use_underlay=1)
                            if exists:
                                underlay, path = 1, underlaypath
                        self._underlay = underlay # XXX XXX
                    else:
                        underlay = self._underlay
                        path = self._pagepath[underlay]
                else: # normal or underlay
                    underlay, path = use_underlay, self._pagepath[use_underlay]

            # our current rootpage is THE virtual rootpage, really at top of all
            else:
                # 'auto' doesn't make sense here. maybe not even 'underlay':
                if use_underlay == 1:
                    underlay, path = 1, self.cfg.data_underlay_dir
                # no need to check 'standard' case, we just use path in that case!
                else:
                    # this is the location of the virtual root page
                    underlay, path = 0, self.cfg.data_dir

        return underlay, path

    def getPageStatus(self, *args, **kw):
        """
        Get full path to a page-specific storage area. `args` can
        contain additional path components that are added to the base path.

        @param args: additional path components
        @keyword use_underlay: force using a specific pagedir, default '-1'
                                -1 = automatically choose page dir
                                1 = use underlay page dir
                                0 = use standard page dir
        @keyword check_create: if true, ensures that the path requested really exists
                               (if it doesn't, create all directories automatically).
                               (default true)
        @keyword isfile: is the last component in args a filename? (default is false)
        @rtype: string
        @return: the full path to the storage area
        """
        check_create = kw.get('check_create', 1)
        isfile = kw.get('isfile', 0)
        use_underlay = kw.get('use_underlay', -1)
        underlay, path = self.getPageBasePath(use_underlay)
        fullpath = os.path.join(*((path,) + args))
        if check_create:
            if isfile:
                dirname, filename = os.path.split(fullpath)
            else:
                dirname = fullpath
            if not os.path.exists(dirname):
                filesys.makeDirs(dirname)
        return underlay, fullpath

    def getPagePath(self, *args, **kw):
        return self.getPageStatus(*args, **kw)[1]

    def split_title(self, request, force=0):
        """
        Return a string with the page name split by spaces, if
        the user wants that.

        @param request: the request object
        @param force: if != 0, then force splitting the page_name
        @rtype: unicode
        @return: pagename of this page, splitted into space separated words
        """
        if not force and not request.user.wikiname_add_spaces:
            return self.page_name

        # look for the end of words and the start of a new word,
        # and insert a space there
        split_re = re.compile('([%s])([%s])' % (config.chars_lower, config.chars_upper))
        splitted = split_re.sub(r'\1 \2', self.page_name)
        return splitted

    def _text_filename(self, **kw):
        """
        The name of the page file, possibly of an older page.

        @keyword rev: page revision, overriding self.rev
        @rtype: string
        @return: complete filename (including path) to this page
        """
        if hasattr(self, '_text_filename_force'):
            return self._text_filename_force
        rev = kw.get('rev', 0)
        if not rev and self.rev:
            rev = self.rev
        fname, rev, exists = self.get_rev(-1, rev)
        return fname

    def _tmp_filename(self):
        """
        The name of the temporary file used while saving.

        @rtype: string
        @return: temporary filename (complete path + filename)
        """
        rnd = random.randint(0,1000000000)
        tmpname = os.path.join(self.cfg.data_dir, '#%s.%d#' % (self.page_name_fs, rnd))
        return tmpname

    # XXX TODO clean up the mess, rewrite _last_edited, last_edit, lastEditInfo for new logs,
    # XXX TODO do not use mtime() calls any more
    def _last_edited(self, request):
        from MoinMoin.logfile import editlog
        try:
            logfile = editlog.EditLog(request, self.getPagePath('edit-log', check_create=0, isfile=1))
            logfile.to_end()
            log = logfile.previous()
        except StopIteration:
            log = None
        return log

    def last_edit(self, request):
        """
        Return the last edit.
        This is used by wikirpc(2).py.

        @param request: the request object
        @rtype: dict
        @return: timestamp and editor information
        """
        if not self.exists():
            return None

        result = None
        if not self.rev:
            log = self._last_edited(request)
            if log:
                editordata = log.getEditorData(request)
                editor = editordata[1]
                if editordata[0] == 'homepage':
                    editor = editordata[1].page_name
                result = {
                    'timestamp': log.ed_time_usecs,
                    'editor': editor,
                }
                del log
        if not result:
            version = self.mtime_usecs()
            result = {
                'timestamp': version,
                'editor': '?',
            }

        return result

    def lastEditInfo(self, request=None):
        """ Return the last edit info.

        @param request: the request object
        @rtype: dict
        @return: timestamp and editor information
        """
        if not self.exists():
            return {}
        if request is None:
            request = self.request

        # Try to get data from log
        log = self._last_edited(request)
        if log:
            editor = log.getEditor(request)
            time = wikiutil.version2timestamp(log.ed_time_usecs)
            del log
        # Or from the file system
        else:
            editor = ''
            time = os.path.getmtime(self._text_filename())

        # Use user time format
        time = request.user.getFormattedDateTime(time)
        return {'editor': editor, 'time': time}

    def isWritable(self):
        """ Can this page be changed?

        @rtype: bool
        @return: true, if this page is writable or does not exist
        """
        return os.access(self._text_filename(), os.W_OK) or not self.exists()

    def isUnderlayPage(self, includeDeleted=True):
        """ Does this page live in the underlay dir?

        Return true even if the data dir has a copy of this page. To
        check for underlay only page, use ifUnderlayPage() and not
        isStandardPage()

        @param includeDeleted: include deleted pages
        @rtype: bool
        @return: true if page lives in the underlay dir
        """
        return self.exists(domain='underlay', includeDeleted=includeDeleted)

    def isStandardPage(self, includeDeleted=True):
        """ Does this page live in the data dir?

        Return true even if this is a copy of an underlay page. To check
        for data only page, use isStandardPage() and not isUnderlayPage().

        @param includeDeleted: include deleted pages
        @rtype: bool
        @return: true if page lives in the data dir
        """
        return self.exists(domain='standard', includeDeleted=includeDeleted)

    def exists(self, rev=0, domain=None, includeDeleted=False):
        """ Does this page exist?

        This is the lower level method for checking page existence. Use
        the higher level methods isUnderlayPagea and isStandardPage for
        cleaner code.

        @param rev: revision to look for. Default check current
        @param domain: where to look for the page. Default look in all,
            available values: 'underlay', 'standard'
        @param includeDeleted: ignore page state, just check its pagedir
        @rtype: bool
        @return: true, if page exists
        """
        # Edge cases
        if domain == 'underlay' and not self.request.cfg.data_underlay_dir:
            return False

        if includeDeleted:
            # Look for page directory, ignore page state
            if domain is None:
                checklist = [0, 1]
            else:
                checklist = [domain == 'underlay']
            for use_underlay in checklist:
                pagedir = self.getPagePath(use_underlay=use_underlay, check_create=0)
                if os.path.exists(pagedir):
                    return True
            return False
        else:
            # Look for non-deleted pages only, using get_rev
            if not rev and self.rev:
                rev = self.rev

            if domain is None:
                use_underlay = -1
            else:
                use_underlay = domain == 'underlay'
            d, d, exists = self.get_rev(use_underlay, rev)
            return exists

    def size(self, rev=0):
        """ Get Page size.

        @rtype: int
        @return: page size, 0 for non-existent pages.
        """
        if rev == self.rev: # same revision as self
            if self._raw_body is not None:
                return len(self._raw_body)

        try:
            return os.path.getsize(self._text_filename(rev=rev))
        except EnvironmentError, e:
            import errno
            if e.errno == errno.ENOENT: return 0
            raise

    def mtime_usecs(self):
        """
        Get modification timestamp of this page.

        @rtype: long
        @return: mtime of page (or 0 if page does not exist)
        """

        from MoinMoin.logfile import editlog

        mtime = 0L

        current_wanted = (self.rev == 0) # True if we search for the current revision
        wanted_rev = "%08d" % self.rev

        try:
            logfile = editlog.EditLog(self.request, rootpagename=self.page_name)
            for line in logfile.reverse():
                if (current_wanted and line.rev != 99999999) or line.rev == wanted_rev:
                    mtime = line.ed_time_usecs
                    break
        except StopIteration:
            logfile = None

        return mtime

    def mtime_printable(self, request):
        """
        Get printable modification timestamp of this page.

        @rtype: string
        @return: formatted string with mtime of page
        """
        t = self.mtime_usecs()
        if not t:
            result = "0" # TODO: i18n, "Ever", "Beginning of time"...?
        else:
            result = request.user.getFormattedDateTime(
                wikiutil.version2timestamp(t))
        return result

    def getPageCount(self, exists=0):
        """ Return page count

        The default value does the fastest listing, and return count of
        all pages, including deleted pages, ignoring acl rights.

        If you want to get a more accurate number, call with
        exists=1. This will be about 100 times slower though.

        @param exits: filter existing pages
        @rtype: int
        @return: number of pages
        """
        self.request.clock.start('getPageCount')
        if exists:
            # WARNING: SLOW
            pages = self.getPageList(user='')
        else:
            pages = self.request.pages
            if not pages:
                pages = self._listPages()
        count = len(pages)
        self.request.clock.stop('getPageCount')

        return count

    def getPageList(self, user=None, exists=1, filter=None):
        ''' List user readable pages under current page

        Currently only request.rootpage is used to list pages, but if we
        have true sub pages, any page can list its sub pages.

        The default behavior is listing all the pages readable by the
        current user. If you want to get a page list for another user,
        specify the user name.

        If you want to get the full page list, without user filtering,
        call with user="". Use this only if really needed, and do not
        display pages the user can not read.

        filter is usually compiled re match or search method, but can be
        any method that get a unicode argument and return bool. If you
        want to filter the page list, do it with this filter function,
        and NOT on the output of this function. page.exists() and
        user.may.read are very expensive, and should be done on the
        smallest data set.

        Filter those annoying /MoinEditorBackup pages.

        @param user: the user requesting the pages (MoinMoin.user.User)
        @param filter: filter function
        @param exits: filter existing pages
        @rtype: list of unicode strings
        @return: user readable wiki page names
        '''
        request = self.request
        request.clock.start('getPageList')
        # Check input
        if user is None:
            user = request.user

        # Get pages cache or create it
        cache = request.pages
        if not cache:
            for name in self._listPages():
                # Unquote file system names
                pagename = wikiutil.unquoteWikiname(name)

                # Filter those annoying editor backups
                if pagename.endswith(u'/MoinEditorBackup'):
                    continue

                cache[pagename] = None

        if user or exists or filter:
            # Filter names
            pages = []
            for name in cache:
                # First, custom filter - exists and acl check are very
                # expensive!
                if filter and not filter(name):
                    continue

                # Filter deleted pages
                if exists and not Page(request, name).exists():
                    continue

                # Filter out page user may not read.
                if user and not user.may.read(name):
                    continue

                pages.append(name)
        else:
            pages = cache.keys()

        request.clock.stop('getPageList')
        return pages

    def getPageDict(self, user=None, exists=1, filter=None):
        """ Return a dictionary of filtered page objects readable by user

        Invoke getPageList then create a dict from the page list. See
        getPageList docstring for more details.

        @param user: the user requesting the pages
        @param filter: filter function
        @param exits: only existing pages
        @rtype: dict {unicode: Page}
        @return: user readable pages
        """
        pages = {}
        for name in self.getPageList(user=user, exists=exists, filter=filter):
            pages[name] = Page(self.request, name)
        return pages

    def _listPages(self):
        """ Return a list of file system page names

        This is the lowest level disk access, don't use it unless you
        really need it.

        NOTE: names are returned in file system encoding, not in unicode!

        @rtype: dict
        @return: dict of page names using file system encoding
        """
        # Get pages in standard dir
        path = self.getPagePath('pages')
        pages = self._listPageInPath(path)

        if self.cfg.data_underlay_dir is not None:
            # Merge with pages from underlay
            path = self.getPagePath('pages', use_underlay=1)
            underlay = self._listPageInPath(path)
            pages.update(underlay)

        return pages

    def _listPageInPath(self, path):
        """ List page names in domain, using path

        This is the lowest level disk access, don't use it unless you
        really need it.

        NOTE: names are returned in file system encoding, not in unicode!

        @param path: directory to list (string)
        @rtype: dict
        @return: dict of page names using file system encoding
        """
        import dircache

        pages = {}
        for name in dircache.listdir(path):
            # Filter non-pages in quoted wiki names
            # List all pages in pages directory - assume flat namespace
            if name.startswith('.') or name.startswith('#') or name == 'CVS':
                continue

            pages[name] = None

        return pages

    def getlines(self):
        lines = self.get_raw_body().split('\n')
        return lines

    def get_raw_body(self):
        """
        Load the raw markup from the page file.

        @rtype: string
        @return: raw page contents of this page
        """
        if self._raw_body is None:
            # try to open file
            try:
                file = codecs.open(self._text_filename(), 'rb', config.charset)
            except IOError, er:
                import errno
                if er.errno == errno.ENOENT:
                    # just doesn't exist, return empty text (note that we
                    # never store empty pages, so this is detectable and also
                    # safe when passed to a function expecting a string)
                    return ""
                else:
                    raise er

            # read file content and make sure it is closed properly
            try:
                text = file.read()
                text = self.decodeTextMimeType(text)
                self.set_raw_body(text)
            finally:
                file.close()

        return self._raw_body

    def set_raw_body(self, body, modified=0):
        """ Set the raw body text (prevents loading from disk).

        TODO: this should not be a public function, as Page is immutable.

        @param body: raw body text
        @param modified: 1 means that we internally modified the raw text and
                         that it is not in sync with the page file on disk.
                         This is used e.g. by PageEditor when previewing the page.
        """
        self._raw_body = body
        self._raw_body_modified = modified

    def url(self, request, querystr=None, escape=1):
        """ Return complete URL for this page, including scriptname

        @param request: the request object
        @param querystr: the query string to add after a "?" after the url
            (str or dict, see util.web.makeQueryString)
        @param escpae: escape url for html, to be backward compatible
            with old code (bool)
        @rtype: str
        @return: complete url of this page, including scriptname
        """
        url = '%s/%s' % (request.getScriptname(),
                     wikiutil.quoteWikinameURL(self.page_name))

        if querystr:
            querystr = web.makeQueryString(querystr)

            # TODO: remove in 1.4
            # Escape query string to be compatible with old 3rd party code
            # New code should call with escape=0 to prevent the warning.
            if escape:
                import warnings
                warnings.warn("In moin 1.4 query string in url will not be"
                              " escaped. See"
                              " http://moinmoin.wikiwikiweb.de/ApiChanges")
                querystr = wikiutil.escape(querystr)

            url = '%s?%s' % (url, querystr)

        return url

    def link_to(self, request, text=None, querystr=None, anchor=None, **kw):
        """ Return HTML markup that links to this page.

        See wikiutil.link_tag() for possible keyword parameters.

        @param request: the request object
        @param text: inner text of the link - it gets automatically escaped
        @param querystr: the query string to add after a "?" after the url
        @param anchor: if specified, make a link to this anchor
        @keyword on: opening/closing tag only
        @keyword attachment_indicator: if 1, add attachment indicator after link tag
        @keyword css_class: css class to use
        @rtype: string
        @return: formatted link
        """
        if not text:
            text = self.split_title(request)

        # Create url, excluding scriptname
        url = wikiutil.quoteWikinameURL(self.page_name)
        if querystr:
            querystr = web.makeQueryString(querystr)
            # makeQueryString does not escape any more
            querystr = wikiutil.escape(querystr)
            url = "%s?%s" % (url, querystr)

        # Add anchor
        if anchor:
            url = "%s#%s" % (url, urllib.quote_plus(anchor.encode(config.charset)))

        # Add css class for non existing page
        if not self.exists():
            kw['css_class'] = 'nonexistent'

        link = wikiutil.link_tag(request, url, wikiutil.escape(text),
                                 formatter=getattr(self, 'formatter', None), **kw)

        # Create a link to attachments if any exist
        if kw.get('attachment_indicator', 0):
            from MoinMoin.action import AttachFile
            link += AttachFile.getIndicator(request, self.page_name)

        return link

    def getSubscribers(self, request, **kw):
        """
        Get all subscribers of this page.

        @param request: the request object
        @keyword include_self: if 1, include current user (default: 0)
        @keyword return_users: if 1, return user instances (default: 0)
        @keyword trivial: if 1, only include users who want trivial changes (default: 0)
        @rtype: dict
        @return: lists of subscribed email addresses in a dict by language key
        """
        include_self = kw.get('include_self', self.include_self)
        return_users = kw.get('return_users', 0)
        trivial = kw.get('trivial', 0)

        # extract categories of this page
        pageList = self.getCategories(request)

        # add current page name for list matching
        pageList.append(self.page_name)

        if self.cfg.SecurityPolicy:
            UserPerms = self.cfg.SecurityPolicy
        else:
            from security import Default as UserPerms

        # get email addresses of the all wiki user which have a profile stored;
        # add the address only if the user has subscribed to the page and
        # the user is not the current editor
        # Also, if the change is trivial (send email isn't ticked) only send email to users
        # who want_trivial changes (typically Admins on public sites)
        userlist = user.getUserList(request)
        subscriber_list = {}
        for uid in userlist:
            if uid == request.user.id and not include_self: continue # no self notification
            subscriber = user.User(request, uid)

            # This is a bit wrong if return_users=1 (which implies that the caller will process
            # user attributes and may, for example choose to send an SMS)
            # So it _should_ be "not (subscriber.email and return_users)" but that breaks at the moment.
            if not subscriber.email: continue # skip empty email addresses
            if trivial and not subscriber.want_trivial: continue # skip uninterested subscribers

            if not UserPerms(subscriber).read(self.page_name): continue

            if subscriber.isSubscribedTo(pageList):
                lang = subscriber.language or 'en'
                if not subscriber_list.has_key(lang): subscriber_list[lang] = []
                if return_users:
                    subscriber_list[lang].append(subscriber)
                else:
                    subscriber_list[lang].append(subscriber.email)

        return subscriber_list


    def send_page(self, request, msg=None, **keywords):
        """
        Output the formatted page.

        @param request: the request object
        @param msg: if given, display message in header area
        @keyword content_only: if 1, omit page header and footer
        @keyword content_id: set the id of the enclosing div
        @keyword count_hit: if 1, add an event to the log
        @keyword send_missing_page: if 1, assume that page to be sent is MissingPage
        """
        from MoinMoin import i18n
        request.clock.start('send_page')
        _ = request.getText

        # determine modes
        print_mode = request.form.has_key('action') and request.form['action'][0] == 'print'
        if print_mode:
            media = request.form.has_key('media') and request.form['media'][0] or 'print'
        else:
            media = 'screen'
        content_only = keywords.get('content_only', 0)
        content_id = keywords.get('content_id', 'content')
        do_cache = keywords.get('do_cache', 1)
        send_missing_page = keywords.get('send_missing_page', 0)
        if request.form.has_key('highlight'):
            self.hilite_re = request.form['highlight'][0]
        else:
            self.hilite_re = None
        if msg is None: msg = ""

        # count hit?
        if keywords.get('count_hit', 0):
            eventlog.EventLog(request).add(request, 'VIEWPAGE', {'pagename': self.page_name})

        # load the text
        body = self.get_raw_body()

        # if necessary, load the default formatter
        if self.default_formatter:
            from MoinMoin.formatter.text_html import Formatter
            self.formatter = Formatter(request, store_pagelinks=1)
        self.formatter.setPage(self)
        if self.hilite_re: self.formatter.set_highlight_re(self.hilite_re)
        request.formatter = self.formatter

        # default is wiki markup
        pi_format = self.cfg.default_markup or "wiki"
        pi_formatargs = ''
        pi_redirect = None
        pi_refresh = None
        pi_formtext = []
        pi_formfields = []
        wikiform = None

        # check for XML content
        if body and body[:5] == '<?xml':
            pi_format = "xslt"

        # check processing instructions
        while body and body[0] == '#':
            # extract first line
            try:
                line, body = body.split('\n', 1)
            except ValueError:
                line = body
                body = ''

            # end parsing on empty (invalid) PI
            if line == "#":
                body = line + '\n' + body
                break

            # skip comments (lines with two hash marks)
            if line[1] == '#': continue

            # parse the PI
            verb, args = (line[1:]+' ').split(' ', 1)
            verb = verb.lower()
            args = args.strip()

            # check the PIs
            if verb == "format":
                # markup format
                pi_format, pi_formatargs = (args+' ').split(' ',1)
                pi_format = pi_format.lower()
                pi_formatargs = pi_formatargs.strip()
            elif verb == "refresh":
                if self.cfg.refresh:
                    try:
                        mindelay, targetallowed = self.cfg.refresh
                        args = args.split()
                        if len(args) >= 1:
                            delay = max(int(args[0]), mindelay)
                        if len(args) >= 2:
                            target = args[1]
                        else:
                            target = self.page_name
                        if target.find('://') >= 0:
                            if targetallowed == 'internal':
                                raise ValueError
                            elif targetallowed == 'external':
                                url = target
                        else:
                            url = Page(request, target).url(request)
                        pi_refresh = {'delay': delay, 'url': url, }
                    except (ValueError,):
                        pi_refresh = None
            elif verb == "redirect":
                # redirect to another page
                # note that by including "action=show", we prevent
                # endless looping (see code in "request") or any
                # cascaded redirection
                pi_redirect = args
                if request.form.has_key('action') or request.form.has_key('redirect') or content_only: continue

                request.http_redirect('%s/%s?action=show&redirect=%s' % (
                    request.getScriptname(),
                    wikiutil.quoteWikinameURL(pi_redirect),
                    urllib.quote_plus(self.page_name.encode(config.charset), ''),))
                return
            elif verb == "deprecated":
                # deprecated page, append last backup version to current contents
                # (which should be a short reason why the page is deprecated)
                msg = '%s<strong>%s</strong><br>%s' % (
                    self.formatter.smiley('/!\\'),
                    _('The backupped content of this page is deprecated and will not be included in search results!'),
                    msg)

                revisions = self.getRevList()
                if len(revisions) >= 2: # XXX shouldn't that be ever the case!? Looks like not.
                    oldpage = Page(request, self.page_name, rev=revisions[1])
                    body += oldpage.get_raw_body()
                    del oldpage
            elif verb == "pragma":
                # store a list of name/value pairs for general use
                try:
                    key, val = args.split(' ', 1)
                except (ValueError, TypeError):
                    pass
                else:
                    request.setPragma(key, val)
            elif verb == "form":
                # ignore form PIs on non-form pages
                if not wikiutil.isFormPage(request, self.page_name):
                    continue

                # collect form definitions
                if not wikiform:
                    from MoinMoin import wikiform
                    # TODO: form probably can work with action=""
                    pi_formtext.append('<table border="1" cellspacing="1" cellpadding="3">\n'
                        '<form method="POST" action="%s">\n'
                        '<input type="hidden" name="action" value="formtest">\n' % self.url(request))
                pi_formtext.append(wikiform.parseDefinition(request, args, pi_formfields))
            elif verb == "acl":
                # We could build it here, but there's no request.
                pass
            elif verb == "language":
                # Page language. Check if args is a known moin language
                if args in i18n.wikiLanguages():
                    self.language = args
                    request.setContentLanguage(self.language)
            else:
                # unknown PI ==> end PI parsing, and show invalid PI as text
                body = line + '\n' + body
                break

        # Save values for later use
        self.pi_format = pi_format

        # start document output
        doc_leader = self.formatter.startDocument(self.page_name)
        page_exists = self.exists()
        if not content_only:
            # send the document leader
            if page_exists:
                request.http_headers()
            else:
                request.http_headers(['Status: 404 NOTFOUND'])
                request.setResponseCode(404)
            request.write(doc_leader)

            # send the page header
            if self.default_formatter:
                full_text_query = 'linkto:"%s"' % self.page_name
                link = '%s/%s?action=fullsearch&amp;value=%s&amp;context=180' % (
                    request.getScriptname(),
                    wikiutil.quoteWikinameURL(self.page_name),
                    urllib.quote_plus(full_text_query.encode(config.charset)))

                title = self.split_title(request)
                if self.rev:
                    msg = "<strong>%s</strong><br>%s" % (
                        _('Revision %(rev)d as of %(date)s') % {
                            'rev': self.rev,
                            'date': self.mtime_printable(request)
                        }, msg)

                # This redirect message is very annoying.
                # Less annoying now without the warning sign.
                if request.form.has_key('redirect'):
                    redir = request.form['redirect'][0]
                    msg = '<strong>%s</strong><br>%s' % (
                        _('Redirected from page "%(page)s"') % {'page':
                            wikiutil.link_tag(request, wikiutil.quoteWikinameURL(redir) + "?action=show", self.formatter.text(redir))},
                        msg)
                if pi_redirect:
                    msg = '<strong>%s</strong><br>%s' % (
                        _('This page redirects to page "%(page)s"') % {'page': wikiutil.escape(pi_redirect)},
                        msg)


                # Page trail
                trail = None
                if not print_mode:
                    request.user.addTrail(self.page_name)
                    trail = request.user.getTrail()

                wikiutil.send_title(request, title,  page=self, link=link, msg=msg,
                                    pagename=self.page_name, print_mode=print_mode,
                                    media=media, pi_refresh=pi_refresh,
                                    allow_doubleclick=1, trail=trail,
                                    )

                # user-defined form preview?
                # TODO: check if this is also an RTL form - then add ui_lang_attr
                if pi_formtext:
                    pi_formtext.append('<input type="hidden" name="fieldlist" value="%s">\n' %
                        "|".join(pi_formfields))
                    pi_formtext.append('</form></table>\n')
                    pi_formtext.append(_(
                        '~-If you submit this form, the submitted values'
                        ' will be displayed.\nTo use this form on other pages, insert a\n'
                        '[[BR]][[BR]]\'\'\'{{{    [[Form("%(pagename)s")]]}}}\'\'\'[[BR]][[BR]]\n'
                        'macro call.-~\n'
                    ) % {'pagename': self.formatter.text(self.page_name)})
                    request.write(''.join(pi_formtext))

        # try to load the parser
        Parser = wikiutil.importPlugin(self.request.cfg, "parser",
                                       self.pi_format, "Parser")
        if Parser is None:
            # default to plain text formatter (i.e. show the page source)
            del Parser
            from parser.plain import Parser

        # start wiki content div
        request.write(self.formatter.startContent(content_id))

        # new page?
        if not page_exists and (not content_only or (content_only
                                                     and send_missing_page)):
            if self.default_formatter and not content_only:
                self._emptyPageText(request)
            elif content_only and send_missing_page:
                # We should send MissingPage but it is not there
                import warnings
                warnings.warn("Error - The page MissingPage could not be found."
                              " Check your underlay directory setting.")
                url = '%s?action=edit' % wikiutil.quoteWikinameURL(self.page_name)
                request.write(wikiutil.link_tag(self.request, url, text=_("Create New Page"),
                                                formatter=self.formatter))
        elif not request.user.may.read(self.page_name):
            request.write("<strong>%s</strong><br>" % _("You are not allowed to view this page."))
        else:
            # parse the text and send the page content
            self.send_page_content(request, Parser, body, format_args=pi_formatargs, do_cache=do_cache)

            # check for pending footnotes
            if getattr(request, 'footnotes', None):
                from MoinMoin.macro.FootNote import emit_footnotes
                request.write(emit_footnotes(request, self.formatter))

        # end wiki content div
        request.write(self.formatter.endContent())

        # end document output
        doc_trailer = self.formatter.endDocument()
        if not content_only:
            # send the page footer
            if self.default_formatter:
                wikiutil.send_footer(request, self.page_name, print_mode=print_mode)

            request.write(doc_trailer)

        # cache the pagelinks
        if do_cache and self.default_formatter and page_exists:
            cache = caching.CacheEntry(request, self, 'pagelinks')
            if cache.needsUpdate(self._text_filename()):
                links = self.formatter.pagelinks
                cache.update('\n'.join(links) + '\n', True)

        request.clock.stop('send_page')

    def getFormatterName(self):
        """ Return a formatter name, used in the caching system

        @rtype: string
        @return: formatter name as used in caching
        """
        if not hasattr(self, 'formatter'):
            return ''

        name = str(self.formatter.__class__)
        name = name.replace('MoinMoin.formatter.', '').replace('.Formatter', '')
        return name

    def canUseCache(self, parser=None):
        """ Is caching available for this request?

        This make sure we can try to use the caching system for this
        request, but it does not make sure that this will
        succeed. Themes can use this to decide if a Refresh action
        should be displayed.

        @param parser: the parser used to render the page
        @rtype: bool
        @return: if this page can use caching
        """
        if (not self.rev and
            not self.hilite_re and
            not self._raw_body_modified and
            self.getFormatterName() in self.cfg.caching_formats):
            # Everything is fine, now check the parser:
            if not parser:
                parser = wikiutil.importPlugin(self.request.cfg, "parser",
                                               self.pi_format, "Parser")
            return getattr(parser, 'caching', False)

        return False

    def send_page_content(self, request, Parser, body, needsupdate=0,
                          format_args='', do_cache=1):
        # XXX CFG remove request param? self.request ?
        """
        Output the formatted wiki page, using caching, if possible.

        @param request: the request object
        @param Parser: the Parser
        @param body: text of the wiki page
        @param needsupdate: if 1, force update of the cached compiled page
        """
        request.clock.start('send_page_content')

        formatter_name = self.getFormatterName()

        # if we should not or can not use caching
        if not (do_cache and self.canUseCache(Parser)):
            # parse the text and send the page content
            Parser(body, request, format_args=format_args).format(self.formatter)
            request.clock.stop('send_page_content')
            return

        #try cache
        _ = request.getText
        from MoinMoin import wikimacro
        arena = self
        key = formatter_name
        cache = caching.CacheEntry(request, arena, key)
        code = None

        if cache.needsUpdate(self._text_filename(),
                             self.getPagePath('attachments', check_create=0)):
            needsupdate = 1

        # load cache
        if not needsupdate:
            try:
                import marshal
                code = marshal.loads(cache.content())
            except (EOFError, ValueError, TypeError), err:
                # Bad marshal data, must update the cache.
                # See http://docs.python.org/lib/module-marshal.html
                needsupdate = 1
            except:
                # Log unexpected errors
                import sys
                err = sys.exc_info()[1]
                err = ('Unexpected error while trying to load "%(pagename)s"'
                       ' cache: %(errorname)s: %(error)s\n') % {
                    'pagename': self.page_name.encode(config.charset),
                    'errorname': err.__class__.__name__,
                    'error': str(err),
                    }
                request.log(err)
                # And also update the cache
                needsupdate = 1

        # render page
        if needsupdate:
            # Save request state before - rendering page might
            # change request state!
            saved_current_lang = request.current_lang

            from MoinMoin.formatter.text_python import Formatter
            formatter = Formatter(request, ["page"], self.formatter)

            import marshal
            buffer = StringIO.StringIO()
            request.redirect(buffer)
            parser = Parser(body, request)
            parser.format(formatter)
            request.redirect()
            text = buffer.getvalue()
            buffer.close()
            src = formatter.assemble_code(text)
            ## request.write(src) # debug
            code = compile(src.encode(config.charset),
                           self.page_name.encode(config.charset), 'exec')
            cache.update(marshal.dumps(code))

            # Restore request state
            request.current_lang = saved_current_lang

        # send page
        formatter = self.formatter
        parser = Parser(body, request)
        macro_obj = wikimacro.Macro(parser)

        try:
            # if this code module is in a .zip file, mess with __file__
            # in order to get caching right
            moinmodule = __import__('MoinMoin')
            if hasattr(moinmodule, '__loader__'):
                __file__ = os.path.join(moinmodule.__loader__.archive, 'dummy')

            exec code
        except 'CacheNeedsUpdate':
            # if something goes wrong, try without caching
            # Prevent wrong timing in recursive calls
            request.clock.stop('send_page_content')
            self.send_page_content(request, Parser, body, needsupdate=1)
            request.clock.start('send_page_content')
            cache = caching.CacheEntry(request, arena, key)

        # Save my cache modification time, this info might be used by
        # themes - but only after the page content was sent.
        self.cache_mtime = cache.mtime()

        # TODO: move this into theme (currently used only by classic)
        url = wikiutil.quoteWikinameURL(self.page_name) + '?action=refresh'
        link = wikiutil.link_tag(request, url, _("DeleteCache", formatted=False))
        date = self.request.user.getFormattedDateTime(cache.mtime())
        fragment = link + ' ' +  _('(cached %s)') % date
        self.request.add2footer('DeleteCache', fragment)

        request.clock.stop('send_page_content')

    def _emptyPageText(self, request):
        """
        Output the default page content for new pages.

        @param request: the request object
        """
        missingpage = wikiutil.getSysPage(request, 'MissingPage')
        missingpagefn = missingpage._text_filename()
        missingpage.page_name = self.page_name
        missingpage._text_filename_force = missingpagefn
        missingpage.send_page(request, content_only=1, send_missing_page=1)


    def getRevList(self):
        """
        Get a page revision list of this page, including the current version,
        sorted by revision number in descending order (current page first).

        @rtype: list of ints
        @return: page revisions
        """
        import dircache
        revisions = []
        if self.page_name:
            rev_dir = self.getPagePath('revisions', check_create=0)
            if os.path.isdir(rev_dir):
                for rev in dircache.listdir(rev_dir):
                    try:
                        revint = int(rev)
                        revisions.append(revint)
                    except ValueError:
                        pass
                revisions.sort()
                revisions.reverse()
        return revisions

    def olderrevision(self, rev=0):
        """
        Get revision of the next older page revision than rev.
        rev == 0 means this page objects revision (that may be an old
        revision already!)
        """
        if rev == 0:
            rev = self.rev
        revisions = self.getRevList()
        for r in revisions:
            if r < rev:
                older = r
                break
        return older

    def getPageText(self, start=0, length=None):
        """ Convenience function to get the page text, skipping the header

        @rtype: unicode
        @return: page text, excluding the header
        """

        # Lazy compile regex on first use. All instances share the
        # same regex, compiled once when the first call in an instance is done.
        if isinstance(self.__class__.header_re, (str, unicode)):
            self.__class__.header_re = re.compile(self.__class__.header_re, re.MULTILINE | re.UNICODE)

        body = self.get_raw_body() or ''
        header = self.header_re.search(body)
        if header:
            start += header.end()

        # Return length characters from start of text
        if length is None:
            return body[start:]
        else:
            return body[start:start + length]

    def getPageHeader(self, start=0, length=None):
        """ Convenience function to get the page header

        @rtype: unicode
        @return: page header
        """

        # Lazy compile regex on first use. All instances share the
        # same regex, compiled once when the first call in an instance is done.
        if isinstance(self.__class__.header_re, (str, unicode)):
            self.__class__.header_re = re.compile(self.__class__.header_re, re.MULTILINE | re.UNICODE)

        body = self.get_raw_body() or ''
        header = self.header_re.search(body)
        if header:
            text = header.group()
            # Return length characters from start of text
            if length is None:
                return text[start:]
            else:
                return text[start:start + length]
        return ''

    def getPageLinks(self, request):
        """ Get a list of the links on this page.

        @param request: the request object
        @rtype: list
        @return: page names this page links to
        """
        if not self.exists():
            return []
        cache = caching.CacheEntry(request, self, 'pagelinks')
        if cache.needsUpdate(self._text_filename()):
            links = self.parsePageLinks(request)
            cache.update('\n'.join(links) + '\n', True)
            return links
        return cache.content(True).split('\n')

    def parsePageLinks(self, request):
        """ Parse page links by formatting with a pagelinks formatter 
        
        This is a old hack to get the pagelinks by rendering the page
        with send_page. We can remove this hack after factoring
        send_page and send_page_content into small reuseable methods.
        
        More efficient now by using special pagelinks formatter and
        redirecting possible output into null file.
        """
        request.clock.start('parsePagelinks')
        class Null:
            def write(self, str): pass
        request.redirect(Null())
        request.mode_getpagelinks = 1
        try:
            try:
                from MoinMoin.formatter.pagelinks import Formatter
                formatter = Formatter(request, store_pagelinks=1)
                page = Page(request, self.page_name, formatter=formatter)
                page.send_page(request, content_only=1)
            except:
                import traceback
                traceback.print_exc()
        finally:
            request.mode_getpagelinks = 0
            request.redirect()
            if hasattr(request, '_fmt_hd_counters'):
                del request._fmt_hd_counters
            request.clock.stop('parsePagelinks')
        return formatter.pagelinks

    def getCategories(self, request):
        """ Get categories this page belongs to.

        @param request: the request object
        @rtype: list
        @return: categories this page belongs to
        """
        return wikiutil.filterCategoryPages(request, self.getPageLinks(request))

    def getParentPage(self):
        """ Return parent page or None

        @rtype: Page
        @return: parent page or None
        """
        if config.allow_subpages and self.page_name:
            pos = self.page_name.rfind('/')
            if pos > 0:
                parent = Page(self.request, self.page_name[:pos])
                if parent.exists():
                    return parent
        return None

    def getACL(self, request):
        """ Get cached ACLs of this page.
        
        Return cached ACL or invoke parseACL and update the cache.

        @param request: the request object
        @rtype: MoinMoin.wikiacl.AccessControlList
        @return: ACL of this page
        """
        import wikiacl
        # Return new empty acl when acl is not enabled
        if not self.cfg.acl_enabled:
            return wikiacl.AccessControlList(request)
        request.clock.start('getACL')
        # Try the cache or parse acl and update the cache
        currentRevision = self.current_rev()
        key = self.page_name
        try:
            aclRevision, acl = request.cfg._acl_cache.get(key, (None, None))
        except AttributeError:
            request.cfg._acl_cache = {}
            aclRevision, acl = None, None
        if aclRevision != currentRevision:
            acl = self.parseACL()
            request.cfg._acl_cache[key] = (currentRevision, acl)
        request.clock.stop('getACL')
        return acl

    def parseACL(self):
        """ Return ACLs parsed from the last available revision 
        
        The effective ACL is always from the last revision, even if
        you access an older revision.
        """
        import wikiacl
        if self.exists() and self.rev == 0:
            return wikiacl.parseACL(self.request, self.get_raw_body())
        try:
            lastRevision = self.getRevList()[0]
        except IndexError:
            return wikiacl.AccessControlList(self.request)
        body = Page(self.request, self.page_name,
                    rev=lastRevision).get_raw_body()
        return wikiacl.parseACL(self.request, body)

    def clean_acl_cache(self):
        """
        Clean ACL cache entry of this page (used by PageEditor on save)
        """
        request = self.request
        key = self.page_name
        try:
            del request.cfg._acl_cache[key]
        except KeyError:
            pass
        except AttributeError:
            request.cfg._acl_cache = {}

    # Text format -------------------------------------------------------

    def encodeTextMimeType(self, text):
        """ Encode text from moin internal representation to text/* mime type

        Make sure text uses CRLF line ends, keep trailing newline.

        @param text: text to encode (unicode)
        @rtype: unicode
        @return: encoded text
        """
        if text:
            lines = text.splitlines()
            # Keep trailing newline
            if text.endswith(u'\n') and not lines[-1] == u'':
                lines.append(u'')
            text = u'\r\n'.join(lines)
        return text

    def decodeTextMimeType(self, text):
        """ Decode text from text/* mime type to moin internal representation

        @param text: text to decode (unicode). Text must use CRLF!
        @rtype: unicode
        @return: text using internal representation
        """
        text = text.replace(u'\r', u'')
        return text


