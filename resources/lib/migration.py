#!/usr/bin/env python
# -*- coding: utf-8 -*-
from logging import getLogger

from . import variables as v
from . import utils
###############################################################################

LOG = getLogger('PLEX.migration')


def migrate_addon_id_settings():
    """
    This fork uses its own addon id. On first run, copy the settings and the
    server registry from the original PKC addon profile so users do not have
    to configure their servers and account again.
    """
    import os
    import shutil
    import xbmcvfs

    old_profile = xbmcvfs.translatePath(
        'special://profile/addon_data/plugin.video.plexkodiconnect/')
    new_profile = v.ADDON_PROFILE
    marker = os.path.join(new_profile, '.pkc_ms_settings_migrated')
    if os.path.exists(marker) or not os.path.isdir(old_profile):
        return
    if not os.path.isdir(new_profile):
        os.makedirs(new_profile)
    copied = []
    for name in ('settings.xml', 'servers.json'):
        source = os.path.join(old_profile, name)
        target = os.path.join(new_profile, name)
        if os.path.exists(source) and not os.path.exists(target):
            try:
                shutil.copy2(source, target)
                copied.append(name)
            except (IOError, OSError) as error:
                LOG.error('Could not copy %s: %s', source, error)
    LOG.info('Migrated settings from original PKC profile: %s', copied)
    try:
        with open(marker, 'w') as handle:
            handle.write('done')
    except (IOError, OSError):
        pass


def check_migration():
    migrate_addon_id_settings()
    LOG.info('Checking whether we need to migrate something')
    last_migration = utils.settings('last_migrated_PKC_version')
    # Ensure later migration if user downgraded PKC!
    utils.settings('last_migrated_PKC_version', value=v.ADDON_VERSION)

    if last_migration == '':
        LOG.info('New, clean PKC installation - no migration necessary')
        return
    elif last_migration == v.ADDON_VERSION:
        LOG.info('Already migrated to PKC version %s' % v.ADDON_VERSION)
        return

    if not utils.compare_version(last_migration, '3.0.4'):
        LOG.info('Migrating to version 3.0.4')
        # Add an additional column `trailer_synced` in the Plex movie table
        from .plex_db import PlexDB
        with PlexDB() as plexdb:
            query = 'ALTER TABLE movie ADD trailer_synced BOOLEAN'
            plexdb.cursor.execute(query)
            # Index will be automatically recreated on next PKC startup

    if not utils.compare_version(last_migration, '3.7.0'):
        LOG.info('Migrating to version 3.7.0')
        from .library_sync import sections
        sections.delete_videonode_files()
        utils.reboot_kodi()

    utils.settings('last_migrated_PKC_version', value=v.ADDON_VERSION)
