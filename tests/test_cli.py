import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from vlearn_importer.__main__ import main


class CliTests(unittest.TestCase):
    def test_check_command(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"WORKER_MODE": "idle"}, clear=True):
            with redirect_stdout(output):
                code = main(["check"])
        self.assertEqual(code, 0)
        self.assertIn("importer OK", output.getvalue())
