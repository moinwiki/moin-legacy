# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - Version Information

    @copyright: 2000-2004 by J�rgen Hermann <jh@web.de>
    @license: GNU GPL, see COPYING for details.
"""

project = "MoinMoin"
revision = '$Revision: 1.183 $'[11:-2]
release  = '1.2'

if __name__ == "__main__":
    # Bump own revision
    import os
    os.system('cvs ci -f -m "Bumped revision" version.py')

