#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for multi-server sync selection and combined library picker."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import kodi_stubs  # noqa: E402
kodi_stubs.install()

from resources.lib import app  # noqa: E402
from resources.lib.app.server import Server  # noqa: E402
from resources.lib.library_sync import sections  # noqa: E402

ROOT = os.path.dirname(HERE)


class TestMultiServerSync(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.init()
        app.CONN.add_server(Server('server-A', 'Jason Plex', '10.0.0.1', 32400))
        app.CONN.add_server(Server('server-B', 'Adam Plex', '10.0.0.2', 32400))

    def test_section_carries_server_identity(self):
        with app.using_server('server-B'):
            section = sections.Section()
            section.section_id = 5
        self.assertEqual(section.server_id, 'server-B')
        self.assertEqual(section.server_name, 'Adam Plex')
        self.assertEqual(sections.library_label(section,
                         app.CONN.get_server('server-B')),
                         'None (Adam Plex)')
        section.name = 'TV Shows'
        self.assertEqual(sections.library_label(section,
                         app.CONN.get_server('server-B')),
                         'TV Shows (Adam Plex)')

    def test_sections_from_different_servers_are_not_equal(self):
        with app.using_server('server-A'):
            first = sections.Section()
            first.section_id = 3
            first.name = 'TV Shows'
        with app.using_server('server-B'):
            second = sections.Section()
            second.section_id = 3
            second.name = 'TV Shows'
        self.assertNotEqual(first, second)

    def test_full_sync_uses_enabled_servers_and_combined_picker(self):
        path = os.path.join(ROOT, 'resources', 'lib', 'library_sync',
                            'full_sync.py')
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn('app.CONN.enabled_servers()', source)
        self.assertIn('sections.pick_libraries_all(self)', source)

    def test_select_libraries_command_uses_combined_picker(self):
        path = os.path.join(ROOT, 'resources', 'lib', 'service_entry.py')
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn("sections.pick_libraries_all(self, force=True)", source)

    def test_tv_items_use_content_key_deduplication(self):
        path = os.path.join(ROOT, 'resources', 'lib', 'itemtypes',
                            'tvshows.py')
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn('item_by_content(', source)
        self.assertIn('content_key=content_key', source)
        self.assertIn('remove_source(server_id', source)

    def test_settings_expose_server_enable_action(self):
        path = os.path.join(ROOT, 'resources', 'settings.xml')
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn('mode=selectServers', source)

    def test_servermanager_has_enable_action(self):
        path = os.path.join(ROOT, 'resources', 'lib', 'servermanager.py')
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn('def select_enabled_servers()', source)
        self.assertIn("selectdialog.select_multi('Enable Plex servers for sync'",
                      source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
