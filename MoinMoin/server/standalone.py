# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - Stand-alone HTTP Server

    This is a simple, fast and very easy to install server. Its
    recommended for personal wikis or public wikis with little load.

    It is not well tested in public wikis with heavy load. In these case
    you might want to use twisted, fast cgi or mod python, or if you
    can't use those, cgi.
        
    Minimal usage:

        from MoinMoin.server.standalone import StandaloneConfig, run
        
        class Config(StandaloneConfig):
            docs = '/usr/share/moin/wiki/htdocs'
            user = 'www-data'
            group = 'www-data'
            
        run(Config)
        
    See more options in StandaloneConfig class.

    For security, the server will not run as root. If you try to run it
    as root, it will run as the user and group in the config. If you run
    it as a normal user, it will run with your regular user and group.

    Significant contributions to this module by R. Church <rc@ghostbitch.org>

    TODO: sends 'expires' header but browsers seems to ignore it,
    requesting the css and images on each request.

    @copyright: 2001-2004 MoinMoin:JürgenHermann
    @copyright: 2005      MoinMoin:AlexanderSchremmer
    @copyright: 2005      MoinMoin:NirSoffer
    @license: GNU GPL, see COPYING for details.
"""

# Imports
import os, sys, time, urllib, socket, errno, shutil
import BaseHTTPServer, SimpleHTTPServer, SocketServer
from email.Utils import formatdate

# MoinMoin imports
from MoinMoin import version
from MoinMoin.server import Config, switchUID
from MoinMoin.request import RequestStandAlone

# Server globals
httpd = None
config = None
moin_requests_done = 0


class SimpleServer(BaseHTTPServer.HTTPServer):
    """ Simplest server, serving one request after another
    
    This server is good for personal wiki, or when lowest memory
    footprint is needed.
    """    
    use_threads = False
    
    def __init__(self, config):
        self.htdocs = config.docs
        self.request_queue_size = config.requestQueueSize
        self._abort = 0
        address = (config.interface, config.port)
        BaseHTTPServer.HTTPServer.__init__(self, address, MoinRequestHandler)

    def server_activate(self):
        BaseHTTPServer.HTTPServer.server_activate(self)
        sys.stderr.write("Serving on %s:%d\n" % self.server_address)

    def serve_forever(self):
        """Handle one request at a time until we die """
        while not self._abort:
            self.handle_request()

    def die(self):
        """Abort this server instance's serving loop """
        # Close hotshot profiler
        if config.hotshotProfile:
            config.hotshotProfile.close()

        # Set abort flag, then make request to wake the server
        self._abort = 1
        try:
            import httplib
            req = httplib.HTTP('%s:%d' % self.server_address)
            req.connect()
            req.putrequest('DIE', '/')
            req.endheaders()
            del req
        except socket.error, err:
            # Ignore certain errors
            if err.args[0] not in [errno.EADDRNOTAVAIL,]:
                raise


class ThreadingServer(SimpleServer):
    """ Serve each request in a new thread 
    
    This server is used since release 1.3 and seems to work nice with
    little load.
    
    From release 1.3.5 there is a thread limit, that should help to
    limit the load on the server.
    """
    use_threads = True
    
    def __init__(self, config):
        self.thread_limit = config.threadLimit
        from threading import Condition
        self.lock = Condition()
        SimpleServer.__init__(self, config)

    def process_request(self, request, client_address):
        """ Start a new thread to process the request
        
        If the thread limit has been reached, wait on the lock. The
        next thread will notify when finished.
        """
        from threading import Thread, activeCount
        self.lock.acquire()
        try:
            if activeCount() > self.thread_limit:
                self.lock.wait()
            if self._abort:
                return
            t = Thread(target=self.process_request_thread,
                       args=(request, client_address))
            t.start()
        finally:
            self.lock.release()
    
    def process_request_thread(self, request, client_address):
        """ Called for each request on a new thread 
        
        Notify the main thread on the end of each request.
        """
        try:
            self.finish_request(request, client_address)
        except:
            self.handle_error(request, client_address)
        self.close_request(request)
        self.lock.acquire()
        try:
            # Main thread might be waiting
            self.lock.notify()
        finally:
            self.lock.release()


