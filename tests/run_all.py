#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run all PKC multi-server unit tests (no Kodi installation required)."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = ['test_multiserver.py', 'test_dedup_db.py', 'test_playback_picker.py',
         'test_repo_build.py']

if __name__ == '__main__':
    failed = False
    for name in TESTS:
        print('\n=== %s ===' % name)
        result = subprocess.call(
            [sys.executable, os.path.join(ROOT, 'tests', name)], cwd=ROOT)
        failed = failed or result != 0
    sys.exit(1 if failed else 0)
