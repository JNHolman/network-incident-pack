import re
import unittest
from pathlib import Path

from incidentpack import __version__


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_package_and_project_versions_match(self):
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, flags=re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)


if __name__ == "__main__":
    unittest.main()
