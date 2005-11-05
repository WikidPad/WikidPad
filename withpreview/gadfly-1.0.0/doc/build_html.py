#!/usr/bin/env python

"""
:Author: David Goodger
:Contact: goodger@users.sourceforge.net
:Revision: $Revision: 1.2 $
:Date: $Date: 2002/05/08 00:49:00 $
:Copyright: This module has been placed in the public domain.

A minimal front-end to the Docutils Publisher.

This module takes advantage of the default values defined in `publish()`.
"""

import sys, os.path
from docutils.core import publish
from docutils import utils

if len(sys.argv) < 2:
    print >>sys.stderr, 'I need at least one filename'
    sys.exit(1)

reporter = utils.Reporter(2, 4)

for file in sys.argv[1:]:
    name, ext = os.path.splitext(file)
    dest = '%s.html'%name
    print >>sys.stderr, '%s -> %s'%(file, dest)
    publish(writer_name='html', source=file, destination=dest,
        reporter=reporter)
