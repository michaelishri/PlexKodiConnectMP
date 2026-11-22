#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Minimal Kodi stand-ins so the pure-Python parts of PKC can be unit tested
outside of Kodi. Import this module before importing resources.lib.*.
"""
import os
import sys
import types

SETTINGS = {}
WINDOW_PROPS = {}


class FakeAddon(object):
    def __init__(self, *args, **kwargs):
        pass

    def getSetting(self, key):
        return SETTINGS.get(key, '')

    def setSetting(self, key, value):
        SETTINGS[key] = str(value)

    def getLocalizedString(self, key):
        return ''

    def getAddonInfo(self, key):
        return {
            'version': '3.12.6',
            'path': os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'profile': '/tmp/opencode/pkc-test-profile/',
        }.get(key, '')


class FakePlayList(object):
    def __init__(self, *args, **kwargs):
        self.items = []

    def __len__(self):
        return len(self.items)

    def getposition(self):
        return 0

    def clear(self):
        self.items = []


class FakePlayer(object):
    def __init__(self, *args, **kwargs):
        pass

    def isPlaying(self):
        return False

    def getPlayingFile(self):
        return ''


class FakeWindow(object):
    def __init__(self, *args, **kwargs):
        pass

    def setProperty(self, key, value):
        WINDOW_PROPS[key] = str(value)

    def getProperty(self, key):
        return WINDOW_PROPS.get(key, '')

    def clearProperty(self, key):
        WINDOW_PROPS.pop(key, None)


def install():
    """Install the Kodi modules into sys.modules and return the settings dict."""
    NUMERIC_DEFAULTS = {
        'companionPort': '3005', 'companionUpdatePort': '32412',
        'fullSyncInterval': '60', 'syncThreadNumber': '10',
        'limitindex': '200', 'backgroundsync_saftyMargin': '5',
        'useDirectPaths': '0', 'trailerNumber': '3',
        'enableAutoHideSkipTime': '10', 'audioStreamPick': '0',
        'subtitleStreamPick': '0', 'resumeJumpBack': '10',
        'playType': '0', 'transcoderVideoQualities': '5',
        'maxVideoQualities': '11', 'transcodeH265': '0',
        'transcodeAV1': '0', 'audioBoost': '0', 'subtitleSize': '100',
        'kodi_video_cache': '20971520', 'failedCount': '0',
        'widgetLimit': '30', 'fetch_pms_item_number': '50',
        'startupDelay': '0',
    }
    for key, value in NUMERIC_DEFAULTS.items():
        SETTINGS.setdefault(key, value)
    SETTINGS.setdefault('deviceName', 'PKC-test')
    SETTINGS.setdefault('enableTextureCache', 'false')
    SETTINGS.setdefault('myplexlogin', 'false')
    SETTINGS.setdefault('plex_client_Id', 'pkctest-client-id')

    xbmc = types.ModuleType('xbmc')
    xbmc.getLanguage = lambda *args, **kwargs: 'en'
    xbmc.getInfoLabel = lambda key: '21' if 'BuildVersion' in key else ''
    xbmc.getCondVisibility = lambda key: False
    xbmc.getLocalizedString = lambda key: ''
    xbmc.executebuiltin = lambda command: None
    xbmc.executeJSONRPC = lambda request: '{}'
    xbmc.PlayList = FakePlayList
    xbmc.Player = FakePlayer
    xbmc.PLAYLIST_MUSIC = 0
    xbmc.PLAYLIST_VIDEO = 1
    xbmc.sleep = lambda ms: None
    xbmc.log = lambda message, level=0: None
    xbmc.ISO_639_1 = 2
    xbmc.ISO_639_2 = 3
    xbmc.PLAYER_CORE_MPLAYER = 0
    xbmc.LOGDEBUG = 0
    xbmc.LOGINFO = 1
    xbmc.LOGWARNING = 2
    xbmc.LOGERROR = 3

    xbmcaddon = types.ModuleType('xbmcaddon')
    xbmcaddon.Addon = FakeAddon

    xbmcgui = types.ModuleType('xbmcgui')
    xbmcgui.Window = FakeWindow
    xbmcgui.Dialog = object
    xbmcgui.ListItem = object
    xbmcgui.ACTION_PREVIOUS_MENU = 10
    xbmcgui.ACTION_NAV_BACK = 92

    xbmcvfs = types.ModuleType('xbmcvfs')
    xbmcvfs.translatePath = lambda path: path.replace(
        'special://profile', '/tmp/opencode/pkc-test-profile').replace(
        'special://home', '/tmp/opencode/pkc-test-home')

    sys.modules.setdefault('xbmc', xbmc)
    sys.modules.setdefault('xbmcaddon', xbmcaddon)
    sys.modules.setdefault('xbmcgui', xbmcgui)
    sys.modules.setdefault('xbmcvfs', xbmcvfs)
    return SETTINGS
