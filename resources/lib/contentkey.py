#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Content keys used to deduplicate items coming from different Plex servers.

A Plex ratingKey is only unique within one server. To show one Kodi item for
a movie that exists on several servers we need a server-independent key. We
prefer external metadata ids (IMDb, TMDB, TVDB, AniDB) and fall back to Plex's
own guid. Seasons, episodes and tracks are keyed relative to their parent so
that they line up even when Plex assigned them different guids.
"""
from logging import getLogger

LOG = getLogger('PLEX.contentkey')

PROVIDER_PRIORITY = ('imdb', 'tmdb', 'tvdb', 'anidb')

SHOW_TYPES = ('show', 'artist')
SEASON_TYPES = ('season', 'album')
EPISODE_TYPES = ('episode', 'track')


def external_key(guids):
    """Return e.g. 'imdb:tt0111161' from a dict of Plex Guid entries."""
    if not guids:
        return None
    for provider in PROVIDER_PRIORITY:
        value = guids.get(provider)
        if value:
            return '%s:%s' % (provider, value)
    return None


def normalize_plex_guid(guid):
    """Strip agent query parameters that vary between servers."""
    if not guid:
        return None
    for separator in ('?', '#'):
        if separator in guid:
            guid = guid.split(separator, 1)[0]
    return guid or None


def from_guids(guids, plex_guid=None):
    """Content key for a top-level item (movie, show, artist, album)."""
    external = external_key(guids)
    if external:
        return external
    normalized = normalize_plex_guid(plex_guid)
    return 'plex:%s' % normalized if normalized else None


def from_xml(xml, plex_type=None):
    """
    Derive the content key for one Plex XML element.

    Returns None when there is no usable identifier, in which case the item
    is treated as server-specific and will not be deduplicated.
    """
    if xml is None:
        return None
    plex_type = plex_type or xml.get('type')
    guids = {}
    for child in xml.iter():
        if child is xml:
            continue
        if child.tag == 'Guid':
            identifier = child.get('id') or ''
            if '://' in identifier:
                provider, value = identifier.split('://', 1)
                guids[provider] = value
    guid = xml.get('guid')

    if plex_type == 'episode':
        show_key = from_guids(None, xml.get('grandparentGuid')) \
            or from_guids(guids, guid)
        season = xml.get('season')
        episode = xml.get('index') or xml.get('episode')
        if show_key and season and episode:
            return '%s/S%sE%s' % (show_key, season, episode)

    if plex_type in SEASON_TYPES + EPISODE_TYPES:
        parent_guid = xml.get('parentGuid') or xml.get('grandparentGuid')
        parent_key = from_guids(None, parent_guid)
        if plex_type == 'season':
            index = xml.get('season')
        elif plex_type == 'album':
            index = xml.get('index') or xml.get('year') or xml.get('title')
        else:
            index = xml.get('index') or xml.get('track') or xml.get('title')
        if parent_key and index:
            return '%s/%s' % (parent_key, index)

    return from_guids(guids, guid)
