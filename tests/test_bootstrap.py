import json
import unittest
from pathlib import Path


class HarnessBootstrapTest(unittest.TestCase):
    def test_feature_inventory_exists(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "docs" / "features.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["features"]), 3)


if __name__ == "__main__":
    unittest.main()
