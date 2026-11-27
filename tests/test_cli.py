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


class StructuredCliTests(unittest.TestCase):
    def test_generates_and_parses_templates_for_every_kind(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from vlearn_importer.structured import CONTRACT

        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main(["templates", "--output", directory]), 0)
            self.assertEqual(
                {path.name for path in Path(directory).iterdir()},
                {
                    f"{kind.lower()}.{extension}"
                    for kind in CONTRACT["kinds"]
                    for extension in ("csv", "xlsx", "docx")
                },
            )
            for kind, spec in CONTRACT["kinds"].items():
                results = []
                for extension in ("csv", "xlsx", "docx"):
                    path = Path(directory) / f"{kind.lower()}.{extension}"
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(main(["parse", str(path), "--kind", kind]), 0)
                    [row] = json.loads(output.getvalue())["rows"]
                    self.assertEqual(row["row"], 2)
                    self.assertEqual(list(row["values"]), spec["columns"])
                    results.append(row["values"])
                self.assertEqual(results[0], results[1])
                self.assertEqual(results[0], results[2])
