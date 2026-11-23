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
        self.original_select = selectdialog.select
        self.original_select_ex = selectdialog.select_ex
        self.original_discover = PF.discover_pms
        # manage() runs headless: the dialog aborts immediately and discovery
        # finds nothing
        selectdialog.select_ex = lambda *args, **kwargs: (None, None)
        PF.discover_pms = lambda *args, **kwargs: []

    def tearDown(self):
        selectdialog.select = self.original_select
        selectdialog.select_ex = self.original_select_ex
        PF.discover_pms = self.original_discover

    def _clean_init(self):
        """Fresh app state without servers persisted by earlier tests."""
        app.init()
        app.CONN.clear()

    def _capture_select_ex(self):
        captured = {}

        def fake_select_ex(heading, options, **kwargs):
            captured['heading'] = heading
            captured['options'] = options
            captured.update(kwargs)
            return (None, None)

        selectdialog.select_ex = fake_select_ex
        return captured

    def test_manage_does_not_crash_on_labels(self):
        # Regression: labels used to be a tuple, so `list + tuple` raised
        # TypeError before the dialog could open
        self._clean_init()
        app.CONN.add_server(Server('server-A', 'Jason', '10.0.0.1', 32400))
        app.CONN.add_server(Server('server-B', 'Adam', '10.0.0.2', 32400))
        servermanager.manage()  # returns immediately because select_ex aborts

    def test_manage_lists_discovered_and_offline_servers(self):
        self._clean_init()
        app.CONN.add_server(Server('server-A', 'Jason', '10.0.0.1', 32400))
        PF.discover_pms = lambda *args, **kwargs: [
            {'machineIdentifier': 'server-A', 'name': 'Jason'},
            {'machineIdentifier': 'far-away', 'name': 'Far',
             'presence': False, 'baseURL': 'https://far:32400',
             'token': 'far-token'},
        ]
        captured = self._capture_select_ex()
        servermanager.manage()
        options = captured['options']
        # Own server, already known plex.tv server, new offline server
        self.assertEqual(len(options), 2)
        self.assertEqual(options[0]['label'], 'Jason [primary]')
        self.assertIn('10.0.0.1', options[0]['label2'])
        self.assertEqual(options[1]['label'], 'Far')
        # Offline servers are annotated instead of being silently dropped
        self.assertIn('https://far:32400', options[1]['label2'])
        self.assertNotEqual(options[1]['label2'], 'https://far:32400')
        # Only the enabled configured server is pre-checked
        self.assertEqual(captured['selected'], [0])
        self.assertIsNone(captured['subtitle'])

    def test_manage_toggle_adds_discovered_server(self):
        self._clean_init()
        app.CONN.add_server(Server('server-A', 'Jason', '10.0.0.1', 32400))
        PF.discover_pms = lambda *args, **kwargs: [
            {'machineIdentifier': 'far-away', 'name': 'Far',
             'presence': False, 'scheme': 'https',
             'ip': 'far', 'port': '32400',
             'baseURL': 'https://far:32400', 'token': 'far-token'},
        ]
        captured = self._capture_select_ex()
        servermanager.manage()
        # Simulate the user checking the offline, unconfigured row
        self.assertTrue(captured['can_toggle'](1, True))
        added = app.CONN.get_server('far-away')
        self.assertIsNotNone(added)
        self.assertTrue(added.enabled)

    def test_manage_toggle_guard_keeps_last_enabled(self):
        self._clean_init()
        app.CONN.add_server(Server('server-A', 'Jason', '10.0.0.1', 32400))
        captured = self._capture_select_ex()
        servermanager.manage()
        # Unchecking the only enabled server is vetoed
        self.assertFalse(captured['can_toggle'](0, False))
        self.assertTrue(app.CONN.get_server('server-A').enabled)
        # Re-checking is always allowed
        self.assertTrue(captured['can_toggle'](0, True))

    def test_manage_reports_failed_discovery_in_subtitle(self):
        self._clean_init()
        app.CONN.add_server(Server('server-A', 'Jason', '10.0.0.1', 32400))

        def broken_discover(*args, **kwargs):
            raise IOError('plex.tv unreachable')

        PF.discover_pms = broken_discover
        captured = self._capture_select_ex()
        servermanager.manage()
        self.assertEqual(len(captured['options']), 1)
        self.assertIsNotNone(captured['subtitle'])

    def test_manage_without_any_servers_goes_to_manual_entry(self):
        self._clean_init()
        called = []
        original = servermanager._add_manually
        servermanager._add_manually = lambda: called.append(True) or None
        try:
            # No configured servers, discovery finds nothing
            servermanager.manage()
        finally:
            servermanager._add_manually = original
        self.assertEqual(called, [True])

    def test_select_enabled_servers_refuses_to_disable_everything(self):
        self._clean_init()
        app.CONN.add_server(Server('server-A', 'Jason', '10.0.0.1', 32400))
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
        PF._pms_list_from_plex_tv = \
            lambda token, include_offline=False: calls.append(token) or []
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

    _OFFLINE_XML = ET.fromstring('''
      <MediaContainer>
        <Device name="Offline" provides="server" clientIdentifier="off"
                lastSeenAt="0" presence="0">
          <Connection uri="https://1.2.3.4:32400" local="1"/>
        </Device>
      </MediaContainer>
    ''')

    def test_offline_servers_are_filtered_by_default(self):
        xml = self._OFFLINE_XML
        original = PF.DU().downloadUrl
        PF.DU().downloadUrl = lambda *args, **kwargs: xml
        try:
            self.assertEqual(PF._pms_list_from_plex_tv('token'), [])
        finally:
            PF.DU().downloadUrl = original

    def test_offline_servers_are_included_on_request(self):
        xml = self._OFFLINE_XML
        original = PF.DU().downloadUrl
        PF.DU().downloadUrl = lambda *args, **kwargs: xml
        try:
            result = PF._pms_list_from_plex_tv('token', include_offline=True)
        finally:
            PF.DU().downloadUrl = original
        self.assertEqual(len(result), 1)
        server = result[0]
        self.assertEqual(server['machineIdentifier'], 'off')
        self.assertFalse(server['presence'])
        # Address taken from plex.tv without probing
        self.assertEqual(server['scheme'], 'https')
        self.assertEqual(server['ip'], '1.2.3.4')
        self.assertEqual(server['port'], '32400')
        self.assertEqual(server['baseURL'], 'https://1.2.3.4:32400')


if __name__ == '__main__':
    unittest.main(verbosity=2)
