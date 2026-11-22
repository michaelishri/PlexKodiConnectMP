#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Used to save PKC's application state and share between modules. Be careful
if you invoke another PKC Python instance (!!) when e.g. PKC.movies is called
"""
from .account import Account
from .application import App
from .connection import Connections
from .libsync import Sync
from .playstate import PlayState
from .playqueues import Playqueues

ACCOUNT = None
APP = None
CONN = None
SYNC = None
PLAYSTATE = None
PLAYQUEUES = None


def init(entrypoint=False):
    """
    entrypoint=True initiates only the bare minimum - for other PKC python
    instances
    """
    global ACCOUNT, APP, CONN, SYNC, PLAYSTATE, PLAYQUEUES
    APP = App(entrypoint)
    CONN = Connections(entrypoint)
    ACCOUNT = Account(entrypoint)
    SYNC = Sync(entrypoint)
    if not entrypoint:
        PLAYSTATE = PlayState()
        PLAYQUEUES = Playqueues()


def reload():
    """
    Reload PKC settings from xml file, e.g. on user-switch
    """
    global APP, SYNC
    APP.reload()
    SYNC.reload()


def using_server(machine_identifier):
    """
    Context manager selecting the Plex server for the current thread.
    Use as `with app.using_server(server_id):` around sync/playback work.
    """
    if CONN is None:
        raise RuntimeError('app.init() must be called before using_server()')
    return CONN.using_server(machine_identifier)


def current_server():
    """machineIdentifier of the server in the current thread's context."""
    return CONN.current_id if CONN is not None else None