class ThreadPoolServer(SimpleServer):
    """ Threading server using a pool of threads 

    This is a new experimental server, using a pool of threads instead
    of creating new thread for each request. This is similar to Apache
    worker mpm, with a simpler constant thread pool.

    This server is 5 times faster than ThreadingServer for static
    files, and about the same for wiki pages.
    
    TODO: sometimes the server won't exit on Conrol-C, and continue to
    run with few threads (you can kill it with kill -9). Same problem
    exist with the twisted server. When the problem is finally solved,
    remove the commented debug prints.
    """
    use_threads = True
    
    def __init__(self, config):
        self.queue = []
        # The size of the queue need more testing
        self.queueSize = config.threadLimit * 2
        self.poolSize = config.threadLimit
        from threading import Condition
        self.lock = Condition()
        SimpleServer.__init__(self, config)

    def serve_forever(self):
        """ Create a thread pool then invoke base class method """
        from threading import Thread
        for i in range(self.poolSize):
            t = Thread(target=self.serve_forever_thread)
            t.start()
        SimpleServer.serve_forever(self)
        
    def process_request(self, request, client_address):
        """ Called for each request 
        
        Insert the request into the queue. If the queue is full, wait
        until one of the request threads pop a request. During the wait,
        new connections might be dropped.
        """
        self.lock.acquire()
        try:
            if len(self.queue) >= self.queueSize:
                self.lock.wait()
            if self._abort:
                return
            self.queue.insert(0, (request, client_address))
            self.lock.notify()
        finally:
            self.lock.release()       

    def serve_forever_thread(self):
        """ The main loop of request threads 
        
        Pop a request from the queue and process it.
        """
        while not self._abort:
            request, client_address = self.pop_request()
            try:
                self.finish_request(request, client_address)
            except:
                self.handle_error(request, client_address)
            self.close_request(request)            
        # sys.stderr.write('thread exiting...\n')
    
    def pop_request(self):
        """ Pop a request from the queue 
        
        If the queue is empty, wait for notification. If the queue was
        full, notify the main thread which may be waiting.
        """
        self.lock.acquire()
        try:
            while not self._abort:
                try:
                    item = self.queue.pop()
                    if len(self.queue) == self.queueSize - 1:
                        # Queue was full - main thread might be waiting
                        self.lock.notify()
                    return item
                except IndexError:
                    self.lock.wait()
        finally:
            self.lock.release()
        # sys.stderr.write('thread exiting...\n')
        sys.exit()        
        
    def die(self):
        """ Wake all threads then invoke base class die

        Threads should exist when _abort is True.
        """
        self._abort = True
        self.wake_all_threads()
        time.sleep(0.1)
        SimpleServer.die(self)

    def wake_all_threads(self):
        self.lock.acquire()
        try:
            # sys.stderr.write('waking up all threads...\n')
            self.lock.notifyAll()
        finally:
            self.lock.release()
   

class ForkingServer(SocketServer.ForkingMixIn, SimpleServer):
    """ Serve each request in a new process 
    
    This is new untested server, first tests show rather pathetic cgi
    like performance. No data is cached between requests.
    
    The mixin has its own process limit.
    """
    max_children = 10
    
    
class MoinRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):

    bufferSize = 8 * 1024 # used to server static files
    staticExpire =  7 * 24 * 3600 # 1 week
    
    def __init__(self, request, client_address, server):
        self.server_version = "MoinMoin %s %s" % (version.revision,
                                                  server.__class__.__name__)
        self.expires = 0
        SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self, request, 
            client_address, server)

    # -------------------------------------------------------------------
    # do_METHOD dispatchers - called for each request
    
    def do_DIE(self):
        if self.server._abort:
            self.log_error("Shutting down")

    def do_POST(self):
        self.serve_moin()

    def do_GET(self):
        """ Handle GET requests

        Separate between wiki pages and css and image url by similar
        system as cgi and twisted, the '/wiki/' url prefix.

        TODO: should use request.cfg.url_prefix - and not a constant but
        request is not available at this time.  Should be fixed by
        loading config earlier.
        """
        if self.path.startswith('/wiki/'):
            self.path = self.path[5:]
            self.serve_static_file()
        elif self.path in ['/favicon.ico', '/robots.txt']:
            self.serve_static_file()
        else:
            self.serve_moin()

    # -------------------------------------------------------------------    
    # Serve methods
    
    def serve_static_file(self):
        """ Serve files from the htdocs directory """
        self.expires = self.staticExpire
        try: 
            SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
        except socket.error, err:
            # Ignore certain errors
            if err.args[0] not in [errno.EPIPE, errno.ECONNABORTED]:
                raise
    
    def serve_moin(self):
        """ Serve a request using moin """
        global moin_requests_done

        # don't make an Expires header for wiki pages
        self.expires = 0
        
        # Run request, use optional profiling
        if config.memoryProfile:
            config.memoryProfile.addRequest()
        try:
            if config.hotshotProfile and moin_requests_done > 0:
                # Don't profile the first request, its not interesting
                # for long running process, and its very expensive.
                runcall = config.hotshotProfile.runcall
                req = runcall(RequestStandAlone, self)
                runcall(req.run)
            else:
                req = RequestStandAlone(self)
                req.run()
        except socket.error, err:
            # Ignore certain errors
            if err.args[0] not in [errno.EPIPE, errno.ECONNABORTED]:
                raise
        # Count moin requests
        moin_requests_done += 1
        
    def translate_path(self, uri):
        """ Translate a /-separated PATH to the local filename syntax.

        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.
        """
        file = urllib.unquote(uri)
        file.replace('\\', '/')
        words = file.split('/')
        words = filter(None, words)

        path = self.server.htdocs
        bad_uri = 0
        for word in words:
            drive, word = os.path.splitdrive(word)
            if drive:
                bad_uri = 1
            head, word = os.path.split(word)
            if word in (os.curdir, os.pardir):
                bad_uri = 1
                continue
            path = os.path.join(path, word)

        if bad_uri:
            self.log_error("Detected bad request URI '%s', translated to '%s'"
                           % (uri, path,))    
        return path

    def end_headers(self):
        """overload the default end_headers, inserting expires header"""
        if self.expires:
            now = time.time()
            expires = now + self.expires
            self.send_header('Expires', formatdate(expires))
        SimpleHTTPServer.SimpleHTTPRequestHandler.end_headers(self)
        
    def copyfile(self, source, outputfile):
        """Copy all data between two file objects.
        
        Modify the base class method to change the buffer size. Test
        show that for the typical static files we serve, 8K buffer is
        faster than the default 16K buffer.
        """
        shutil.copyfileobj(source, outputfile, length=self.bufferSize)
        

def quit(signo, stackframe):
    """ Signal handler for aborting signals """
    global httpd
    print "\nThanks for using MoinMoin!"
    if httpd:
        httpd.die()


def registerSignalHandlers(func):
    """ Register signal handlers on platforms that support it """
    try:
        import signal
        signal.signal(signal.SIGABRT, func)
        signal.signal(signal.SIGINT, func)
        signal.signal(signal.SIGTERM, func)        
    except ImportError:
        pass


def makeServer(config):
    """ Create a new server, based on the the platform capabilities 
    
    Try to create the server class specified in the config. If threads
    are not available, fallback to ForkingServer. If fork is not
    available, fallback to a SimpleServer.
    """
    serverClass = globals()[config.serverClass]
    if serverClass.use_threads:
        try:
            import threading
        except ImportError:
            serverClass = ForkingServer
    if serverClass is ForkingServer and not hasattr(os, "fork"):
        serverClass = SimpleServer    
    if serverClass.__name__ != config.serverClass:
        sys.stderr.write('%s is not available on this platform, falling back '
                         'to %s\n' % (config.serverClass,
                                      serverClass.__name__))
            
    from MoinMoin import config as _config
    _config.use_threads = serverClass.use_threads    
    return serverClass(config)


class StandaloneConfig(Config):
    """ Standalone server default config """

    docs = '/usr/share/moin/htdocs'
    user = 'www-data'
    group = 'www-data'
    port = 8000
    interface = 'localhost'
    logPath = None
    
    # Advanced options
    serverClass = 'ThreadPoolServer'
    threadLimit = 10
    # The size of the listen backlog. Twisted uses a default of 50.
    # Tests on Mac OS X show many failed request with backlog of 5 or 10.
    requestQueueSize = 50

    # Development options
    memoryProfile = None
    hotshotProfile = None


def run(configClass):
    """ Create and run a moin server
    
    See StandaloneConfig for available options
    
    @param configClass: config class
    """    
    # set globals (only on first import, save from reloads!)
    global httpd
    global config

    config = configClass()    
    if config.logPath:
        sys.stderr = file(config.logPath, 'at')
    if config.memoryProfile:
        config.memoryProfile.sample()
    registerSignalHandlers(quit)
    httpd = makeServer(config)

    # If running as root, switch user and group id
    if os.getuid() == 0 and os.name == 'posix':
        switchUID(config.uid, config.gid)        

    httpd.serve_forever()

