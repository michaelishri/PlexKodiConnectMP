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
    def __init__(self, result, button_result=None):
        self.result = result
        self.button_result = button_result


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

    def test_select_ex_returns_button_action(self):
        selectdialog.SelectDialog.open = \
            lambda **kwargs: FakeWindow(None,
                                        button_result=('remove', 1))
        result, action = selectdialog.select_ex('H', ['a', 'b'])
        self.assertIsNone(result)
        self.assertEqual(action, ('remove', 1))

    def test_select_ex_without_buttons(self):
        selectdialog.SelectDialog.open = lambda **kwargs: FakeWindow([1])
        result, action = selectdialog.select_ex('H', ['a', 'b'])
        self.assertEqual(result, [1])
        self.assertIsNone(action)

    def test_single_mode_has_no_checkboxes(self):
        items = selectdialog._build_items(['a', 'b'], multi=False,
                                           selected=set([0]))
        for item in items:
            self.assertNotIn('checkbox', item.properties)
            self.assertNotIn('checked', item.properties)

    def test_multi_mode_has_checkboxes(self):
        items = selectdialog._build_items(['a', 'b'], multi=True,
                                          selected=set([0]))
        self.assertEqual(items[0].properties['checkbox'], '1')
        self.assertEqual(items[0].properties['checked'], '1')
        self.assertEqual(items[1].properties['checkbox'], '1')
        # Unchecked rows carry an empty (invisible) marker
        self.assertEqual(items[1].properties['checked'], '')

    def test_dict_options_carry_second_line(self):
        options = [{'label': 'WHARE',
                    'label2': 'https://192.168.1.198:32400'},
                   'Just a plain option']
        items = selectdialog._build_items(options, multi=True,
                                          selected=set())
        self.assertEqual(items[0].label, 'WHARE')
        self.assertEqual(items[0].label2, 'https://192.168.1.198:32400')
        self.assertEqual(items[1].label, 'Just a plain option')
        self.assertEqual(items[1].label2, '')

    def test_checkbox_can_be_suppressed_per_row(self):
        options = [{'label': 'info', 'checkbox': False}, 'normal']
        items = selectdialog._build_items(options, multi=True, selected=set())
        self.assertNotIn('checkbox', items[0].properties)
        self.assertEqual(items[1].properties['checkbox'], '1')


class TestRailNavigation(unittest.TestCase):
    """Keyboard/remote navigation fallback for the button rail."""

    MANAGE = [1003, 1004, 1005, 1002, 1001]
    MULTI_ONLY = [1002, 1001]
    SINGLE_ONLY = [1002]

    def test_right_from_list_enters_rail_at_the_top(self):
        for rail in (self.MANAGE, self.MULTI_ONLY, self.SINGLE_ONLY):
            self.assertEqual(
                selectdialog._rail_focus_target(
                    rail, 100, selectdialog.xbmcgui.ACTION_MOVE_RIGHT),
                rail[0])

    def test_down_walks_the_rail(self):
        self.assertEqual(
            selectdialog._rail_focus_target(
                self.MANAGE, 1003, selectdialog.xbmcgui.ACTION_MOVE_DOWN),
            1004)
        self.assertEqual(
            selectdialog._rail_focus_target(
                self.MANAGE, 1005, selectdialog.xbmcgui.ACTION_MOVE_DOWN),
            1002)
        self.assertEqual(
            selectdialog._rail_focus_target(
                self.MULTI_ONLY, 1002, selectdialog.xbmcgui.ACTION_MOVE_DOWN),
            1001)

    def test_down_at_the_bottom_stays(self):
        self.assertIsNone(selectdialog._rail_focus_target(
            self.MANAGE, 1001, selectdialog.xbmcgui.ACTION_MOVE_DOWN))
        self.assertIsNone(selectdialog._rail_focus_target(
            self.SINGLE_ONLY, 1002, selectdialog.xbmcgui.ACTION_MOVE_DOWN))

    def test_up_walks_the_rail_and_hands_back_to_the_list(self):
        self.assertEqual(
            selectdialog._rail_focus_target(
                self.MANAGE, 1005, selectdialog.xbmcgui.ACTION_MOVE_UP),
            1004)
        self.assertEqual(
            selectdialog._rail_focus_target(
                self.MANAGE, 1002, selectdialog.xbmcgui.ACTION_MOVE_UP),
            1005)
        # Top of the rail goes back to the list, in every mode
        for rail in (self.MANAGE, self.MULTI_ONLY, self.SINGLE_ONLY):
            self.assertEqual(
                selectdialog._rail_focus_target(
                    rail, rail[0], selectdialog.xbmcgui.ACTION_MOVE_UP),
                100)

    def test_unrelated_focus_and_actions_are_ignored(self):
        self.assertIsNone(selectdialog._rail_focus_target(
            self.MANAGE, 100, selectdialog.xbmcgui.ACTION_MOVE_UP))
        self.assertIsNone(selectdialog._rail_focus_target(
            self.MANAGE, 999, selectdialog.xbmcgui.ACTION_MOVE_DOWN))
        self.assertIsNone(selectdialog._rail_focus_target(
            self.MANAGE, 1002, selectdialog.xbmcgui.ACTION_MOVE_LEFT))
        self.assertIsNone(selectdialog._rail_focus_target(
            [], 100, selectdialog.xbmcgui.ACTION_MOVE_RIGHT))


