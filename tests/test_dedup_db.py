#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for the multi-server plex.db schema and deduplication helpers."""
import os
import sqlite3
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import kodi_stubs  # noqa: E402
kodi_stubs.install()

from resources.lib import contentkey  # noqa: E402
from resources.lib.plex_db import schema  # noqa: E402
from resources.lib.plex_db.common import PlexDBBase  # noqa: E402

LEGACY_DDL = '''
CREATE TABLE movie(
    plex_id INTEGER PRIMARY KEY,
    plex_guid TEXT,
    checksum INTEGER UNIQUE,
    section_id INTEGER,
    kodi_id INTEGER,
    kodi_fileid INTEGER,
    kodi_pathid INTEGER,
    fanart_synced INTEGER,
    trailer_synced BOOLEAN,
    last_sync INTEGER);
'''


class TestContentKey(unittest.TestCase):

    def test_external_id_wins(self):
        guids = {'imdb': 'tt0111161', 'tmdb': '278'}
        self.assertEqual(contentkey.from_guids(guids), 'imdb:tt0111161')
        self.assertEqual(contentkey.from_guids({'tmdb': '278'}), 'tmdb:278')

    def test_plex_guid_fallback_normalizes_query(self):
        self.assertEqual(contentkey.from_guids({}, 'plex://movie/abc?lang=en'),
                         'plex:plex://movie/abc')

    def test_same_movie_on_two_servers(self):
        guids = {'imdb': 'tt0111161'}
        self.assertEqual(contentkey.from_guids(guids, 'plex://movie/serverA'),
                         contentkey.from_guids(guids, 'plex://movie/serverB'))

    def test_episode_key_uses_show_and_episode_number(self):
        xml = _xml('''<Video type="episode" season="1" index="2"
                      guid="plex://episode/a"
                      grandparentGuid="plex://show/shared"><Guid id="imdb://tt123"/></Video>''')
        key = contentkey.from_xml(xml, 'episode')
        self.assertEqual(key, 'plex:plex://show/shared/S1E2')


class _xml(object):
    """Tiny stand-in with .iter() for the XML elements contentkey uses."""
    def __init__(self, source):
        import re
        self.attributes = dict(re.findall(r'(\w+)="([^"]*)"', source))
        self.children = []
        for match in re.finditer(r'<Guid id="([^"]*)"', source):
            child = _xml('')
            child.attributes = {'id': match.group(1)}
            child.tag = 'Guid'
            self.children.append(child)
        self.tag = self.attributes.get('tag')

    def get(self, key):
        return self.attributes.get(key)

    def iter(self):
        yield self
        for child in self.children:
            yield child


class TestSchemaMigration(unittest.TestCase):

    def test_migrate_legacy_rows_and_add_sources(self):
        connection = sqlite3.connect(':memory:')
        cursor = connection.cursor()
        cursor.execute(LEGACY_DDL)
        cursor.execute('''INSERT INTO movie VALUES (
            123, 'plex://movie/abc', 999, 1, 42, 5, 6, 0, 0, 1000)''')

        self.assertTrue(schema.migrate(cursor, 'server-A'))
        columns = [row[1] for row in cursor.execute('PRAGMA table_info(movie)')]
        self.assertIn('server_id', columns)
        self.assertIn('content_key', columns)

        row = cursor.execute('SELECT server_id, content_key FROM movie').fetchone()
        self.assertEqual(row, ('server-A', 'plex://movie/abc'))

        db = PlexDBBase(plexconn=connection)
        key = 'imdb:tt0111161'
        db.set_kodi_id(key, 'movie', 42)
        db.upsert_source('server-A', 123, 'movie', key, checksum=999,
                         section_id=1, kodi_id=42)
        db.upsert_source('server-B', 777, 'movie', key, checksum=555,
                         section_id=9, kodi_id=42)

        sources = db.sources_by_content(key, 'movie')
        self.assertEqual(len(sources), 2)
        self.assertEqual(sorted((s[0], s[1]) for s in sources),
                         [('server-A', 123), ('server-B', 777)])

        self.assertTrue(db.is_recorded_on_server(777, 'movie', 'server-B'))
        self.assertFalse(db.is_recorded_on_server(777, 'movie', 'server-A'))

        db.set_kodi_id(key, 'movie', 99)
        kodi_ids = [row[0] for row in cursor.execute(
            'SELECT kodi_id FROM movie ORDER BY server_id')]
        self.assertEqual(kodi_ids, [99, 99])

        db.remove_sources_for_server('server-B')
        self.assertEqual(len(db.sources_by_content(key, 'movie')), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
