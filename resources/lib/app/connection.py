#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Plex server connection state.

app.CONN used to be a single Connection instance. It is now a Connections
facade: one Connection per configured server plus a contextvar that selects
the "current" server. Existing code keeps reading app.CONN.server and friends
unchanged; sync/playback code opts into another server with
`with app.CONN.using_server(machine_identifier):`.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from logging import getLogger
import secrets

from .. import utils, json_rpc as js
from .server import Server, ServerRegistry

LOG = getLogger('PLEX.connection')


class Connection(object):
    """Connection details of one Plex Media Server."""

    def __init__(self, server=None):
        self.verify_ssl_cert = None
        self.ssl_cert_path = None
        self.machine_identifier = None
        self.server_name = None
        self.https = None
        self.host = None
        self.port = None
        self.server = None
        self.online = False

        if server is not None:
            self.load_from_server(server)
        else:
            self.load()

    def load_from_server(self, server):
        self.machine_identifier = server.machine_identifier
        self.server_name = server.name
        self.host = server.host
        self.port = server.port
        self.https = server.https
        self.server = server.base_url
        self.ssl_cert_path = server.ssl_cert_path
        self.verify_ssl_cert = server.verify_ssl_cert
        LOG.debug('Set server %s (%s) to %s', self.server_name,
                  self.machine_identifier, self.server)

    def load(self):
        """Legacy loader - kept for callers constructing Connection directly."""
        LOG.debug('Loading connection settings')
        self.verify_ssl_cert = None
        certificate = utils.settings('sslcert')
        self.ssl_cert_path = certificate if certificate != 'None' else None
        self.machine_identifier = utils.settings('plex_machineIdentifier') or None
        self.server_name = utils.settings('plex_servername') or None
        self.https = utils.settings('https') == 'true'
        self.host = utils.settings('ipaddress') or None
        self.port = int(utils.settings('port')) if utils.settings('port') else None
        if not self.host:
            self.server = None
        elif self.https:
            self.server = 'https://%s:%s' % (self.host, self.port)
        else:
            self.server = 'http://%s:%s' % (self.host, self.port)
        self.online = False
        LOG.debug('Set server %s (%s) to %s',
                  self.server_name, self.machine_identifier, self.server)

    def load_entrypoint(self):
        # Kept for compatibility; facade handles entrypoint instances.
        self.load()

    def clear(self):
        LOG.debug('Clearing connection settings')
        self.machine_identifier = None
        self.server_name = None
        self.https = None
        self.host = None
        self.port = None
        self.server = None


