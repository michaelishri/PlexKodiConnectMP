#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unit tests for the multi-server foundation (no Kodi required)."""
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
    'plex_servername': 'Living Room PMS',
    'ipaddress': '192.168.1.10',
    'port': '32400',
    'https': 'false',
    'plex_serverowned': 'true',
    'accessToken': 'token-A',
    'sslcert': 'None',
})

from resources.lib import app  # noqa: E402
from resources.lib.app.server import Server, ServerRegistry  # noqa: E402


class TestServerRegistry(unittest.TestCase):

    def setUp(self):
        for name in os.listdir(PROFILE):
            path = os.path.join(PROFILE, name)
            if os.path.isfile(path):
                os.remove(path)

    def test_legacy_import(self):
        registry = ServerRegistry()
        self.assertEqual(len(registry), 1)
        server = registry.primary
        self.assertEqual(server.machine_identifier, 'server-A')
        self.assertEqual(server.base_url, 'http://192.168.1.10:32400')
        self.assertEqual(server.token, 'token-A')
        self.assertTrue(os.path.exists(registry.path))

    def test_add_remove_and_roundtrip(self):
        registry = ServerRegistry()
        second = Server(machine_identifier='server-B', name='Basement PMS',
                        host='10.0.0.2', port=32400, https=True,
                        token='token-B')
        registry.add(second)
        self.assertEqual(len(registry), 2)
        self.assertEqual(registry.primary_id, 'server-A')
        self.assertEqual(registry.get('server-B').base_url,
                         'https://10.0.0.2:32400')

        reloaded = ServerRegistry()
        self.assertEqual(len(reloaded), 2)
        self.assertEqual(reloaded.primary_id, 'server-A')
        self.assertEqual(reloaded.get('server-B').token, 'token-B')

        self.assertTrue(registry.remove('server-B'))
        self.assertEqual(len(ServerRegistry()), 1)

    def test_mirror_legacy_points_at_primary(self):
        registry = ServerRegistry()
        registry.add(Server('server-B', name='B', host='10.0.0.2', port=32400))
        registry.set_primary('server-B')
        self.assertEqual(SETTINGS['plex_machineIdentifier'], 'server-B')
        self.assertEqual(SETTINGS['ipaddress'], '10.0.0.2')


class TestConnectionContext(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        for name in os.listdir(PROFILE):
            path = os.path.join(PROFILE, name)
            if os.path.isfile(path):
                os.remove(path)
        app.init()
        app.CONN.add_server(Server('server-B', name='B', host='10.0.0.2',
                                   port=32400, https=True, token='token-B'))

    def test_default_is_primary_server(self):
        self.assertEqual(app.CONN.current_id, 'server-A')
        self.assertEqual(app.CONN.server, 'http://192.168.1.10:32400')
        self.assertEqual(app.CONN.machine_identifier, 'server-A')

    def test_context_switch_and_restore(self):
        self.assertEqual(app.CONN.server, 'http://192.168.1.10:32400')
        with app.using_server('server-B'):
            self.assertEqual(app.CONN.server, 'https://10.0.0.2:32400')
            self.assertEqual(app.CONN.machine_identifier, 'server-B')
        self.assertEqual(app.CONN.server, 'http://192.168.1.10:32400')

    def test_account_token_follows_context(self):
        app.ACCOUNT.pms_tokens = {
            'server-A': 'token-A',
            'server-B': 'token-B',
        }
        self.assertEqual(app.ACCOUNT.pms_token, 'token-A')
        with app.using_server('server-B'):
            self.assertEqual(app.ACCOUNT.pms_token, 'token-B')
        self.assertEqual(app.ACCOUNT.pms_token, 'token-A')

    def test_online_state_is_per_server(self):
        app.CONN.online = True
        self.assertTrue(app.CONN.get_server('server-A') is not None)
        with app.using_server('server-B'):
            self.assertFalse(app.CONN.online)
            app.CONN.online = True
        self.assertTrue(app.CONN.online)


if __name__ == '__main__':
    unittest.main(verbosity=2)
