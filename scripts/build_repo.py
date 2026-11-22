#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Build the static Kodi repository served by GitHub Pages.

Produces, in <output> (default: build/pages):
    index.html
    repository.plexkodiconnect.ms-<version>.zip
    repository.plexkodiconnect.ms/            (browsable source)
    repo/addons.xml
    repo/addons.xml.md5
    repo/bin/<addon-id>/<addon-id>-<version>.zip  (+ icon/fanart per addon)

No third-party dependencies - standard library only.
"""
import argparse
import hashlib
import os
import re
import shutil
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_ID = 'plugin.video.plexkodiconnect.ms'
REPO_ID = 'repository.plexkodiconnect.ms'
PAGES_BASE = 'https://michaelishri.github.io/PlexKodiConnectMP'

MAIN_EXCLUDES = {
    '.git', '.github', '__pycache__', 'tests', 'vendor', 'repository',
    'scripts', 'build', '.pytest_cache',
}
MAIN_FILE_EXCLUDES = {'.DS_Store', '.codacy.yaml', '.gitignore'}


def addon_version(addon_dir):
    with open(os.path.join(addon_dir, 'addon.xml'), encoding='utf-8') as handle:
        content = handle.read()
    match = re.search(r'<addon[^>]*\bversion="([^"]+)"', content)
    if not match:
        raise RuntimeError('No version in %s' % addon_dir)
    return match.group(1)


def addon_body(addon_dir):
    """addon.xml without its XML declaration, for embedding in addons.xml."""
    with open(os.path.join(addon_dir, 'addon.xml'), encoding='utf-8') as handle:
        content = handle.read()
    return re.sub(r'^<\?xml.*?\?>\s*', '', content, count=1, flags=re.S).strip()


def zip_addon(source_dir, target, addon_id, excludes=(), file_excludes=()):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    count = 0
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for dirpath, dirnames, filenames in os.walk(source_dir):
            dirnames[:] = [d for d in dirnames if d not in excludes]
            relative = os.path.relpath(dirpath, source_dir)
            for name in sorted(filenames):
                if name in file_excludes or name.endswith(('.pyc', '.pyo')):
                    continue
                full = os.path.join(dirpath, name)
                arc = (os.path.join(addon_id, relative, name)
                       if relative != '.' else os.path.join(addon_id, name))
                zf.write(full, arc)
                count += 1
    print('  %s (%d files, %d bytes)' % (os.path.basename(target), count,
                                         os.path.getsize(target)))


def _find_asset(addon_dir, name):
    """Locate an asset declared in addon.xml (root or resources/)."""
    for relative in (name, os.path.join('resources', name)):
        path = os.path.join(addon_dir, relative)
        if os.path.isfile(path):
            return path
    return None


def _stage_addon(source_dir, addon_id, bin_dir, **zip_kwargs):
    """
    Kodi expects <datadir>/<addon.id>/<addon.id>-<version>.zip and looks for
    artwork in <datadir>/<addon.id>/ as well (datadir doubles as artdir).
    """
    version = addon_version(source_dir)
    target_dir = os.path.join(bin_dir, addon_id)
    os.makedirs(target_dir, exist_ok=True)
    for asset in ('icon.png', 'fanart.jpg'):
        source = _find_asset(source_dir, asset)
        if source:
            shutil.copy2(source, os.path.join(target_dir, asset))
    target = os.path.join(target_dir, '%s-%s.zip' % (addon_id, version))
    zip_addon(source_dir, target, addon_id, **zip_kwargs)
    return version


def build(output):
    if os.path.isabs(output):
        out = output
    else:
        out = os.path.join(ROOT, output)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    bin_dir = os.path.join(out, 'repo', 'bin')
    addons = []

    print('Building addon ZIPs...')
    version = _stage_addon(ROOT, MAIN_ID, bin_dir,
                           excludes=MAIN_EXCLUDES,
                           file_excludes=MAIN_FILE_EXCLUDES)
    addons.append((ROOT, version))

    for suffix in ('movies', 'tvshows'):
        addon_id = '%s.%s' % (MAIN_ID, suffix)
        source = os.path.join(ROOT, 'vendor', addon_id)
        version = _stage_addon(source, addon_id, bin_dir)
        addons.append((source, version))

    print('Generating addons.xml...')
    body = '\n\n'.join(addon_body(directory) for directory, _ in addons)
    catalogue = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                 '<addons>\n%s\n</addons>\n' % body)
    catalogue_path = os.path.join(out, 'repo', 'addons.xml')
    with open(catalogue_path, 'w', encoding='utf-8') as handle:
        handle.write(catalogue)
    with open(catalogue_path, 'rb') as handle:
        checksum = hashlib.md5(handle.read()).hexdigest()
    with open(os.path.join(out, 'repo', 'addons.xml.md5'), 'w') as handle:
        handle.write(checksum)
    print('  addons.xml (%d bytes), md5 %s' % (len(catalogue), checksum))

    print('Packaging repository addon...')
    repo_source = os.path.join(ROOT, 'repository', REPO_ID)
    repo_version = addon_version(repo_source)
    zip_addon(repo_source,
              os.path.join(out, '%s-%s.zip' % (REPO_ID, repo_version)),
              REPO_ID)
    shutil.copytree(repo_source, os.path.join(out, REPO_ID))

    index = '''<!DOCTYPE html>
<html><head><title>PlexKodiConnect Multi-Server Repository</title></head>
<body>
<h1>PlexKodiConnect Multi-Server Repository</h1>
<p>Install <a href="%s-%s.zip">%s-%s.zip</a> in Kodi via
<em>Add-ons &rarr; Install from zip file</em>, then install PlexKodiConnect
from <em>Install from repository</em>.</p>
<p><a href="repo/addons.xml">addons.xml</a></p>
</body></html>
''' % (REPO_ID, repo_version, REPO_ID, repo_version)
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as handle:
        handle.write(index)

    print('Repository written to %s' % out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='build/pages',
                        help='output directory (default: build/pages)')
    args = parser.parse_args()
    build(args.output)
