#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validate the generated Kodi repository layout against the current spec."""
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestRepoBuild(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.output = tempfile.mkdtemp(prefix='pkc-repo-test-')
        subprocess.check_call([
            sys.executable, os.path.join(ROOT, 'scripts', 'build_repo.py'),
            '--output', cls.output,
        ], cwd=ROOT)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.output, ignore_errors=True)

    def test_catalogue_and_checksum(self):
        catalogue = os.path.join(self.output, 'repo', 'addons.xml')
        root = ET.parse(catalogue).getroot()
        self.assertEqual(
            [addon.get('id') for addon in root],
            ['plugin.video.plexkodiconnect.ms',
             'plugin.video.plexkodiconnect.ms.movies',
             'plugin.video.plexkodiconnect.ms.tvshows'])
        with open(catalogue, 'rb') as handle:
            expected = hashlib.md5(handle.read()).hexdigest()
        with open(catalogue + '.md5') as handle:
            self.assertEqual(handle.read().strip(), expected)

    def test_zip_paths_match_kodi_layout(self):
        """
        Kodi resolves a repository package as:
            <datadir>/<addon.id>/<addon.id>-<version>.zip
        See xbmc/addons/addoninfo/AddonInfoBuilder.cpp.
        """
        bin_dir = os.path.join(self.output, 'repo', 'bin')
        catalogue = ET.parse(os.path.join(self.output, 'repo', 'addons.xml'))
        for addon in catalogue.getroot():
            addon_id = addon.get('id')
            version = addon.get('version')
            zip_path = os.path.join(bin_dir, addon_id,
                                    '%s-%s.zip' % (addon_id, version))
            self.assertTrue(os.path.isfile(zip_path),
                            'missing Kodi-style package: %s' % zip_path)
            with zipfile.ZipFile(zip_path) as archive:
                self.assertEqual(set(entry.split('/')[0]
                                     for entry in archive.namelist()),
                                 {addon_id})
                self.assertIn(addon_id + '/addon.xml', archive.namelist())
        self.assertEqual(glob.glob(os.path.join(bin_dir, '*.zip')), [])

    def test_each_addon_directory_has_its_assets(self):
        bin_dir = os.path.join(self.output, 'repo', 'bin')
        for addon_dir in os.listdir(bin_dir):
            for asset in ('icon.png', 'fanart.jpg'):
                self.assertTrue(
                    os.path.isfile(os.path.join(bin_dir, addon_dir, asset)),
                    '%s missing from %s' % (asset, addon_dir))

    def test_repository_addon_uses_dir_schema(self):
        repository = ET.parse(os.path.join(
            ROOT, 'repository', 'repository.plexkodiconnect.ms', 'addon.xml'))
        extension = next(
            element for element in repository.getroot().findall('extension')
            if element.get('point') == 'xbmc.addon.repository')
        self.assertIsNotNone(extension.find('dir'),
                             'repository must use the <dir> schema (Kodi 20+)')
        self.assertIsNone(extension.find('info'),
                          'old flat <info> definition is no longer supported')
        dir_element = extension.find('dir')
        for tag in ('info', 'checksum', 'datadir'):
            self.assertIsNotNone(dir_element.find(tag), tag)
        self.assertNotIn('zip', dir_element.find('datadir').attrib)

    def test_repository_installer_zip(self):
        archives = glob.glob(os.path.join(
            self.output, 'repository.plexkodiconnect.ms-*.zip'))
        self.assertEqual(len(archives), 1)
        with zipfile.ZipFile(archives[0]) as archive:
            self.assertIn('repository.plexkodiconnect.ms/addon.xml',
                          archive.namelist())
            self.assertIn('repository.plexkodiconnect.ms/icon.png',
                          archive.namelist())


if __name__ == '__main__':
    unittest.main(verbosity=2)
