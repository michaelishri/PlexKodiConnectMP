#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for the PKC checkbox selection dialog and its call sites."""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import kodi_stubs  # noqa: E402
kodi_stubs.install()

from resources.lib.windows import selectdialog  # noqa: E402

ROOT = os.path.dirname(HERE)
SKIN = os.path.join(ROOT, 'resources', 'skins', 'Main', '1080i',
                    'script-plex-select-dialog.xml')


class FakeWindow(object):
    def __init__(self, result):
        self.result = result


class TestSelectDialogHelpers(unittest.TestCase):

    def setUp(self):
        self.original_open = selectdialog.SelectDialog.open

    def tearDown(self):
        selectdialog.SelectDialog.open = self.original_open

    def test_empty_options(self):
        self.assertIsNone(selectdialog.select('Heading', []))
        self.assertEqual(selectdialog.select_multi('Heading', []), [])

    def test_single_choice_returns_index(self):
        selectdialog.SelectDialog.open = lambda **kwargs: FakeWindow(2)
        self.assertEqual(selectdialog.select('H', ['a', 'b', 'c']), 2)

    def test_multi_choice_returns_indices(self):
        selectdialog.SelectDialog.open = lambda **kwargs: FakeWindow([0, 2])
        self.assertEqual(selectdialog.select_multi('H', ['a', 'b', 'c']),
                         [0, 2])

    def test_cancel_returns_none(self):
        selectdialog.SelectDialog.open = lambda **kwargs: FakeWindow(None)
        self.assertIsNone(selectdialog.select('H', ['a', 'b']))
        self.assertIsNone(selectdialog.select_multi('H', ['a', 'b']))

    def test_selected_int_is_normalised_for_single_mode(self):
        captured = {}

        def fake_open(**kwargs):
            captured.update(kwargs)
            return FakeWindow(0)

        selectdialog.SelectDialog.open = fake_open
        selectdialog.select('H', ['a', 'b'], selected=1)
        self.assertEqual(captured['selected'], [1])
        self.assertFalse(captured['multi'])


class TestSelectDialogSkin(unittest.TestCase):

    def test_skin_has_visible_checkbox_per_row(self):
        with open(SKIN, encoding='utf-8') as handle:
            xml = handle.read()
        self.assertIn('<defaultcontrol>1001</defaultcontrol>', xml)
        self.assertIn('type="list" id="100"', xml)
        self.assertIn('ListItem.Property(checkbox)', xml)
        self.assertIn('ListItem.Property(checked)', xml)
        self.assertIn('settings/checkbox.png', xml)
        self.assertIn('settings/checkmark.png', xml)
        self.assertIn('type="button" id="1001"', xml)  # OK
        self.assertIn('type="button" id="1002"', xml)  # Cancel

    def test_select_libraries_command_calls_a_real_method(self):
        path = os.path.join(ROOT, 'resources', 'lib', 'service_entry.py')
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        self.assertNotIn('self.choose_plex_libraries', source)
        self.assertIn('sections.pick_libraries_all(self, force=True)', source)

    def test_dialog_uses_kodi_modal_loop(self):
        # Without this, key presses go to the window behind our dialog.
        path = os.path.join(ROOT, 'resources', 'lib', 'windows',
                            'selectdialog.py')
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn('xbmcgui.WindowXMLDialog.doModal(self)', source)

    def test_no_native_select_dialogs_remain(self):
        pattern = re.compile(r'(Dialog\(\)\.select|multiselect\(|'
                             r"utils\.dialog\(['\"]select['\"])")
        offenders = []
        for directory, _, files in os.walk(os.path.join(ROOT, 'resources', 'lib')):
            for name in files:
                if not name.endswith('.py') or name == 'selectdialog.py':
                    continue
                path = os.path.join(directory, name)
                with open(path, encoding='utf-8') as handle:
                    if pattern.search(handle.read()):
                        offenders.append(os.path.relpath(path, ROOT))
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
