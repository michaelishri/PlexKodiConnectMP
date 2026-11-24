#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kodi-native looking selection dialog.

PKC used xbmcgui.Dialog().select()/multiselect() for several choices. Those
dialogs are rendered by the active Kodi skin, and some skins indicate the
selection only by changing the text colour. This window is drawn by PKC's own
Main skin so selections are explicit.

Modes:
- Single choice (select()): plain rows, clicking one picks it. The dialog
  shows a single Cancel button. NO checkboxes are drawn in this mode.
- Multiple choice (select_multi()/select_ex()): every row carries a checkbox
  that may be toggled; footer shows Done and Cancel.

Extensions used by the server manager (select_ex()):
- options entries may be dicts with 'label', 'label2' (second, dimmed line)
  and 'checkbox' (set to False to suppress the row checkbox)
- can_toggle(index, checked_after) -> bool vetoes a toggle before it is
  applied, e.g. to keep at least one server enabled
- up to three extra footer buttons; clicking one closes the dialog and
  returns (action_key, focused_row_index)
"""
import xbmc
import xbmcgui

from . import kodigui
from .. import utils, variables as v


def _entry_fields(entry):
    """
    Options entries are either plain labels (str/unicode) or dicts with
    'label', 'label2' and 'checkbox' keys.
    """
    if isinstance(entry, dict):
        return (entry.get('label', ''),
                entry.get('label2', ''),
                entry.get('checkbox') is not False)
    return str(entry), '', True


def _build_items(options, multi, selected):
    """Create the ManagedListItems, with checkboxes in multi mode only."""
    items = []
    for index, entry in enumerate(options):
        label, label2, checkbox = _entry_fields(entry)
        item = kodigui.ManagedListItem(label, label2, data_source=index)
        if multi and checkbox:
            item.setProperty('checkbox', '1')
            item.setBoolProperty('checked', index in selected)
        items.append(item)
    return items


class SelectDialog(kodigui.BaseDialog):
    xmlFile = 'script-plex-select-dialog.xml'
    path = v.ADDON_PATH
    theme = 'Main'
    res = '1080i'
    width = 1920
    height = 1080

    LIST_ID = 100
    OK_BUTTON_ID = 1001
    CANCEL_BUTTON_ID = 1002
    EXTRA_BUTTON_IDS = (1003, 1004, 1005)

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.heading = kwargs.get('heading') or ''
        self.options = list(kwargs.get('options') or [])
        self.multi = bool(kwargs.get('multi', False))
        self.selected = set(index for index in (kwargs.get('selected') or [])
                            if 0 <= index < len(self.options))
        self.subtitle = kwargs.get('subtitle')
        self.can_toggle = kwargs.get('can_toggle')
        self.extra_buttons = list(kwargs.get('extra_buttons') or [])[:3]
        self.result = None
        self.button_result = None
        self.list = None
        self.items = []

    def doModal(self):
        """
        Use Kodi's real modal loop. The generic kodigui.Modal helper only
        shows the window and waits in Python, which leaves the underlying
        add-on settings window active and swallows navigation/select actions.
        """
        xbmcgui.WindowXMLDialog.doModal(self)

    def onFirstInit(self):
        self.setProperty('header', self.heading)
        if self.multi:
            self.setProperty('multi', '1')
            self.setProperty('oklabel', utils.lang(30125))  # Done
        if self.subtitle:
            self.setProperty('subtitle', self.subtitle)
        for index, (_action_key, label) in enumerate(self.extra_buttons):
            self.setProperty('button%slabel' % (index + 1), label)
        self.list = kodigui.ManagedControlList(self, self.LIST_ID,
                                               max(1, len(self.options)))
        items = _build_items(self.options, self.multi, self.selected)
        self.items = items
        self.list.addItems(items)
        self._update_subtitle()
        self.setBoolProperty('initialized', True)
        xbmc.Monitor().waitForAbort(0.1)
        self.setFocusId(self.LIST_ID)

    def _update_subtitle(self):
        if not self.multi or self.subtitle:
            return
        self.setProperty('subtitle', '%s / %s' % (len(self.selected),
                                                  len(self.options)))

    def focused_index(self):
        item = self.list.getSelectedItem() if self.list else None
        return item.dataSource if item else None

    def _toggle(self):
        item = self.list.getSelectedItem()
        if not item:
            return
        index = item.dataSource
        checked = index not in self.selected
        if self.can_toggle and not self.can_toggle(index, checked):
            # Caller vetoed the change (e.g. last server enabled) and has
            # already told the user why
            return
        if checked:
            self.selected.add(index)
            item.setBoolProperty('checked', True)
        else:
            self.selected.discard(index)
            item.setBoolProperty('checked', False)
        self._update_subtitle()

    def onClick(self, controlID):
        if controlID == self.LIST_ID:
            if self.multi:
                self._toggle()
            else:
                item = self.list.getSelectedItem()
                if item:
                    self.result = item.dataSource
                    self.doClose()
        elif controlID == self.OK_BUTTON_ID:
            self.result = sorted(self.selected) if self.multi else None
            self.doClose()
        elif controlID == self.CANCEL_BUTTON_ID:
            self.result = None
            self.doClose()
        else:
            for index, control in enumerate(self.EXTRA_BUTTON_IDS):
                if controlID == control and index < len(self.extra_buttons):
                    action_key = self.extra_buttons[index][0]
                    self.button_result = (action_key, self.focused_index())
                    self.result = None
                    self.doClose()
                    return


    def onAction(self, action):
        # NOTE: Do NOT move focus from here for directional actions. onAction
        # runs BEFORE Kodi's built-in navigation, so a setFocusId() here is
        # followed by the built-in navigation moving focus again - one key
        # press then jumps two buttons. All rail navigation lives in the
        # skin's <onup>/<ondown>/<onleft>/<onright> tags; targets that are
        # hidden in the current mode are simply not focused.
        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU,
                              xbmcgui.ACTION_NAV_BACK):
            self.result = None
            self.doClose()
            return
        kodigui.BaseDialog.onAction(self, action)


def _open(**kwargs):
    window = SelectDialog.open(**kwargs)
    result = window.result
    button_result = getattr(window, 'button_result', None)
    del window
    utils.garbageCollect()
    return result, button_result


def select(heading, options, selected=None):
    """Single choice. Returns the chosen index or None when cancelled."""
    if not options:
        return None
    if selected is None:
        selected = []
    elif isinstance(selected, int):
        selected = [selected]
    result, _button = _open(heading=heading, options=options,
                            selected=selected, multi=False)
    return result


def select_multi(heading, options, selected=None, subtitle=None):
    """Multiple choices. Returns a list of indices or None when cancelled."""
    if not options:
        return []
    result, _button = _open(heading=heading, options=options,
                            selected=selected or [], multi=True,
                            subtitle=subtitle)
    return result


def select_ex(heading, options, selected=None, subtitle=None,
              can_toggle=None, extra_buttons=None):
    """
    Multiple choices with live-apply semantics and optional footer buttons.

    Checkbox toggles may be vetoed through can_toggle(index, checked_after).
    Clicking one of the (up to three) extra footer buttons closes the dialog;
    the caller then receives (action_key, focused_row_index) as the second
    return value.

    Returns a tuple (checked_indices_or_None, button_result_or_None).
    """
    if not options:
        return [], None
    return _open(heading=heading, options=options, multi=True,
                 selected=selected or [], subtitle=subtitle,
                 can_toggle=can_toggle, extra_buttons=extra_buttons)
