#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Skin textures use the media folder name, not the addon id."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, 'resources', 'skins', 'Main')
MEDIA = os.path.join(SKIN, 'media')
MEDIA_FOLDER = 'plugin.video.plexkodiconnect'


class TestSkinPaths(unittest.TestCase):

    def test_no_forked_addon_id_in_skin_texture_paths(self):
        for directory, _, files in os.walk(SKIN):
            for name in files:
                if not name.endswith(('.xml', '.py')):
                    continue
                path = os.path.join(directory, name)
                with open(path, encoding='utf-8') as handle:
                    text = handle.read()
                self.assertNotIn(
                    MEDIA_FOLDER + '.ms/', text,
                    '%s still points textures at the forked addon id' % path)

    def test_pin_login_images_point_at_existing_files(self):
        signin = os.path.join(ROOT, 'resources', 'lib', 'windows', 'signin.py')
        with open(signin, encoding='utf-8') as handle:
            text = handle.read()
        self.assertIn(MEDIA_FOLDER + '/sign_in/digits/', text)

        expected = ['sign_in/pin-display.jpg',
                    'sign_in/generating-code.jpg',
                    'sign_in/linking-account.jpg']
        for relative in expected:
            self.assertTrue(os.path.exists(os.path.join(MEDIA, MEDIA_FOLDER,
                                                        relative)), relative)

    def test_static_texture_references_exist(self):
        missing = []
        xml_dir = os.path.join(SKIN, '1080i')
        for name in os.listdir(xml_dir):
            if not name.endswith('.xml'):
                continue
            with open(os.path.join(xml_dir, name), encoding='utf-8') as handle:
                text = handle.read()
            for texture in re.findall(r'<texture[^>]*>([^<]+)</texture>', text):
                for path in re.findall(
                        r'plugin\.video\.plexkodiconnect/[^"\'\s\]]+',
                        texture):
                    if '$INFO' in path:
                        continue
                    if not os.path.exists(os.path.join(MEDIA, path)):
                        missing.append((name, path))
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
