#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for resolving a content key to a playback server."""
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import kodi_stubs  # noqa: E402

SETTINGS = kodi_stubs.install()
PROFILE = '/tmp/opencode/pkc-test-profile'
shutil.rmtree(PROFILE, ignore_errors=True)
os.makedirs(PROFILE, exist_ok=True)
SETTINGS.update({
    'plex_machineIdentifier': 'server-A',
    'ipaddress': '127.0.0.1',
    'port': '32400',
    'https': 'false',
})

from resources.lib import app, playback, utils  # noqa: E402
from resources.lib.app.server import Server  # noqa: E402


class FakePlexDB(object):
    sources = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def sources_by_content(self, content_key, plex_type):
        return list(self.sources)


class TestPlaybackPicker(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.init()
        app.CONN.add_server(Server('server-A', 'Living Room',
                                   '192.168.1.10', 32400))
        app.CONN.add_server(Server('server-B', 'Basement',
                                   '10.0.0.2', 32400, token='token-B'))
        app.CONN.connections['server-A'].online = True
        app.CONN.connections['server-B'].online = True

    def setUp(self):
        self.original_db = playback.PlexDB
        self.original_dialog = utils.dialog
        playback.PlexDB = FakePlexDB
        playback.PLAYBACK_SERVERS.clear()

    def tearDown(self):
        playback.PlexDB = self.original_db
        utils.dialog = self.original_dialog

    def test_single_source_is_used_without_dialog(self):
        FakePlexDB.sources = [('server-B', 777, 1, 1, 100)]
        utils.dialog = lambda *args, **kwargs: self.fail('dialog must not show')
        self.assertEqual(playback._pick_playback_server('key', 'movie'),
                         ('server-B', 777))

    def test_multiple_sources_show_picker(self):
        FakePlexDB.sources = [
            ('server-A', 123, 1, 1, 100),
            ('server-B', 777, 2, 1, 100),
        ]
        utils.dialog = lambda *args, **kwargs: 1
        self.assertEqual(playback._pick_playback_server('key', 'movie'),
                         ('server-B', 777))

    def test_cancelling_picker_aborts(self):
        FakePlexDB.sources = [
            ('server-A', 123, 1, 1, 100),
            ('server-B', 777, 2, 1, 100),
        ]
        utils.dialog = lambda *args, **kwargs: -1
        self.assertEqual(playback._pick_playback_server('key', 'movie'),
                         (None, None))

    def test_disabled_servers_are_hidden(self):
        app.CONN.get_server('server-B').enabled = False
        try:
            FakePlexDB.sources = [
                ('server-A', 123, 1, 1, 100),
                ('server-B', 777, 2, 1, 100),
            ]
            utils.dialog = lambda *args, **kwargs: self.fail('dialog must not show')
            self.assertEqual(playback._pick_playback_server('key', 'movie'),
                             ('server-A', 123))
        finally:
            app.CONN.get_server('server-B').enabled = True


if __name__ == '__main__':
    unittest.main(verbosity=2)
