#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Registry of the Plex Media Servers known to PKC.

PKC used to store a single PMS as a flat set of addon settings. This module
keeps a list of servers, keyed by the PMS machineIdentifier, persisted as JSON
in the addon profile. The legacy settings are still written as a *mirror* of
the primary server so that the settings dialog and older code keep working.

A Plex account may have access to several servers; the account itself (and its
plex.tv token) is shared between all of them. The per-server PMS token can
differ, hence it is stored on each Server record.
"""
from logging import getLogger
import json
import os
import threading

from .. import utils, variables as v

LOG = getLogger('PLEX.server')

SERVERS_FILE = 'servers.json'


class Server(object):
    """Connection details for one Plex Media Server."""

    def __init__(self, machine_identifier, name=None, host=None, port=None,
                 https=False, token=None, owned=True, enabled=True,
                 last_seen=None, ssl_cert_path=None, verify_ssl_cert=None):
        self.machine_identifier = machine_identifier
        self.name = name or ''
        self.host = host or None
        self.port = int(port) if port else None
        self.https = bool(https)
        self.token = token or None
        self.owned = bool(owned)
        self.enabled = bool(enabled) if enabled is not None else True
        self.last_seen = last_seen
        self.ssl_cert_path = ssl_cert_path or None
        self.verify_ssl_cert = verify_ssl_cert

    @property
    def base_url(self):
        """The http(s)://host:port string used by all {server} URL templates."""
        if not self.host:
            return None
        scheme = 'https' if self.https else 'http'
        if self.port:
            return '%s://%s:%s' % (scheme, self.host, self.port)
        return '%s://%s' % (scheme, self.host)

    def to_dict(self):
        return {
            'machine_identifier': self.machine_identifier,
            'name': self.name,
            'host': self.host,
            'port': self.port,
            'https': self.https,
            'token': self.token,
            'owned': self.owned,
            'enabled': self.enabled,
            'last_seen': self.last_seen,
            'ssl_cert_path': self.ssl_cert_path,
            'verify_ssl_cert': self.verify_ssl_cert,
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return None
        machine_identifier = data.get('machine_identifier')
        if not machine_identifier:
            return None
        return cls(machine_identifier=machine_identifier,
                   name=data.get('name'),
                   host=data.get('host'),
                   port=data.get('port'),
                   https=data.get('https', False),
                   token=data.get('token'),
                   owned=data.get('owned', True),
                   enabled=data.get('enabled', True),
                   last_seen=data.get('last_seen'),
                   ssl_cert_path=data.get('ssl_cert_path'),
                   verify_ssl_cert=data.get('verify_ssl_cert'))

    def __repr__(self):
        return '<Server %s (%s) %s>' % (self.name, self.machine_identifier,
                                        self.base_url)


class ServerRegistry(object):
    """Thread-safe persistence of the configured Plex servers."""

    def __init__(self, path=None):
        self._path = path or os.path.join(v.ADDON_PROFILE, SERVERS_FILE)
        self._lock = threading.Lock()
        self._servers = {}
        self.primary_id = None
        self.load()

    # ------------------------------------------------------------------ io
    def load(self):
        """Load the registry, falling back to the legacy scalar settings."""
        data = None
        try:
            with open(self._path, 'r') as handle:
                data = json.load(handle)
        except (IOError, OSError, ValueError) as error:
            LOG.info('Cannot read %s (%s) - checking legacy settings',
                     self._path, error)

        if isinstance(data, dict) and data.get('servers'):
            self._servers = {}
            for entry in data['servers']:
                server = Server.from_dict(entry)
                if server is not None:
                    self._servers[server.machine_identifier] = server
            primary = data.get('primary')
            self.primary_id = primary if primary in self._servers else None
            if self.primary_id is None:
                self.primary_id = next(iter(self._servers), None)
            LOG.info('Loaded %s Plex server(s) from %s',
                     len(self._servers), self._path)
            return

        self._from_legacy_settings()

    def save(self):
        """Write the registry atomically so a crash cannot corrupt it."""
        directory = os.path.dirname(self._path)
        if directory and not os.path.isdir(directory):
            try:
                os.makedirs(directory)
            except OSError as error:
                LOG.error('Cannot create %s: %s', directory, error)
        data = {
            'primary': self.primary_id,
            'servers': [self._servers[key].to_dict()
                        for key in sorted(self._servers)],
        }
        temporary = self._path + '.tmp'
        with self._lock:
            try:
                with open(temporary, 'w') as handle:
                    json.dump(data, handle, indent=2, sort_keys=True)
                os.replace(temporary, self._path)
            except (IOError, OSError, TypeError) as error:
                LOG.error('Cannot save %s: %s', self._path, error)

    def _from_legacy_settings(self):
        """Seed the registry from the single-server settings if possible."""
        machine_identifier = utils.settings('plex_machineIdentifier') or None
        if not machine_identifier:
            LOG.info('No Plex server configured yet')
            self.primary_id = None
            return
        host = utils.settings('ipaddress') or None
        if not host:
            LOG.info('Legacy server %s has no address - ignoring',
                     machine_identifier)
            self.primary_id = None
            return
        port = utils.settings('port') or None
        server = Server(
            machine_identifier=machine_identifier,
            name=utils.settings('plex_servername') or None,
            host=host,
            port=port,
            https=utils.settings('https') == 'true',
            token=utils.settings('accessToken') or None,
            owned=utils.settings('plex_serverowned') != 'false',
            ssl_cert_path=utils.settings('sslcert')
            if utils.settings('sslcert') != 'None' else None,
        )
        self._servers = {machine_identifier: server}
        self.primary_id = machine_identifier
        LOG.info('Imported legacy server %s (%s)', server.name,
                 server.machine_identifier)
        self.save()

    # -------------------------------------------------------------- access
    @property
    def path(self):
        return self._path

    def get(self, machine_identifier):
        return self._servers.get(machine_identifier)

    def __contains__(self, machine_identifier):
        return machine_identifier in self._servers

    def __iter__(self):
        return iter(self._servers.values())

    def __len__(self):
        return len(self._servers)

    @property
    def primary(self):
        return self._servers.get(self.primary_id)

    @property
    def servers(self):
        return list(self._servers.values())

    def add(self, server, primary=False, mirror=True):
        """Add or update a server and persist the registry."""
        if not isinstance(server, Server) or not server.machine_identifier:
            return None
        self._servers[server.machine_identifier] = server
        if primary or self.primary_id is None:
            self.primary_id = server.machine_identifier
        self.save()
        if mirror and self.primary_id == server.machine_identifier:
            self.mirror_legacy()
        LOG.info('Added Plex server %s (%s)', server.name,
                 server.machine_identifier)
        return server

    def remove(self, machine_identifier, mirror=True):
        """Remove a server. Returns True when something was removed."""
        if machine_identifier not in self._servers:
            return False
        del self._servers[machine_identifier]
        if self.primary_id == machine_identifier:
            self.primary_id = next(iter(self._servers), None)
        self.save()
        if mirror:
            self.mirror_legacy()
        LOG.info('Removed Plex server %s', machine_identifier)
        return True

    def set_primary(self, machine_identifier, mirror=True):
        if machine_identifier not in self._servers:
            return False
        self.primary_id = machine_identifier
        self.save()
        if mirror:
            self.mirror_legacy()
        return True

    def update_token(self, machine_identifier, token, mirror=True):
        server = self._servers.get(machine_identifier)
        if server is None:
            return False
        server.token = token
        self.save()
        if mirror and self.primary_id == machine_identifier:
            self.mirror_legacy()
        return True

    def set_enabled(self, machine_identifier, enabled):
        """Enable or disable one Plex server for library syncing."""
        server = self._servers.get(machine_identifier)
        if server is None:
            return False
        server.enabled = bool(enabled)
        self.save()
        LOG.info('Plex server %s enabled: %s', server.name or
                 server.machine_identifier, server.enabled)
        return True

    def enabled_servers(self):
        return [server for server in self._servers.values() if server.enabled]

    def mirror_legacy(self):
        """
        Keep the old single-server settings pointing at the primary server.
        Lets the settings dialog and any un-migrated code work unchanged.
        """
        server = self.primary
        if server is None:
            return
        utils.settings('plex_machineIdentifier',
                       value=server.machine_identifier)
        utils.settings('plex_servername', value=server.name or '')
        utils.settings('plex_serverowned',
                       value='true' if server.owned else 'false')
        utils.settings('ipaddress', value=server.host or '')
        utils.settings('port', value=str(server.port or ''))
        utils.settings('https', value='true' if server.https else 'false')
        utils.settings('accessToken', value=server.token or '')
        utils.settings('sslcert', value=server.ssl_cert_path or 'None')
