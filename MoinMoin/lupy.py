# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - lupy indexing search engine

    @copyright: 2005 by Florian Festi, Nir Soffer
    @license: GNU GPL, see COPYING for details.
"""

import os, re, codecs, errno, time

from MoinMoin.Page import Page
from MoinMoin import config
from MoinMoin.util import filesys, lock
from MoinMoin.support.lupy.index.term import Term
from MoinMoin.support.lupy import document
from MoinMoin.support.lupy.index.indexwriter import IndexWriter
from MoinMoin.support.lupy.search.indexsearcher import IndexSearcher

##############################################################################
### Tokenizer
##############################################################################

word_re = re.compile(r"\w+", re.U)
wikiword_re = re.compile(r"^([%(u)s][%(l)s]+)+$" % {'u': config.chars_upper,
                                                'l': config.chars_lower}, re.U)
singleword_re = re.compile(r"[%(u)s][%(l)s]+" % {'u': config.chars_upper,
                                             'l': config.chars_lower}, re.U)

token_re = re.compile(
    r"(?P<company>\w+[&@]\w+)|" + #company names like AT&T and Excite@Home.
    r"(?P<email>\w+([.-]\w+)*@\w+([.-]\w+)*)|" +    # email addresses
    r"(?P<hostname>\w+(\.\w+)+)|" +                 # hostnames
    r"(?P<num>(\w+[-/.,])*\w*\d\w*([-/.,]\w+)*)|" + # version numbers
    r"(?P<acronym>(\w\.)+)|" +          # acronyms: U.S.A., I.B.M., etc.
    r"(?P<word>\w+)",                   # words
    re.U)

dot_re = re.compile(r"[-_/,.]")
mail_re = re.compile(r"[-_/,.]|(@)")

def tokenizer(value):
    """Yield a stream of lower cased words from a string."""
    if isinstance(value, list): # used for page links
        for v in value:
            yield v
    else:
        tokenstream = re.finditer(token_re, value)
        for m in tokenstream:
            if m.group("acronym"):
                yield m.group("acronym").replace('.','').lower()
            elif m.group("company"):
                yield m.group("company").lower()
            elif m.group("email"):
                for word in mail_re.split(m.group("email").lower()):
                    if word:
                        yield word
            elif m.group("hostname"):                
                for word in dot_re.split(m.group("hostname").lower()):
                    yield word
            elif m.group("num"):
                for word in dot_re.split(m.group("num").lower()):
                    yield word
            elif m.group("word"):
                if wikiword_re.match(m.group("word")):
                    for sm in re.finditer(singleword_re, m.group()):
                        yield sm.group().lower()
                else:
                    yield  m.group("word").lower()


#############################################################################
### Indexing
#############################################################################

class UpdateQueue:
    def __init__(self, file, lock_dir):
        self.file = file
        self.writeLock = lock.WriteLock(lock_dir, timeout=10.0)
        self.readLock = lock.ReadLock(lock_dir, timeout=10.0)

    def exists(self):
        return os.path.exists(self.file)

    def append(self, pagename):
        """ Append a page to queue 
        
        TODO: tune timeout
        """
        if not self.writeLock.acquire(60.0):
            request.log("can't add %r to lupy update queue: can't lock queue" %
                        pagename)
            return
        try:
            f = codecs.open(self.file, 'a', config.charset)
            try:
                f.write(pagename + "\n")
            finally:
                f.close()                
        finally:
            self.writeLock.release()

    def pages(self):
        """ Return list of pages in the queue 
        
        TODO: tune timeout
        """
        if self.readLock.acquire(1.0):
            try:
                return self._decode(self._read())
            finally:
                self.readLock.release()            
        return []

    def remove(self, pages):
        """ Remove pages from the queue
        
        When the queue is empty, the queue file is removed, so exists()
        can tell if there is something waiting in the queue.
        
        TODO: tune the timeout
        """
        if self.writeLock.acquire(30.0):
            try:
                queue = self._decode(self._read())
                for page in pages:
                    try:
                        queue.remove(page)
                    except ValueError:
                        pass
                if queue:
                    self._write(queue)
                else:
                    self._removeFile()
                return True
            finally:
                self.writeLock.release()
        return False

    # Private -------------------------------------------------------

    def _decode(self, data):
        """ Decode queue data """
        pages = data.splitlines()
        return self._filterDuplicates(pages)

    def _filterDuplicates(self, pages):
        """ Filter duplicates in page list, keeping the order """
        unique = []
        seen = {}
        for name in pages:
            if name in seen:
                continue
            unique.append(name)
            seen[name] = 1
        return unique

    def _read(self):
        """ Read and return queue data
        
        This does not do anything with the data so we can release the
        lock as soon as possible, enabling others to update the queue.
        """
        try:
            f = codecs.open(self.file, 'r', config.charset)
            try:
                return f.read()
            finally:
                f.close()
        except (OSError, IOError), err:
            if err.errno != errno.ENOENT:
                raise
            return ''

    def _write(self, pages):
        """ Write pages to queue file
        
        Require queue write locking.
        """
        # XXX use tmpfile/move for atomic replace on real operating systems
        data = '\n'.join(pages) + '\n'
        f = codecs.open(self.file, 'w', config.charset)
        try:
            f.write(data)
        finally:
            f.close()            

    def _removeFile(self):
        """ Remove queue file 
        
        Require write locking.
        """
        try:
            os.remove(self.file)
        except OSError, err:
            if err.errno != errno.ENOENT:
                raise

class Index:
    class LockedException(Exception):
        pass
    
    def __init__(self, request):
        self.request = request
        cache_dir = request.cfg.cache_dir
        self.dir = os.path.join(cache_dir, 'lupy_index')
        filesys.makeDirs(self.dir)
        self.sig_file = os.path.join(self.dir, '__complete__')
        self.segments_file = os.path.join(self.dir, 'segments')
        lock_dir = os.path.join(cache_dir, 'lupy_index_lock')
        self.lock = lock.WriteLock(lock_dir,
                                   timeout=3600.0, readlocktimeout=60.0)
        self.read_lock = lock.ReadLock(lock_dir, timeout=3600.0)
        self.queue = UpdateQueue(os.path.join(self.dir, "__update_queue__"),
                                 os.path.join(cache_dir, 'lupy_queue_lock'))
        
        # Disabled until we have a sane way to build the index with a
        # queue in small steps.
        ## if not self.exists():
        ##    self.indexPagesInNewThread(request)

    def exists(self):
        """ Check if index exists """        
        return os.path.exists(self.sig_file)
                
    def mtime(self):
        return os.path.getmtime(self.segments_file)

    def search(self, query):
        if not self.read_lock.acquire(1.0):
            raise self.LockedException
        try:
            while True:
                try:
                    searcher, timestamp = self.request.cfg.lupy_searchers.pop()
                    if timestamp!=self.mtime():
                        searcher.close()
                    else:
                        break
                except IndexError:
                    searcher = IndexSearcher(self.dir)
                    timestamp = self.mtime()
                    break
                
            hits = list(searcher.search(query))
            self.request.cfg.lupy_searchers.append((searcher, timestamp))
        finally:
            self.read_lock.release()
        return hits

    def update_page(self, page):
        if not self.lock.acquire(1.0):
            self.queue.append(page.page_name)
            return
        self.request.clock.start('update_page')
        try:
            self._do_queued_updates()
            self._update_page(page)
        finally:
            self.lock.release()
        self.request.clock.stop('update_page')

    def indexPages(self):
        """ Index all pages
        
        Can be called only from a script. To index pages during a user
        request, use indexPagesInNewThread. 
        
        TODO: tune the acquire timeout
        """
        if not self.lock.acquire(1.0):
            self.request.log("can't index: can't acquire lock")
            return
        try:
            self._index_pages(self._indexingRequest(self.request))
        finally:
            self.lock.release()
    
    def indexPagesInNewThread(self):
        """ Index all pages in a new thread
        
        Should be called from a user request. From a script, use
        indexPages.

        TODO: tune the acquire timeout
        """
        if not self.lock.acquire(1.0):
            self.request.log("can't index: can't acquire lock")
            return
        try:
            # Prevent rebuilding the index just after it was finished
            if self.exists():
                self.lock.release()
                return
            from threading import Thread
            indexThread = Thread(target=self._index_pages,
                args=(self._indexingRequest(self.request), self.lock))
            indexThread.setDaemon(True)
            
            # Join the index thread after current request finish, prevent
            # Apache CGI from killing the process.
            def joinDecorator(finish):
                def func():
                    finish()
                    indexThread.join()
                return func
                
            self.request.finish = joinDecorator(self.request.finish)        
            indexThread.start()
        except:
            self.lock.release()
            raise

    def optimize(self):
        """ Optimize the index
        
        This may take from few seconds to few hours, depending on the
        size of the wiki. Currently it's usable only from a script.
        
        TODO: needs special locking, so the index is readable until the
        optimization is finished.
        """
        if not self.exists():
            raise RuntimeError("Index does not exist or is not finished")
        if not self.lock.acquire(1.0):
            self.request.log("can't lock the index for optimization")
            return
        try:
            self._optimize(self.request)
        finally:
            self.lock.release()

    # -------------------------------------------------------------------
    # Private

    def _do_queued_updates(self, amount=5):
        """ Assumes that the write lock is acquired """
        pages = self.queue.pages()[:amount]
        for name in pages:
            self._update_page(Page(self.request, name))
        self.queue.remove(pages)

    def _update_page(self, page):
        """ Assumes that the write lock is acquired """
        reader = IndexSearcher(self.dir)
        reader.reader.deleteTerm(Term('pagename', page.page_name))
        reader.close()
        if page.exists():
            writer = IndexWriter(self.dir, False, tokenizer)
            self._index_page(writer, page)
            writer.close()
        
    def _index_page(self, writer, page):
        """ Assumes that the write lock is acquired """
        d = document.Document()
        d.add(document.Keyword('pagename', page.page_name))
        d.add(document.Text('title', page.page_name, store=False))        
        d.add(document.Text('text', page.get_raw_body(), store=False))
        
        links = page.getPageLinks(page.request)
        t = document.Text('links', '', store=False)
        t.stringVal = links
        d.add(t)
        d.add(document.Text('link_text', ' '.join(links), store=False))

        writer.addDocument(d)

    def _index_pages(self, request, lock=None):
        """ Index all pages
        
        This should be called from indexPages or indexPagesInNewThread
        only!
        
        This may take few minutes up to few hours, depending on the
        size of the wiki.

        When called in a new thread, lock is acquired before the call,
        and this method must release it when it finishes or fails.
        """
        try:
            self._unsign()
            start = time.time()
            writer = IndexWriter(self.dir, True, tokenizer)
            writer.mergeFactor = 200
            pages = request.rootpage.getPageList(user='', exists=1)
            request.log("indexing all (%d) pages..." % len(pages))
            for pagename in pages:
                # Some code assumes request.page
                request.page = Page(request, pagename)
                self._index_page(writer, request.page)
            writer.close()
            request.log("indexing completed successfully in %0.2f seconds." % 
                        (time.time() - start))
            self._optimize(request)
            self._sign()
        finally:
            if lock:
                lock.release()

    def _optimize(self, request):
        """ Optimize the index """
        start = time.time()
        request.log("optimizing index...")
        writer = IndexWriter(self.dir, False, tokenizer)
        writer.optimize()
        writer.close()
        request.log("optimizing completed successfully in %0.2f seconds." % 
                    (time.time() - start))

    def _indexingRequest(self, request):
        """ Return a new request that can be used for index building.
        
        This request uses a security policy that lets the current user
        read any page. Without this policy some pages will not render,
        which will create broken pagelinks index.        
        """
        from MoinMoin.request import RequestCLI
        from MoinMoin.security import Permissions        
        request = RequestCLI(request.url)
        class SecurityPolicy(Permissions):            
            def read(*args, **kw):
                return True        
        request.user.may = SecurityPolicy(request.user)
        return request

    def _unsign(self):
        """ Remove sig file - assume write lock acquired """
        try:
            os.remove(self.sig_file)
        except OSError, err:
            if err.errno != errno.ENOENT:
                raise

    def _sign(self):
        """ Add sig file - assume write lock acquired """
        f = file(self.sig_file, 'w')
        try:
            f.write('')
        finally:
            f.close()

