#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
"""
MoinMoin - build lupy search engine's index

You must run this script as owner of the wiki files, usually this is the
web server user.

@copyright: 2005 by Florian Festi, Nir Soffer
@license: GNU GPL, see COPYING for details.
"""
__version__ = "1.0"

import os

# Insert the path to MoinMoin in the start of the path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(sys.argv[0]), 
                                os.pardir, os.pardir))

from MoinMoin.scripts import _util
from MoinMoin.request import RequestCLI
from MoinMoin.lupy import Index


class IndexScript(_util.Script):
    """ General index script class """

    def __init__(self):
        _util.Script.__init__(self, __name__, "[options]")
        self.parser.add_option(
            "--config-dir", metavar="DIR", dest="config_dir",
            help=("Path to the directory containing the wiki "
                  "configuration files. [default: current directory]")
        )
        self.parser.add_option(
            "--wiki-url", metavar="WIKIURL", dest="wiki_url",
            help="URL of wiki e.g. localhost/mywiki/ [default: CLI]"
        )
    
    def mainloop(self):
        # Insert config dir or the current directory to the start of the
        # path.
        config_dir = self.options.config_dir
        if config_dir and not os.path.isdir(config_dir):
            _util.fatal("bad path given to --config-dir option")
        sys.path.insert(0, os.path.abspath(config_dir or os.curdir))

        # Create request 
        if self.options.wiki_url:
            self.request = RequestCLI(self.options.wiki_url)
        else:
            self.request = RequestCLI()
        self.command()

class BuildIndex(IndexScript):
    def command(self):
        Index(self.request).indexPages()


def run():
    BuildIndex().run()

if __name__ == "__main__":
    run()

