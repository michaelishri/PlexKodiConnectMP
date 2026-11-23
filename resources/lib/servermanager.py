#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
User interface for managing multiple Plex Media Servers.

Reached from the addon setting "Add, remove or enable Plex servers". Runs in
the main PKC service thread so it can safely change app.CONN and request a
resync.

The manage dialog shows every server the Plex account can access in one
list: configured servers with a checkbox that toggles sync on/off, plus
servers known to plex.tv that are not configured yet (offline ones tagged as
such). Checking an unconfigured server adds and enables it. Footer buttons
act on the focused row: set it as the primary server, remove it, or add a
server manually. Checking and unchecking applies to the registry right away;
the heavy work (removing library sources, re-syncing, picking libraries for
newly added servers) happens once the dialog is closed.
"""
from logging import getLogger

from . import app, plex_functions as PF, utils
from .app.server import Server
from .windows import selectdialog

LOG = getLogger('PLEX.servermanager')

ACTION_PRIMARY = 'primary'
ACTION_REMOVE = 'remove'
ACTION_MANUAL = 'manual'


def _request_full_sync():
    """Rebuild the Kodi library after the server configuration changed."""
    utils.settings('SyncInstallRunDone', value='false')
    app.SYNC.run_lib_scan = 'full'


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


def _add_manually():
    """
    Ask for a PMS address and add that server. Returns the new server's
    machine identifier or None when the user aborted or the data was invalid.
    """
    from .initialsetup import InitialSetup
    details = InitialSetup.enter_new_pms_address()
    server = _to_server(details) if details else None
    if server is None:
        return None
    app.CONN.add_server(server)
    return server.machine_identifier


def _remove_server_by_id(machine_identifier):
    """Remove one configured server after asking for confirmation."""
    server = app.CONN.get_server(machine_identifier)
    if server is None:
        return
    if len(app.CONN.registry) <= 1:
        # The registry must never become empty - the running service and the
        # settings dialog rely on at least one server being configured
        utils.dialog('notification', heading=utils.lang(29999),
                     message=utils.lang(39970))
        return
    if not utils.yesno_dialog(
            utils.lang(29999),
            'Remove %s? Its library items will be re-synced.'
            % (server.name or machine_identifier)):
        return
    app.CONN.remove_server(machine_identifier)
    from .plex_db import PlexDB
    with PlexDB() as plexdb:
        plexdb.remove_sources_for_server(machine_identifier)
    _request_full_sync()


def _set_primary_by_id(machine_identifier):
    """Make one configured server the primary server."""
    if app.CONN.get_server(machine_identifier) is None:
        return
    app.CONN.registry.set_primary(machine_identifier)
    app.CONN.load()


def _manage_entries():
    """
    Build the unified list of servers for the manage dialog.

    Returns (entries, subtitle). Each entry is a dict with 'label', 'label2',
    'checked', 'checkbox' and 'configured'; unconfigured entries also carry
    their plex.tv 'details'. Entries never change after being built - live
    toggles are applied by _toggle_entry on the caller's side.
    """
    servers = app.CONN.servers()
    entries = []
    for server in servers:
        label = server.name or server.machine_identifier
        if server.machine_identifier == app.CONN.registry.primary_id:
            label = '%s [primary]' % label
        entries.append({
            'mid': server.machine_identifier,
            'label': label,
            'label2': server.base_url or '',
            'checked': server.enabled,
            'checkbox': True,
            'configured': True,
        })
    token = utils.settings('plexToken')
    subtitle = None
    discovered = []
    try:
        discovered = PF.discover_pms(token or None,
                                     include_gdm=not token,
                                     include_offline=True) or []
    except Exception as error:
        LOG.error('Could not discover Plex servers: %s', error)
        subtitle = utils.lang(39966)
    known = set(server.machine_identifier for server in servers)
    new_found = False
    for details in discovered:
        machine_identifier = details.get('machineIdentifier')
        if not machine_identifier or machine_identifier in known:
            continue
        new_found = True
        offline = not details.get('presence', False)
        label2 = details.get('baseURL') or details.get('ip') or ''
        if offline:
            # "(offline)"
            label2 = '%s (%s)' % (label2, utils.lang(39968)) if label2 \
                else '(%s)' % utils.lang(39968)
        entries.append({
            'mid': machine_identifier,
            'label': details.get('name') or machine_identifier,
            'label2': label2,
            'checked': False,
            'checkbox': True,
            'configured': False,
            'details': details,
        })
    if subtitle is None and discovered and not new_found:
        subtitle = utils.lang(39969)
    return entries, subtitle


def _toggle_entry(entries, index, checked, state):
    """
    Live-apply one checkbox toggle in the manage dialog. Called before the
    row's visual state flips; returns False to veto the change.

    state collects the session's changes so _finalize() can do the heavy work
    once the dialog closes.
    """
    entry = entries[index]
    if not entry['configured']:
        # Checking an unconfigured server adds and enables it right away
        if not checked:
            return True
        server = _to_server(entry['details'])
        if server is None:
            return False
        app.CONN.add_server(server)
        entry['configured'] = True
        state['needs_libraries'] = True
        return True
    machine_identifier = entry['mid']
    if checked:
        app.CONN.registry.set_enabled(machine_identifier, True)
        if machine_identifier in state['disabled']:
            state['disabled'].discard(machine_identifier)
        elif not entry['checked']:
            # Server was disabled when the dialog opened
            state['needs_libraries'] = True
        entry['checked'] = True
        return True
    # Disabling: at least one other enabled server must remain
    others = [other for other in entries
              if other['configured'] and other['checked']
              and other['mid'] != machine_identifier]
    if not others:
        # "At least one Plex server must stay enabled."
        utils.dialog('notification', heading=utils.lang(29999),
                     message=utils.lang(39967))
        return False
    app.CONN.registry.set_enabled(machine_identifier, False)
    entry['checked'] = False
    state['disabled'].add(machine_identifier)
    return True


def _finalize(state, show_picker):
    """
    Apply the deferred work after the manage dialog closed:
    remove library sources of disabled servers, optionally pick libraries for
    servers that were added or newly enabled, then request a full sync.
    """
    if state['disabled']:
        from .plex_db import PlexDB
        with PlexDB() as plexdb:
            for machine_identifier in state['disabled']:
                plexdb.remove_sources_for_server(machine_identifier)
    if show_picker and state['needs_libraries']:
        try:
            from .library_sync import sections
            sections.pick_libraries_all(None, force=True)
        except Exception as error:
            LOG.error('Could not pick libraries: %s', error)
    if state['disabled'] or state['needs_libraries']:
        _request_full_sync()


def manage():
    """
    Show the server manager until the user closes it.

    Registry-level changes (add, enable, disable) apply live; the destructive
    and long-running parts run when the dialog closes. Choosing Done offers
    the library picker when servers were added or newly enabled; cancelling
    skips that but still re-syncs in the background.
    """
    state = {'disabled': set(), 'needs_libraries': False}
    while True:
        entries, subtitle = _manage_entries()
        if not entries:
            # Nothing to configure or discover: go straight to manual entry
            _add_manually()
            return
        result, action = selectdialog.select_ex(
            utils.lang(39764),
            [{'label': entry['label'], 'label2': entry['label2'],
              'checkbox': entry['checkbox']} for entry in entries],
            selected=[index for index, entry in enumerate(entries)
                      if entry['checked']],
            subtitle=subtitle,
            can_toggle=lambda index, checked:
                _toggle_entry(entries, index, checked, state),
            extra_buttons=[(ACTION_PRIMARY, utils.lang(39963)),
                           (ACTION_REMOVE, utils.lang(39964)),
                           (ACTION_MANUAL, utils.lang(39965))])
        if action is not None:
            key, focused = action
            if key == ACTION_MANUAL:
                if _add_manually():
                    state['needs_libraries'] = True
            elif focused is not None:
                entry = entries[focused]
                if entry['configured']:
                    if key == ACTION_PRIMARY:
                        _set_primary_by_id(entry['mid'])
                    elif key == ACTION_REMOVE:
                        _remove_server_by_id(entry['mid'])
            # Reopen with the fresh state
            continue
        # Done, Cancel or back: apply the deferred work
        _finalize(state, show_picker=result is not None)
        return


def select_enabled_servers():
    """Let the user choose which configured servers PKC syncs from."""
    servers = app.CONN.servers()
    if not servers:
        utils.messageDialog(utils.lang(29999),
                            'No Plex servers configured yet')
        return
    labels = []
    for server in servers:
        primary = ' [primary]' if server.machine_identifier \
            == app.CONN.registry.primary_id else ''
        labels.append('%s%s' % (server.name or server.machine_identifier,
                                primary))
    selected = [index for index, server in enumerate(servers)
                if server.enabled]
    choice = selectdialog.select_multi('Enable Plex servers for sync',
                                       labels,
                                       selected=selected)
    if choice is None:
        return
    if not choice:
        utils.messageDialog(utils.lang(29999),
                            'At least one Plex server must remain enabled')
        return
    changed = False
    from .plex_db import PlexDB
    with PlexDB() as plexdb:
        for index, server in enumerate(servers):
            enabled = index in choice
            if server.enabled == enabled:
                continue
            app.CONN.registry.set_enabled(server.machine_identifier, enabled)
            changed = True
            if not enabled:
                plexdb.remove_sources_for_server(server.machine_identifier)
    if changed:
        _request_full_sync()
