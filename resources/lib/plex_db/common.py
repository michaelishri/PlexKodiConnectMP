#!/usr/bin/env python
# -*- coding: utf-8 -*-
from logging import getLogger
from threading import Lock

from .. import db, utils, variables as v
from . import schema

LOG = getLogger('PLEX.plex_db')

PLEXDB_LOCK = Lock()

SUPPORTED_KODI_TYPES = (
    v.KODI_TYPE_MOVIE,
    v.KODI_TYPE_SHOW,
    v.KODI_TYPE_SEASON,
    v.KODI_TYPE_EPISODE,
    v.KODI_TYPE_ARTIST,
    v.KODI_TYPE_ALBUM,
    v.KODI_TYPE_SONG
)


class PlexDBBase(object):
    """
    Plex database methods used for all types of items.
    """
    def __init__(self, plexconn=None, lock=True, copy=False):
        # Allows us to use this class with a cursor instead of context mgr
        self.plexconn = plexconn
        self.cursor = self.plexconn.cursor() if self.plexconn else None
        self.lock = lock
        self.copy = copy

    def __enter__(self):
        if self.lock:
            PLEXDB_LOCK.acquire()
        self.plexconn = db.connect('plex-copy' if self.copy else 'plex')
        self.cursor = self.plexconn.cursor()
        return self

    def __exit__(self, e_typ, e_val, trcbak):
        try:
            if e_typ:
                # re-raise any exception
                return False
            self.plexconn.commit()
        finally:
            self.plexconn.close()
            if self.lock:
                PLEXDB_LOCK.release()

    def is_recorded(self, plex_id, plex_type, server_id=None):
        """
        FAST method to check whether a ratingKey has been recorded for the
        current Plex server.
        """
        server_id = self._server_id(server_id)
        self.cursor.execute(
            'SELECT plex_id FROM %s WHERE server_id = ? AND plex_id = ?'
            % self._table(plex_type), (server_id, plex_id))
        return self.cursor.fetchone() is not None

    def item_by_id(self, plex_id, plex_type=None, server_id=None):
        """
        Returns the item for plex_id on one Plex server, or None.
        Supply plex_type to speed up lookup.
        """
        server_id = self._server_id(server_id)
        if plex_type is None:
            for kind in (v.PLEX_TYPE_MOVIE,
                         v.PLEX_TYPE_EPISODE,
                         v.PLEX_TYPE_SHOW,
                         v.PLEX_TYPE_SEASON,
                         v.PLEX_TYPE_SONG,
                         v.PLEX_TYPE_ALBUM,
                         v.PLEX_TYPE_ARTIST):
                answ = self.item_by_source(server_id, plex_id, kind)
                if answ:
                    return answ
            return None
        if plex_type in (v.PLEX_TYPE_CLIP, v.PLEX_TYPE_PHOTO,
                         v.PLEX_TYPE_PLAYLIST):
            return None
        return self.item_by_source(server_id, plex_id, plex_type)

    # ------------------------------------------------------- multi-server
    @staticmethod
    def _table(plex_type):
        return 'track' if plex_type == v.PLEX_TYPE_SONG else plex_type

    @staticmethod
    def _server_id(server_id=None):
        if server_id is not None:
            return server_id
        from .. import app
        return app.current_server() or ''

    def is_recorded_on_server(self, plex_id, plex_type, server_id=None):
        """Check a ratingKey within one specific Plex server."""
        table = self._table(plex_type)
        self.cursor.execute(
            'SELECT plex_id FROM %s WHERE server_id = ? AND plex_id = ?'
            % table, (self._server_id(server_id), plex_id))
        return self.cursor.fetchone() is not None

    def item_by_source(self, server_id, plex_id, plex_type):
        """Return the row for a (server, ratingKey) pair."""
        table = self._table(plex_type)
        entry_method = getattr(self, 'entry_to_%s' % table, None)
        self.cursor.execute(
            'SELECT * FROM %s WHERE server_id = ? AND plex_id = ? LIMIT 1'
            % table, (self._server_id(server_id), plex_id))
        row = self.cursor.fetchone()
        if row is None or entry_method is None:
            return row
        return entry_method(row)

    def item_by_content(self, content_key, plex_type, server_id=None):
        """
        Return a row for a content key, preferring the current/primary server.
        Because all sources of one content item share a kodi_id, any row is
        enough to identify the Kodi library item.
        """
        table = self._table(plex_type)
        wanted = self._server_id(server_id)
        self.cursor.execute(
            'SELECT * FROM %s WHERE content_key = ? '
            'ORDER BY (server_id = ?) DESC LIMIT 1' % table,
            (content_key, wanted))
        row = self.cursor.fetchone()
        if row is None:
            return None
        entry_method = getattr(self, 'entry_to_%s' % table, None)
        return entry_method(row) if entry_method else row

    def sources_by_content(self, content_key, plex_type):
        """All (server_id, plex_id) rows that carry the same content."""
        table = self._table(plex_type)
        self.cursor.execute(
            'SELECT server_id, plex_id, checksum, section_id, last_sync '
            'FROM %s WHERE content_key = ?' % table, (content_key, ))
        return self.cursor.fetchall()

    def content_key_by_id(self, plex_id, plex_type, server_id=None):
        table = self._table(plex_type)
        self.cursor.execute(
            'SELECT content_key FROM %s WHERE server_id = ? AND plex_id = ?'
            % table, (self._server_id(server_id), plex_id))
        row = self.cursor.fetchone()
        return row[0] if row else None

    def upsert_source(self, server_id, plex_id, plex_type, content_key,
                      checksum=None, section_id=None, kodi_id=None, **kwargs):
        """
        Insert or update one server's copy of an item. Returns the kodi_id
        that should be used for the canonical Kodi item.
        """
        table = self._table(plex_type)
        provided = {
            'server_id': self._server_id(server_id),
            'plex_id': plex_id,
            'content_key': content_key,
        }
        for key in ('checksum', 'section_id', 'kodi_id', 'plex_guid',
                    'kodi_fileid', 'kodi_pathid', 'kodi_fileid_2',
                    'show_id', 'parent_id', 'fanart_synced', 'last_sync',
                    'trailer_synced'):
            if key == 'checksum':
                value = checksum
            elif key == 'section_id':
                value = section_id
            elif key == 'kodi_id':
                value = kodi_id
            else:
                value = kwargs.get(key)
            if value is not None:
                provided[key] = value
        columns = [key for key in provided if key in schema.COLUMNS[table]]
        values = [provided[key] for key in columns]
        updates = ', '.join('%s = excluded.%s' % (column, column)
                            for column in columns
                            if column not in ('server_id', 'plex_id'))
        query = ('INSERT INTO %s (%s) VALUES (%s) '
                 'ON CONFLICT(server_id, plex_id) DO UPDATE SET %s'
                 % (table, ', '.join(columns),
                    ', '.join('?' for _ in columns), updates))
        self.cursor.execute(query, values)
        return kodi_id

    def remove_source(self, server_id, plex_id, plex_type):
        table = self._table(plex_type)
        self.cursor.execute(
            'DELETE FROM %s WHERE server_id = ? AND plex_id = ?' % table,
            (self._server_id(server_id), plex_id))

    def remove_sources_for_server(self, server_id):
        """Drop every item sourced from one Plex server."""
        existing = set(row[0] for row in self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"))
        for table in schema.COLUMNS:
            if table not in existing:
                continue
            self.cursor.execute('DELETE FROM %s WHERE server_id = ?' % table,
                                (self._server_id(server_id), ))

    def source_count(self, content_key, plex_type):
        table = self._table(plex_type)
        self.cursor.execute('SELECT COUNT(*) FROM %s WHERE content_key = ?'
                            % table, (content_key, ))
        return self.cursor.fetchone()[0]

    def set_kodi_id(self, content_key, plex_type, kodi_id, server_id=None):
        """Share one Kodi item id between all sources of the same content."""
        table = self._table(plex_type)
        self.cursor.execute(
            'UPDATE %s SET kodi_id = ? WHERE content_key = ?' % table,
            (kodi_id, content_key))

    def configured_servers(self):
        self.cursor.execute('SELECT * FROM server')
        return self.cursor.fetchall()

    def items_by_guid(self, plex_guid, plex_type=None):
        """
        Returns a list of items for plex_guid or an empty list.
        Supply with the correct plex_type to speed up lookup
        """
        answ = list()
        if plex_type == v.PLEX_TYPE_MOVIE:
            answ = self.movies_by_guid(plex_guid)
        elif plex_type == v.PLEX_TYPE_EPISODE:
            answ = self.episodes_by_guid(plex_guid)
        elif plex_type == v.PLEX_TYPE_SHOW:
            answ = self.shows_by_guid(plex_guid)
        elif plex_type == v.PLEX_TYPE_SEASON:
            answ = self.seasons_by_guid(plex_guid)
        elif plex_type is None:
            # SLOW - lookup plex_id in all our tables
            for kind in (v.PLEX_TYPE_MOVIE,
                         v.PLEX_TYPE_EPISODE,
                         v.PLEX_TYPE_SHOW,
                         v.PLEX_TYPE_SEASON):
                method = getattr(self, kind + "s_by_guid")
                answ = method(plex_guid)
                if answ:
                    break
        return answ

    def item_by_kodi_id(self, kodi_id, kodi_type):
        """
        """
        if kodi_type not in SUPPORTED_KODI_TYPES:
            return
        self.cursor.execute('SELECT * from %s WHERE kodi_id = ? LIMIT 1'
                            % v.PLEX_TYPE_FROM_KODI_TYPE[kodi_type],
                            (kodi_id, ))
        method = getattr(self, 'entry_to_%s' % v.PLEX_TYPE_FROM_KODI_TYPE[kodi_type])
        return method(self.cursor.fetchone())

    def plex_id_by_last_sync(self, plex_type, last_sync, limit):
        """
        Returns an iterator for all items where the last_sync is NOT identical
        """
        query = '''
            SELECT plex_id FROM %s WHERE last_sync <> ? LIMIT %s
        ''' % (plex_type, limit)
        return (x[0] for x in self.cursor.execute(query, (last_sync, )))

    def checksum(self, plex_id, plex_type, server_id=None):
        """
        Returns the checksum for plex_id on the current Plex server.
        """
        server_id = self._server_id(server_id)
        self.cursor.execute(
            'SELECT checksum FROM %s WHERE server_id = ? AND plex_id = ? '
            'LIMIT 1' % self._table(plex_type), (server_id, plex_id))
        try:
            return self.cursor.fetchone()[0]
        except TypeError:
            pass

    def update_last_sync(self, plex_id, plex_type, last_sync, server_id=None):
        """Sets a new timestamp for plex_id on one Plex server."""
        server_id = self._server_id(server_id)
        self.cursor.execute(
            'UPDATE %s SET last_sync = ? WHERE server_id = ? AND plex_id = ?'
            % self._table(plex_type), (last_sync, server_id, plex_id))

    def remove(self, plex_id, plex_type):
        """
        Removes the item from our Plex db
        """
        self.cursor.execute('DELETE FROM %s WHERE plex_id = ?' % plex_type, (plex_id, ))

    def every_plex_id(self, plex_type, offset, limit):
        """
        Returns an iterator for plex_type for every single plex_id
        Will start with records at DB position offset [int] and return limit
        [int] number of items
        """
        return (x[0] for x in
                self.cursor.execute('SELECT plex_id FROM %s LIMIT %s OFFSET %s'
                                    % (plex_type, limit, offset)))

    def missing_fanart(self, plex_type, offset, limit):
        """
        Returns an iterator for plex_type for all plex_id, where fanart_synced
        has not yet been set to 1
        Will start with records at DB position offset [int] and return limit
        [int] number of items
        """
        query = '''
            SELECT plex_id FROM %s WHERE fanart_synced = 0
            LIMIT %s OFFSET %s
        ''' % (plex_type, limit, offset)
        return (x[0] for x in self.cursor.execute(query))

    def missing_trailers(self, plex_type, offset, limit):
        """
        Returns an iterator for plex_type for all plex_id, where trailer_synced
        has not yet been set to 1
        Will start with records at DB position offset [int] and return limit
        [int] number of items
        """
        query = '''
            SELECT plex_id FROM %s WHERE trailer_synced = 0
            LIMIT %s OFFSET %s
        ''' % (plex_type, limit, offset)
        return (x[0] for x in self.cursor.execute(query))

    def set_fanart_synced(self, plex_id, plex_type):
        """
        Toggles fanart_synced to 1 for plex_id
        """
        self.cursor.execute('UPDATE %s SET fanart_synced = 1 WHERE plex_id = ?' % plex_type,
                            (plex_id, ))

    def set_trailer_synced(self, plex_id, plex_type):
        """
        Toggles fanart_synced to 1 for plex_id
        """
        self.cursor.execute('UPDATE %s SET trailer_synced = 1 WHERE plex_id = ?' % plex_type,
                            (plex_id, ))

    def plexid_by_sectionid(self, section_id, plex_type, limit):
        query = '''
            SELECT plex_id FROM %s WHERE section_id = ? LIMIT %s
        ''' % (plex_type, limit)
        return (x[0] for x in self.cursor.execute(query, (section_id, )))

    def kodiid_by_sectionid(self, section_id, plex_type):
        return (x[0] for x in
                self.cursor.execute('SELECT kodi_id FROM %s WHERE section_id = ?' % plex_type,
                                    (section_id, )))


def initialize():
    """
    Run once upon PKC startup to verify that the plex db exists and uses the
    multi-server schema.
    """
    with PlexDBBase() as plexdb:
        schema.initialize(plexdb.cursor)
        legacy_id = utils.settings('plex_machineIdentifier') or None
        if schema.migrate(plexdb.cursor, legacy_id):
            LOG.info('Migrated plex.db to the multi-server schema')
            # Old rows are attributed to the legacy server but their content
            # keys are only guesses. A full resync rebuilds them correctly.
            utils.settings('SyncInstallRunDone', value='false')
        plexdb.cursor.execute('''
            INSERT OR REPLACE INTO version(idVersion)
            VALUES (?)
        ''', (v.ADDON_VERSION, ))
        _sync_server_table(plexdb.cursor)


def _sync_server_table(cursor):
    """Copy the known Plex servers into the plex.db server table."""
    registry = None
    try:
        from .. import app
        if app.CONN is not None:
            registry = app.CONN.registry
    except (ImportError, AttributeError):
        pass
    if registry is not None:
        servers = list(registry)
    else:
        machine_identifier = utils.settings('plex_machineIdentifier') or None
        servers = []
        if machine_identifier:
            from ..app.server import Server
            servers = [Server(machine_identifier=machine_identifier,
                              host=utils.settings('ipaddress') or None)]
    for server in servers:
        cursor.execute('''
            INSERT OR REPLACE INTO server(
                machine_identifier, name, base_url, token, enabled, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (server.machine_identifier, server.name, server.base_url,
                server.token, int(server.enabled), server.last_seen))



def wipe(table=None):
    """
    Completely resets the Plex database.
    If a table [unicode] name is provided, only that table will be dropped
    """
    with PlexDBBase() as plexdb:
        if table:
            tables = [table]
        else:
            plexdb.cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            tables = [i[0] for i in plexdb.cursor.fetchall()]
        for table in tables:
            plexdb.cursor.execute('DROP table IF EXISTS %s' % table)
