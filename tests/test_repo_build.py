#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validate the generated Kodi repository layout."""
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

    def test_zip_layout(self):
        bin_dir = os.path.join(self.output, 'repo', 'bin')
        archives = sorted(os.listdir(bin_dir))
        self.assertEqual(len(archives), 3)
        for name in archives:
            with zipfile.ZipFile(os.path.join(bin_dir, name)) as archive:
                tops = set(entry.split('/')[0] for entry in archive.namelist())
                addon_id = name.rsplit('-', 1)[0]
                self.assertEqual(tops, {addon_id})
                self.assertIn(addon_id + '/addon.xml', archive.namelist())
                self.assertFalse(any('tests' in top for top in tops))

    def test_repository_installer_zip(self):
        path = os.path.join(self.output, 'repository.plexkodiconnect.ms-1.0.0.zip')
        with zipfile.ZipFile(path) as archive:
            self.assertIn('repository.plexkodiconnect.ms/addon.xml',
                          archive.namelist())
            self.assertIn('repository.plexkodiconnect.ms/icon.png',
                          archive.namelist())


if __name__ == '__main__':
    unittest.main(verbosity=2)
