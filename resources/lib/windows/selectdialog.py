#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kodi-native looking selection dialog with a real checkbox on every row.

PKC used xbmcgui.Dialog().select()/multiselect() for several choices. Those
dialogs are rendered by the active Kodi skin, and some skins indicate the
selection only by changing the text colour. This window is drawn by PKC's own
Main skin so every row has an explicit enabled/checked indicator.
"""
import xbmc
import xbmcgui

from . import kodigui
from .. import utils, variables as v


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

    def __init__(self, *args, **kwargs):
        kodigui.BaseDialog.__init__(self, *args, **kwargs)
        self.heading = kwargs.get('heading') or ''
        self.options = list(kwargs.get('options') or [])
        self.multi = bool(kwargs.get('multi', False))
        self.selected = set(index for index in (kwargs.get('selected') or [])
                            if 0 <= index < len(self.options))
        self.result = None
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
        self.list = kodigui.ManagedControlList(self, self.LIST_ID,
                                               max(1, len(self.options)))
        items = []
        for index, option in enumerate(self.options):
            item = kodigui.ManagedListItem(str(option), data_source=index)
            item.setProperty('checkbox', '1')
            item.setBoolProperty('checked', index in self.selected)
            items.append(item)
        self.items = items
        self.list.addItems(items)
        self._update_subtitle()
        self.setBoolProperty('initialized', True)
        xbmc.Monitor().waitForAbort(0.1)
        self.setFocusId(self.LIST_ID)

    def _update_subtitle(self):
        if not self.multi:
            return
        self.setProperty('subtitle', '%s / %s' % (len(self.selected),
                                                 len(self.options)))

    def _toggle(self):
        item = self.list.getSelectedItem()
        if not item:
            return
        index = item.dataSource
        if index in self.selected:
            self.selected.discard(index)
            item.setBoolProperty('checked', False)
        else:
            self.selected.add(index)
            item.setBoolProperty('checked', True)
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

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU,
                              xbmcgui.ACTION_NAV_BACK):
            self.result = None
            self.doClose()
            return
        kodigui.BaseDialog.onAction(self, action)


def select(heading, options, selected=None):
    """Single choice. Returns the chosen index or None when cancelled."""
    if not options:
        return None
    if selected is None:
        selected = []
    elif isinstance(selected, int):
        selected = [selected]
    window = SelectDialog.open(heading=heading, options=options,
                               selected=selected, multi=False)
    result = window.result
    del window
    utils.garbageCollect()
    return result


def select_multi(heading, options, selected=None):
    """Multiple choices. Returns a list of indices or None when cancelled."""
    if not options:
        return []
    window = SelectDialog.open(heading=heading, options=options,
                               selected=selected or [], multi=True)
    result = window.result
    del window
    utils.garbageCollect()
    return result
