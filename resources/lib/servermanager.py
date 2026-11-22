#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
User interface for managing multiple Plex Media Servers.

Reached from the addon setting "Manage Plex servers". Runs in the main PKC
service thread so it can safely change app.CONN and request a resync.
"""
from logging import getLogger

from . import app, plex_functions as PF, utils
from .app.server import Server
from .windows import selectdialog

LOG = getLogger('PLEX.servermanager')

ADD_DISCOVERED = 'add-discovered'
ADD_MANUAL = 'add-manual'
REMOVE = 'remove'
PRIMARY = 'primary'
DONE = 'done'


def _server_labels():
    labels = []
    for server in app.CONN.servers():
        primary = ' [primary]' if server.machine_identifier \
            == app.CONN.registry.primary_id else ''
        labels.append('%s%s' % (server.name or server.machine_identifier,
                                primary))
    return labels


def _to_server(details):
    machine_identifier = details.get('machineIdentifier')
    if not machine_identifier:
        return None
    base_url = details.get('baseURL') or ''
    scheme = details.get('scheme')
    if not scheme and base_url.startswith('https'):
        scheme = 'https'
    else:
        scheme = scheme or 'http'
    ip = details.get('ip')
    if not ip and base_url:
        ip = base_url.split('://', 1)[-1].split(':', 1)[0]
    return Server(
        machine_identifier=machine_identifier,
        name=details.get('name'),
        host=ip,
        port=details.get('port') or 32400,
        https=scheme == 'https',
        token=details.get('token'),
        owned=details.get('owned', True),
    )


def _add_from_plex_tv():
    try:
        discovered = PF.discover_pms(utils.settings('plexToken')) or []
    except Exception as error:
        LOG.error('Could not discover Plex servers: %s', error)
        utils.messageDialog(utils.lang(29999), utils.lang(33002))
        return
    available = [details for details in discovered
                 if details.get('machineIdentifier') not in app.CONN.registry]
    if not available:
        utils.messageDialog(utils.lang(29999),
                            'No new Plex servers were found')
        return
    labels = ['%s (%s)' % (details.get('name'),
                           details.get('baseURL'))
              for details in available]
    index = selectdialog.select('Add Plex server', labels)
    if index is None or index < 0:
        return
    server = _to_server(available[index])
    if server is None:
        return
    app.CONN.add_server(server)
    utils.messageDialog(utils.lang(29999),
                        'Added %s' % (server.name or server.machine_identifier))


def _add_manually():
    from .initialsetup import InitialSetup
    details = InitialSetup.enter_new_pms_address()
    server = _to_server(details) if details else None
    if server is None:
        return
    app.CONN.add_server(server)
    utils.messageDialog(utils.lang(29999),
                        'Added %s' % (server.name or server.machine_identifier))


def _remove_server():
    labels = _server_labels()
    index = selectdialog.select('Remove Plex server', labels)
    if index is None or index < 0:
        return
    server = app.CONN.servers()[index]
    if not utils.yesno_dialog(
            utils.lang(29999),
            'Remove %s? Its library items will be re-synced.'
            % (server.name or server.machine_identifier)):
        return
    app.CONN.remove_server(server.machine_identifier)
    from .plex_db import PlexDB
    with PlexDB() as plexdb:
        plexdb.remove_sources_for_server(server.machine_identifier)
    utils.settings('SyncInstallRunDone', value='false')
    app.SYNC.run_lib_scan = 'full'


def _set_primary():
    labels = _server_labels()
    index = selectdialog.select('Primary Plex server', labels)
    if index is None or index < 0:
        return
    server = app.CONN.servers()[index]
    app.CONN.registry.set_primary(server.machine_identifier)
    app.CONN.load()


def manage():
    """Show the server manager until the user chooses Done."""
    actions = (ADD_DISCOVERED, ADD_MANUAL, REMOVE, PRIMARY, DONE)
    labels = ('Add Plex server from plex.tv',
              'Add Plex server manually',
              'Remove Plex server',
              'Set primary Plex server',
              'Done')
    while True:
        choices = _server_labels() + labels
        index = selectdialog.select('Manage Plex servers', choices)
        if index is None or index < 0 or index >= len(choices):
            return
        if index < len(app.CONN.servers()):
            # Selecting a server shows its details; no action needed.
            server = app.CONN.servers()[index]
            utils.messageDialog(
                server.name or server.machine_identifier,
                '%s\n%s' % (server.base_url or 'no address',
                            server.machine_identifier))
            continue
        action = actions[index - len(app.CONN.servers())]
        if action == DONE:
            return
        if action == ADD_DISCOVERED:
            _add_from_plex_tv()
        elif action == ADD_MANUAL:
            _add_manually()
        elif action == REMOVE:
            _remove_server()
        elif action == PRIMARY:
            _set_primary()
