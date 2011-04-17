#!/usr/bin/env python

import sys
from xml.etree import ElementTree

tree = ElementTree.parse(sys.argv[1])
for elem in tree.find('database'):
    print 'DB_%s=%s' % (elem.tag.upper(), elem.text)

