#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Schema of PKC's plex.db, including the multi-server migration.

Every table is keyed by (server_id, local id) since Plex ratingKeys and
section ids are only unique within one Plex Media Server. Items from several
servers that represent the same content share a kodi_id, which is how the
Kodi library stays deduplicated.
"""
from logging import getLogger

LOG = getLogger('PLEX.plex_db.schema')

# Columns (without the constraints) of the multi-server tables.
COLUMNS = {
    # The original columns come first so existing entry_to_* parsers, which
    # use positional row indexes, keep working. server_id/content_key are
    # appended at the end.
    'sections': ('section_id', 'section_name', 'plex_type', 'kodi_tagid',
                 'sync_to_kodi', 'last_sync', 'server_id'),
    'movie': ('plex_id', 'plex_guid', 'checksum', 'section_id', 'kodi_id',
              'kodi_fileid', 'kodi_pathid', 'fanart_synced', 'trailer_synced',
              'last_sync', 'server_id', 'content_key'),
    'show': ('plex_id', 'plex_guid', 'checksum', 'section_id', 'kodi_id',
             'kodi_pathid', 'fanart_synced', 'last_sync',
             'server_id', 'content_key'),
    'season': ('plex_id', 'plex_guid', 'checksum', 'section_id', 'show_id',
               'parent_id', 'kodi_id', 'fanart_synced', 'last_sync',
               'server_id', 'content_key'),
    'episode': ('plex_id', 'plex_guid', 'checksum', 'section_id', 'show_id',
                'grandparent_id', 'season_id', 'parent_id', 'kodi_id',
                'kodi_fileid', 'kodi_fileid_2', 'kodi_pathid', 'fanart_synced',
                'last_sync', 'server_id', 'content_key'),
    'artist': ('plex_id', 'checksum', 'section_id', 'kodi_id', 'last_sync',
               'server_id', 'content_key'),
    'album': ('plex_id', 'checksum', 'section_id', 'artist_id', 'parent_id',
              'kodi_id', 'last_sync', 'server_id', 'content_key'),
    'track': ('plex_id', 'checksum', 'section_id', 'artist_id',
              'grandparent_id', 'album_id', 'parent_id', 'kodi_id',
              'kodi_pathid', 'last_sync', 'server_id', 'content_key'),
    'playlists': ('plex_id', 'plex_name', 'plex_updatedat', 'kodi_path',
                  'kodi_type', 'kodi_hash', 'server_id'),
}

PRIMARY_KEYS = {
    'sections': '(server_id, section_id)',
    'playlists': '(server_id, plex_id)',
}
for _table in ('movie', 'show', 'season', 'episode', 'artist', 'album',
               'track'):
    PRIMARY_KEYS[_table] = '(server_id, plex_id)'

MEDIA_TABLES = tuple(table for table in COLUMNS
                     if table not in ('sections', 'playlists'))


def _create_table(cursor, table):
    columns = COLUMNS[table]
    definitions = []
    for column in columns:
        if column == 'server_id':
            definitions.append('server_id TEXT NOT NULL DEFAULT \'\'')
        elif column == 'content_key':
            definitions.append('content_key TEXT')
        elif column == 'plex_id':
            definitions.append('plex_id INTEGER NOT NULL')
        elif column == 'section_id' and table == 'sections':
            definitions.append('section_id INTEGER NOT NULL')
        elif column.endswith('_id') or column == 'checksum':
            definitions.append('%s INTEGER' % column)
        elif column in ('plex_name', 'kodi_path', 'kodi_type', 'kodi_hash',
                        'section_name', 'plex_type', 'plex_guid',
                        'content_key', 'server_id'):
            definitions.append('%s TEXT' % column)
        else:
            definitions.append('%s INTEGER' % column)
    definitions.append('PRIMARY KEY %s' % PRIMARY_KEYS[table])
    cursor.execute('CREATE TABLE IF NOT EXISTS %s(%s)'
                   % (table, ', '.join(definitions)))


def _create_indexes(cursor):
    existing = set(row[0] for row in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"))
    commands = []
    for table in MEDIA_TABLES:
        commands.extend((
            'CREATE INDEX IF NOT EXISTS ix_%s_last_sync ON %s (last_sync)'
            % (table, table),
            'CREATE INDEX IF NOT EXISTS ix_%s_kodi_id ON %s (kodi_id)'
            % (table, table),
            'CREATE INDEX IF NOT EXISTS ix_%s_server ON %s (server_id)'
            % (table, table),
            'CREATE INDEX IF NOT EXISTS ix_%s_content ON %s (content_key)'
            % (table, table),
            'CREATE INDEX IF NOT EXISTS ix_%s_checksum ON %s (server_id, checksum)'
            % (table, table),
        ))
        if 'plex_guid' in COLUMNS[table]:
            commands.append(
                'CREATE INDEX IF NOT EXISTS ix_%s_plex_guid ON %s (plex_guid)'
                % (table, table))
    commands.extend((
        'CREATE INDEX IF NOT EXISTS ix_sections_server ON sections (server_id)',
        'CREATE INDEX IF NOT EXISTS ix_playlists_server ON playlists (server_id)',
        'CREATE INDEX IF NOT EXISTS ix_playlists_kodi_path ON playlists (kodi_path)',
        'CREATE INDEX IF NOT EXISTS ix_playlists_kodi_hash ON playlists (kodi_hash)',
    ))
    for command in commands:
        table = command.split(' ON ', 1)[-1].split(' ', 1)[0] \
            if ' ON ' in command else None
        if table is not None and table not in existing:
            continue
        cursor.execute(command)


def initialize(cursor):
    """Create the multi-server tables and indexes if they do not exist."""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS version(
            idVersion TEXT PRIMARY KEY)
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server(
            machine_identifier TEXT PRIMARY KEY,
            name TEXT,
            base_url TEXT,
            token TEXT,
            enabled INTEGER,
            last_seen INTEGER)
    ''')
    for table in COLUMNS:
        _create_table(cursor, table)
    _create_indexes(cursor)


def _columns(cursor, table):
    return [row[1] for row in cursor.execute('PRAGMA table_info(%s)' % table)]


def migrate(cursor, legacy_server_id):
    """
    Rebuild the old single-server tables with a server_id dimension.

    Returns True if anything was migrated. Existing rows are attributed to
    `legacy_server_id`; their content_key is seeded from plex_guid so that a
    later full sync can refine it.
    """
    if not legacy_server_id:
        LOG.warning('No legacy machineIdentifier - cannot migrate plex.db')
        return False

    migrated = False
    for table in COLUMNS:
        existing = _columns(cursor, table)
        if not existing or 'server_id' in existing:
            continue
        LOG.info('Migrating plex.db table %s to multi-server schema', table)
        old_table = '%s_old' % table
        cursor.execute('DROP TABLE IF EXISTS %s' % old_table)
        cursor.execute('ALTER TABLE %s RENAME TO %s' % (table, old_table))

        # Create the replacement without the IF NOT EXISTS shortcut: the old
        # table has just been renamed, so its name is free again.
        _create_table(cursor, table)

        # server_id / content_key are new; the legacy rows all belong to the
        # one PMS that was configured before the upgrade.
        columns = []
        for column in COLUMNS[table]:
            if column == 'server_id':
                columns.append("'%s'" % legacy_server_id.replace("'", "''"))
            elif column == 'content_key':
                columns.append('plex_guid' if 'plex_guid' in existing else 'NULL')
            elif column in existing:
                columns.append(column)
            else:
                columns.append('NULL')
        values_sql = ', '.join(columns)
        cursor.execute('INSERT INTO %s (%s) SELECT %s FROM %s'
                       % (table, ', '.join(COLUMNS[table]), values_sql,
                          old_table))
        cursor.execute('DROP TABLE %s' % old_table)
        migrated = True

    if migrated:
        _create_indexes(cursor)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server(
                machine_identifier TEXT PRIMARY KEY,
                name TEXT,
                base_url TEXT,
                token TEXT,
                enabled INTEGER,
                last_seen INTEGER)
        ''')
        cursor.execute('INSERT OR REPLACE INTO server('
                       'machine_identifier, name, enabled) VALUES (?, ?, 1)',
                       (legacy_server_id, legacy_server_id))
    return migrated