class TestSelectDialogSkin(unittest.TestCase):

    def test_skin_has_visible_checkbox_per_row(self):
        with open(SKIN, encoding='utf-8') as handle:
            xml = handle.read()
        self.assertIn('<defaultcontrol>100</defaultcontrol>', xml)
        self.assertIn('type="list" id="100"', xml)
        self.assertIn('ListItem.Property(checkbox)', xml)
        self.assertIn('ListItem.Property(checked)', xml)
        self.assertIn('settings/checkbox.png', xml)
        self.assertIn('settings/checkmark.png', xml)
        self.assertIn('type="button" id="1001"', xml)  # Done (multi only)
        self.assertIn('type="button" id="1002"', xml)  # Cancel

    def test_skin_modes_and_extra_buttons(self):
        with open(SKIN, encoding='utf-8') as handle:
            xml = handle.read()
        # The OK button is only shown in multi mode, with a caller label
        self.assertIn('Window.Property(oklabel)', xml)
        self.assertIn('!String.IsEmpty(Window.Property(multi))', xml)
        # Extra footer buttons are property driven
        for number in ('button1label', 'button2label', 'button3label'):
            self.assertIn('Window.Property(%s)' % number, xml)
        # Second line per row
        self.assertIn('ListItem.Label2', xml)
        # Buttons are stacked in a right-hand rail, all sharing one x
        # position, with room for their full labels (no ellipses)
        self.assertEqual(xml.count('<posx>680</posx>'), 5)
        self.assertEqual(xml.count('<width>260</width>'), 5)
        # The list makes room for the rail
        self.assertIn('<width>620</width>', xml)
        # Done and Cancel anchor to the bottom of the rail, Done last
        done_block = xml[xml.index('type="button" id="1001"'):]
        cancel_block = xml[xml.index('type="button" id="1002"'):]
        self.assertIn('<posy>576</posy>', done_block[:done_block.index('</control>')])
        self.assertIn('<posy>506</posy>', cancel_block[:cancel_block.index('</control>')])

    def test_skin_declares_button_navigation(self):
        with open(SKIN, encoding='utf-8') as handle:
            xml = handle.read()
        # Every button hands focus back to the list on Left
        self.assertEqual(xml.count('<onleft>100</onleft>'), 5)
        # Static hops inside the rail where both ends are always
        # visible together; the dynamic hops fall back to python
        self.assertIn('<ondown>1004</ondown>', xml)
        self.assertIn('<onup>1003</onup>', xml)
        self.assertIn('<ondown>1005</ondown>', xml)
        self.assertIn('<onup>1004</onup>', xml)
        self.assertIn('<ondown>1002</ondown>', xml)
        done_block = xml[xml.index('type="button" id="1001"'):]
        self.assertIn('<onup>1002</onup>',
                      done_block[:done_block.index('</control>')])
        self.assertIn('<ondown>1002</ondown>',
                      done_block[:done_block.index('</control>')])

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

    def test_single_choice_dialogs_never_draw_checkboxes(self):
        # Regression: single-select dialogs used to render one unchecked
        # checkbox per row, masquerading as a checklist
        path = os.path.join(ROOT, 'resources', 'lib', 'windows',
                            'selectdialog.py')
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn('if multi and checkbox:', source)

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
