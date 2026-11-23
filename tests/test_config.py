import os
import unittest
from unittest.mock import patch

from vlearn_importer.config import Settings


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_environment()
        self.assertEqual(settings.mode, "idle")
        self.assertEqual(settings.heartbeat_seconds, 60)

    def test_invalid_mode_is_rejected(self):
        with patch.dict(os.environ, {"WORKER_MODE": "queue"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_environment()

    def test_invalid_heartbeat_is_rejected(self):
        with patch.dict(os.environ, {"HEARTBEAT_SECONDS": "2"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_environment()
