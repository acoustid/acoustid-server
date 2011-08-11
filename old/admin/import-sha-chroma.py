#!/usr/bin/env python

import ConfigParser
import psycopg2
import urllib
import urllib2
import sys
import os
from xml.etree import ElementTree

config = ElementTree.parse(sys.argv[1])

opts = {}
for elem in config.find('database'):
    name = elem.tag.lower()
    if name == 'name':
        name = 'database'
    value = elem.text
    opts[name] = value
db = psycopg2.connect(**opts)

USER_API_KEY = 'ye9Bbbfd'
CLIENT_API_KEY = 'dGA3IKKS'
API_URL = 'http://127.0.0.1:8080/ws/v2/submit'
BATCH_SIZE = 50

cursor = db.cursor()
cursor.execute("""
    SELECT mp.puid, length, bitrate, fp, sc.sha
    FROM
        sha_chroma sc
        JOIN sha_puid sp ON sc.sha=sp.sha
        JOIN musicbrainz.puid mp ON mp.puid=sp.puid
        LEFT JOIN sha_chroma_imported sci ON sc.sha=sci.sha
    WHERE sci.sha IS NULL AND length>0
    LIMIT 50000
""")

params = { 'user': USER_API_KEY, 'client': CLIENT_API_KEY }
shas = set()
i = 0
for row in cursor:
    if row[4] in shas:
        continue
    shas.add(row[4])
    params['puid.%d' % i] = row[0]
    params['duration.%d' % i] = row[1]
    params['bitrate.%d' % i] = row[2]
    params['fingerprint.%d' % i] = row[3]
    params['foreignid.%d' % i] = 'zvq-sha:%s' % (row[4],)
    i += 1
    if i == BATCH_SIZE:
        #print "Submitting", i
        data = urllib.urlencode(params)
        urllib2.urlopen(API_URL, data)
        params = { 'user': USER_API_KEY, 'client': CLIENT_API_KEY }
        i = 0

if i:
    #print "Submitting", i
    data = urllib.urlencode(params)
    urllib2.urlopen(API_URL, data)

for sha in shas:
    cursor.execute("INSERT INTO sha_chroma_imported VALUES (%s)", (sha,))
db.commit()

