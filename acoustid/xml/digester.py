# -*- coding: utf-8 -*-

import xml.sax
from xml.sax import ContentHandler
from xml.sax.handler import ErrorHandler

class Rule(object):
    def __init__(self):
        self._storedAttrs = None

    def begin(self, tag, attrs):
        pass

    def body(self, tag, attrs, text):
        pass

    def end(self, tag):
        pass

    def finish(self):
        pass


class FuncRule(Rule):
    def __init__(self, bf=None, bbf=None, ef=None, ff=None):
        Rule.__init__(self)
        if bf is not None:
            self.begin = bf
        if bbf is not None:
            self.body = bbf
        if ef is not None:
            self.end = ef
        if ff is not None:
            self.finish = ff


class Digester(ContentHandler):
    def __init__(self):
        ContentHandler.__init__(self)
        self.reset()

    def addAll(self, path, bf, bbf, ef, ff):
        self.addRule(path, FuncRule(bf, bbf, ef, ff))

    def addOnBeginAndEnd(self, path, bf, ef):
        self.addRule(path, FuncRule(bf, None, ef, None))

    def addOnBegin(self, path, bf):
        self.addRule(path, FuncRule(bf, None, None, None))

    def addOnBody(self, path, bbf):
        self.addRule(path, FuncRule(None, bbf, None, None))

    def addOnEnd(self, path, ef):
        self.addRule(path, FuncRule(None, None, ef, None))

    def addOnFinish(self, ff):
        self.addRule("/", FuncRule(None, None, None, ff))

    def addRule(self, path, rule):
        rslot = self._rules.get(path)
        if rslot is None:
            rslot = self._rules[path] = []
        rslot.append(rule)

    def parse(self, input, errorHandler = ErrorHandler()):
        xml.sax.parse(input, self, errorHandler)

    def pop(self):
        return self._stack.pop()

    def push(self, item):
        return self._stack.append(item)

    def reset(self):
        self._rules = {}
        self._stack = []
        self._path = []
        self._cdata = []
        self._active_rules = 0

    def peek(self):
        return self._stack[-1:][0] if len(self._stack) > 0 else None

    def startDocument(self):
        self._path = []

    def endDocument(self):
        assert self._active_rules == 0
        assert len(self._path) == 0
        for a in self._rules.itervalues():
            for r in [x for x in a if x and hasattr(x.finish, '__call__')]:
                r.finish()

    def startElement(self, tag, attrs):
        self._path.append(tag)
        if len(self._cdata) > 0:
            self._cdata = []
        rset = self._rules.get('/'.join(self._path))
        for r in rset if rset is not None else []:
            self._active_rules += 1
            r._storedAttrs = attrs.copy()
            r.begin(tag, attrs)
        return

    def characters(self, content):
        if content is not None and self._active_rules > 0:
            self._cdata.append(content)

    def endElement(self, tag):
        rset = self._rules.get('/'.join(self._path))
        if rset is not None:
            body = ''.join(self._cdata) if len(self._cdata) > 0 else ''
            for r in rset:
                self._active_rules -= 1
                r.body(tag, r._storedAttrs, body)
                r.end(tag)
        self._path.pop()
        if len(self._cdata) > 0:
            self._cdata = []

