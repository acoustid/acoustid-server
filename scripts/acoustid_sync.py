#!/usr/bin/env python
# -*- coding: utf-8 -*-
from collections import OrderedDict
import os

import urllib2
import logging
import tempfile
import shutil
import subprocess
import psycopg2.extensions

from contextlib import closing
from bz2 import BZ2File
from xml.sax._exceptions import SAXParseException
from xml.sax.xmlreader import InputSource

from acoustid.xml.digester import Digester
from acoustid.script import run_script


logger = logging.getLogger(__name__)

class DataImporter(Digester):
    def __init__(self, ictx, file):
        Digester.__init__(self)
        self._ictx = ictx
        self._file = file
        self._input = InputSource(file.name)
        self._input.setByteStream(BZ2File(file.name, 'r'))
        self._conn = ictx['conn'].connection
        self._cursor = self._conn.cursor()
        self.success = self._closed = False
        self._add_rules()

    def _add_rules(self):
        self.addOnBegin('packet', self._check_packet)
        self.addOnBeginAndEnd('packet/transaction/event', self._on_event, self._on_event_end)
        self.addOnBody('packet/transaction/event/keys/column', self._on_key_column)
        self.addOnBody('packet/transaction/event/values/column', self._on_value_column)
        self.addOnFinish(self._on_finish)

    def _check_packet(self, tag, attrs):
        if self._ictx['schema_seq'] != int(attrs.getValue('schema_seq')):
            raise Exception('<packet> schema_seq: {0} not matched the expected seq number {1}',
                            attrs.getValue('schema_seq'), self._ictx['replication_seq'])

        if self._ictx['replication_seq'] != int(attrs.getValue('replication_seq')):
            raise Exception('<packet> replication_seq: {0} not matched the expected seq number {1}',
                            attrs.getValue('replication_seq'), self._ictx['replication_seq'])

    def _on_key_column(self, tag, attrs, val):
        event = self.peek()
        event['keys'][attrs.getValue('name')] = val

    def _on_value_column(self, tag, attrs, val):
        event = self.peek()
        isNull = attrs.getValue("null") if attrs.has_key('null') else None
        event['values'][attrs.getValue('name')] = val if isNull != "yes" else None

    def _on_event(self, tag, attrs):
        event = {
            'op': attrs.getValue('op'),
            'table': attrs.getValue('table'),
            'keys': OrderedDict(), #array of tuples column name -> column val
            'values': OrderedDict() #array of tuples column name -> column val
        }
        self.push(event)

    def _on_event_end(self, tag):
        event = self.pop()
        type = event['op']
        table = event['table']
        keys = event['keys']
        values = event['values']
        params = []
        if type == 'I':
            sql_columns = ', '.join(values.keys())
            sql_values = ', '.join(['%s'] * len(values))
            sql = 'INSERT INTO %s (%s) VALUES (%s)' % (table, sql_columns, sql_values)
            params = values.values()
        elif type == 'U':
            sql_values = ', '.join('%s=%%s' % i for i in values)
            sql = 'UPDATE %s SET %s' % (table, sql_values)
            params = values.values()
        elif type == 'D':
            sql = 'DELETE FROM %s' % table
        else:
            raise Exception('Invalid <event> op: %s' % type)

        if type == 'D' or type == 'U':
            sql += ' WHERE ' + ' AND '.join('%s%s%%s' % (i, ' IS ' if keys[i] is None else '=') for i in keys.keys())
            params.extend(keys.values())

        #print '%s %s' % (sql, params)
        self._cursor.execute(sql, params)

    def _on_finish(self):
        pass

    def load(self):
        logger.warning('Saving dataset....')
        self.parse(self._input)
        self.success = True

    def recover(self):
        """ This is duty hack to remove weird characters presented in some replications files.
            Using the tidy tool.
        """
        logger.warning('Trying to recover invalid XML...')
        originalXML = None
        fixedXML = None
        try:
            originalXML = tempfile.NamedTemporaryFile(suffix='.xml', delete=False) #bunzipped tmp
            fixedXML = tempfile.NamedTemporaryFile(suffix='.xml', delete=False) #fixed tmp
            fixedXML.close()

            #Fetch uncompressed file data to recover
            bzf = self._input.getByteStream()
            bzf.seek(0)
            shutil.copyfileobj(bzf, originalXML)
            originalXML.close()

            cmd = ['tidy', '-xml', '-o', fixedXML.name, originalXML.name]
            logger.warning('Running: %s', ' '.join(cmd))
            ret = subprocess.call(cmd)
            if ret:
                #raise Exception('Failed to fix XML data, ret=%s' % ret)
                pass

            #ready to load
            self.close()
            self._file = file(fixedXML.name, 'r')
            self._input = InputSource(fixedXML.name)
            self._input.setByteStream(self._file)
            self._cursor = self._conn.cursor()
            self.success = self._closed = False
            self.reset()
            self._add_rules()
            self.load()
        finally:
            for f in [originalXML, fixedXML]:
                if f and not f.closed:
                    f.close()
                if f and os.path.exists(f.name):
                    os.unlink(f.name)


    def close(self):
        if self._closed:
            return
        try:
            if self.success:
                self._conn.commit()
                logger.warning('Done')
            else:
                logger.warning('Rolling back transaction. Seq number: {0}'.format(self._ictx['replication_seq']))
                self._conn.rollback()
            self._cursor.close()
        finally:
            self._closed = True
            self._input.getByteStream().close()
            self._file.close()


def download_arch(url):
    logger.warning('Downloading: %s', url)
    try:
        data = urllib2.urlopen(url)
    except urllib2.HTTPError, e:
        if e.code == 404:
            logger.warning('Resource %s not found', url)
            return None
        raise
    except urllib2.URLError, e:
        if '[Errno 2]' in str(e.reason):
            logger.warning('Resource %s not found', url)
            return None
        raise
    tmp = tempfile.NamedTemporaryFile(suffix='.xml.bz2')
    shutil.copyfileobj(data, tmp)
    data.close()
    tmp.seek(0)
    logger.debug('Stored in %s', tmp.name)
    return tmp


def sync(script, ictx):
    if script.config.replication.import_acoustid is None:
        err = 'Missing required \'import_acoustid\' configuration parameter in [replication]'
        logger.error(err)
        exit(1)

    rseq = ictx['replication_seq']
    while True:
        rseq += 1
        ictx['replication_seq'] = rseq
        url = script.config.replication.import_acoustid.format(seq=rseq)
        arch = download_arch(url)
        if arch is None:
            logger.warning('Stopped on seq %d', rseq)
            break
        di = DataImporter(ictx, arch)
        with closing(di):
            try:
                di.load()
            except SAXParseException, spe:
                logger.error('XML data parsing error. %s URL: %s', spe, url)
                di.recover()


def main(script, opts, args):
    conn = script.engine.connect()
    conn.detach()
    with closing(conn):
        conn.connection.rollback()
        conn.connection.set_session(psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)
        cursor = conn.connection.cursor()
        with closing(cursor):
            cursor.execute('''SELECT current_schema_sequence,
                           current_replication_sequence FROM replication_control''')
            schema_seq, replication_seq = cursor.fetchone()
            conn.connection.commit()

        ictx = {
            'schema_seq': schema_seq,
            'replication_seq': replication_seq,
            'script': script,
            'conn': conn,
            }
        sync(script, ictx)


if __name__ == '__main__':
    run_script(main)