class Connections(object):
    """
    Facade behind app.CONN.

    Holds a Connection for every configured Plex server and exposes the
    classic Connection attributes for whichever server is current.
    """

    _PER_SERVER = (
        'machine_identifier', 'server_name', 'https', 'host', 'port', 'server',
        'online', 'verify_ssl_cert', 'ssl_cert_path',
    )

    def __init__(self, entrypoint=False):
        self.registry = ServerRegistry()
        self.entrypoint = entrypoint
        self._current = ContextVar('pkc_current_server', default=None)
        self.connections = {}
        # Not tied to a single server
        self.webserver_host = None
        self.webserver_port = None
        self.webserver_username = None
        self.webserver_password = None
        self.plex_transient_token = None
        self.restricted_user = False
        if not entrypoint:
            self.load_webserver()
        self.load()

    # ------------------------------------------------------- server context
    @property
    def current_id(self):
        """machineIdentifier of the server in the current thread's context."""
        return self._current.get() or self.registry.primary_id

    @property
    def current(self):
        server_id = self.current_id
        if server_id is None:
            return None
        connection = self.connections.get(server_id)
        if connection is None:
            server = self.registry.get(server_id)
            if server is None:
                return None
            connection = Connection(server)
            self.connections[server_id] = connection
        return connection

    @contextmanager
    def using_server(self, machine_identifier):
        """
        Run a block of code against a specific Plex server.

        Sync threads wrap each server in this context, and playback wraps the
        server picked by the user. All {server} URL templates keep resolving
        to app.CONN.server, which now resolves to the selected server.
        """
        if machine_identifier not in self.registry:
            LOG.warning('No connection registered for server %s',
                        machine_identifier)
        token = self._current.set(machine_identifier)
        try:
            yield self.current
        finally:
            self._current.reset(token)

    def servers(self):
        """All configured Server records."""
        return self.registry.servers()

    def enabled_servers(self):
        return self.registry.enabled_servers()

    def get_server(self, machine_identifier):
        return self.registry.get(machine_identifier)

    def add_server(self, server, primary=False):
        added = self.registry.add(server, primary=primary)
        if added is not None:
            self.load()
        return added

    def remove_server(self, machine_identifier):
        removed = self.registry.remove(machine_identifier)
        if removed:
            self.connections.pop(machine_identifier, None)
            self.load()
        return removed

    # -------------------------------------------- classic Connection API
    def _refresh_primary_from_legacy(self):
        """
        The legacy settings remain the source of truth for the *primary*
        server so that the settings dialog keeps working unchanged.
        """
        machine_identifier = utils.settings('plex_machineIdentifier') or None
        if not machine_identifier:
            return
        certificate = utils.settings('sslcert')
        server = self.registry.get(machine_identifier)
        values = dict(
            name=utils.settings('plex_servername') or None,
            host=utils.settings('ipaddress') or None,
            port=utils.settings('port') or None,
            https=utils.settings('https') == 'true',
            token=utils.settings('accessToken') or None,
            owned=utils.settings('plex_serverowned') != 'false',
            ssl_cert_path=certificate if certificate != 'None' else None,
        )
        if server is None:
            server = Server(machine_identifier=machine_identifier, **values)
            self.registry.add(server, mirror=False)
        else:
            for attribute, value in values.items():
                setattr(server, attribute, value)
            self.registry.save()
        if self.registry.primary_id is None:
            self.registry.set_primary(machine_identifier, mirror=False)

    def load(self):
        """Rebuild all per-server connections from the registry."""
        LOG.debug('Loading connection settings for all Plex servers')
        if not self.entrypoint:
            self._refresh_primary_from_legacy()
        self.connections = {}
        for server in self.registry:
            self.connections[server.machine_identifier] = Connection(server)
        LOG.info('Configured Plex servers: %s',
                 [server.base_url for server in self.registry])

    def load_entrypoint(self):
        # Secondary Python instances only need the current/primary server.
        self.load()

    def load_webserver(self):
        """PKC needs Kodi webserver to work correctly (global, not per PMS)."""
        LOG.debug('Loading Kodi webserver details')
        if not utils.settings('enableTextureCache') == 'true':
            LOG.info('Artwork caching disabled')
            return
        self.webserver_password = js.get_setting('services.webserverpassword')
        if not self.webserver_password:
            LOG.warn('No password set for the Kodi web server. Generating a '
                     'new random password')
            self.webserver_password = secrets.token_urlsafe(16)
            js.set_setting('services.webserverpassword', self.webserver_password)
        if not js.get_setting('services.webserver'):
            utils.messageDialog(utils.lang(29999), utils.lang(30004))
            js.set_setting('services.webserver', True)
            if not js.get_setting('services.webserver'):
                LOG.warn('User chose to not enable Kodi webserver')
                utils.settings('enableTextureCache', value='false')
        self.webserver_host = 'localhost'
        self.webserver_port = js.get_setting('services.webserverport')
        self.webserver_username = js.get_setting('services.webserverusername')

    def clear(self):
        LOG.debug('Clearing all connection settings')
        self.connections = {}
        for server in list(self.registry):
            self.registry.remove(server.machine_identifier, mirror=False)
        self.registry.primary_id = None
        self.registry.save()
        self.registry.mirror_legacy()

    # ------------------------------------------- delegated attributes
    def _connection_attr(self, name):
        connection = self.current
        return getattr(connection, name) if connection is not None else None

    @property
    def machine_identifier(self):
        return self._connection_attr('machine_identifier')

    @machine_identifier.setter
    def machine_identifier(self, value):
        connection = self.current
        if connection is not None:
            connection.machine_identifier = value

    @property
    def server_name(self):
        return self._connection_attr('server_name')

    @property
    def https(self):
        return self._connection_attr('https')

    @property
    def host(self):
        return self._connection_attr('host')

    @property
    def port(self):
        return self._connection_attr('port')

    @property
    def server(self):
        return self._connection_attr('server')

    @property
    def online(self):
        return self._connection_attr('online')

    @online.setter
    def online(self, value):
        connection = self.current
        if connection is not None:
            connection.online = value

    @property
    def verify_ssl_cert(self):
        return self._connection_attr('verify_ssl_cert')

    @property
    def ssl_cert_path(self):
        return self._connection_attr('ssl_cert_path')

    def __getattr__(self, name):
        # Unknown attributes fall through to the current Connection instance.
        try:
            connection = object.__getattribute__(self, 'current')
        except AttributeError:
            connection = None
        if connection is not None:
            try:
                return getattr(connection, name)
            except AttributeError:
                pass
        raise AttributeError(name)
