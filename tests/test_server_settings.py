#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for the simplified server settings and faster discovery."""
import os
import sys
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import kodi_stubs  # noqa: E402
kodi_stubs.install()

from resources.lib import app, plex_functions as PF, servermanager  # noqa: E402
from resources.lib.app.server import Server  # noqa: E402
from resources.lib.windows import selectdialog  # noqa: E402

ROOT = os.path.dirname(HERE)


class TestServerManager(unittest.TestCase):

    def setUp(self):
        self.original = selectdialog.select
        selectdialog.select = lambda *args, **kwargs: None

    def tearDown(self):
        selectdialog.select = self.original

    def test_manage_does_not_crash_on_labels(self):
        # Regression: _server_labels() is a list and labels used to be a tuple,
        # so `list + tuple` raised TypeError before the dialog could open.
        app.init()
        app.CONN.add_server(Server('server-A', 'Jason', '10.0.0.1', 32400))
        app.CONN.add_server(Server('server-B', 'Adam', '10.0.0.2', 32400))
        servermanager.manage()  # returns immediately because select is stubbed

    def test_select_enabled_servers_refuses_to_disable_everything(self):
        app.init()
        app.CONN.add_server(Server('server-A', 'Jason', '10.0.0.1', 32400))
        global select_multi
        original = selectdialog.select_multi
        selectdialog.select_multi = lambda *args, **kwargs: []
        try:
            servermanager.select_enabled_servers()
        finally:
            selectdialog.select_multi = original
        self.assertTrue(app.CONN.get_server('server-A').enabled)


class TestDiscovery(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.init()

    def test_gdm_is_skipped_when_disabled(self):
        original_gdm = PF._plex_gdm
        called = []
        PF._plex_gdm = lambda: called.append(True) or []
        PF._DISCOVERY_CACHE.clear()
        try:
            PF.discover_pms(token='token', include_gdm=False, force=True)
            self.assertEqual(called, [])
        finally:
            PF._plex_gdm = original_gdm
            PF._DISCOVERY_CACHE.clear()

    def test_discovery_result_is_cached(self):
        original_gdm = PF._plex_gdm
        original_plex = PF._pms_list_from_plex_tv
        calls = []
        PF._plex_gdm = lambda: []
        PF._pms_list_from_plex_tv = lambda token: calls.append(token) or []
        PF._DISCOVERY_CACHE.clear()
        try:
            first = PF.discover_pms(token='token', include_gdm=False,
                                    force=True)
            second = PF.discover_pms(token='token', include_gdm=False)
            self.assertIs(first, second)
            self.assertEqual(calls, ['token'])
        finally:
            PF._plex_gdm = original_gdm
            PF._pms_list_from_plex_tv = original_plex
            PF._DISCOVERY_CACHE.clear()

    def test_offline_servers_are_filtered(self):
        xml = ET.fromstring('''
          <MediaContainer>
            <Device name="Offline" provides="server" clientIdentifier="off"
                    lastSeenAt="0" presence="0">
              <Connection uri="https://1.2.3.4:32400" local="1"/>
            </Device>
          </MediaContainer>
        ''')
        original = PF.DU().downloadUrl
        PF.DU().downloadUrl = lambda *args, **kwargs: xml
        try:
            self.assertEqual(PF._pms_list_from_plex_tv('token'), [])
        finally:
            PF.DU().downloadUrl = original


if __name__ == '__main__':
    unittest.main(verbosity=2)
