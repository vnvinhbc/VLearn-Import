import hashlib
import os
import unittest
from importlib.resources import files
from pathlib import Path

# SHA-256 of VLearn's src/shared/contracts/import-formats.json for version 1.
CONTRACT_SHA256 = "53a857f62164eba8ab565d7bd270f436769ebf530a31acebff7bf93d8c7138d9"


class ImportContractTests(unittest.TestCase):
    def test_packaged_contract_matches_vlearn_snapshot(self):
        packaged = files("vlearn_importer").joinpath("import-formats.json").read_bytes()
        self.assertEqual(hashlib.sha256(packaged).hexdigest(), CONTRACT_SHA256)

        explicit_path = os.environ.get("VLEARN_IMPORT_CONTRACT")
        sibling_contract = (
            Path(__file__).resolve().parents[2] / "vlearn/src/shared/contracts/import-formats.json"
        )
        if explicit_path or sibling_contract.is_file():
            source = Path(explicit_path) if explicit_path else sibling_contract
            self.assertEqual(packaged, source.read_bytes())
