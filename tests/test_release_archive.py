import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.verify_release import verify_archive


class ReleaseArchiveTests(unittest.TestCase):
    def _archive(self, *members: str) -> Path:
        temp_dir = Path(tempfile.mkdtemp())
        archive_path = temp_dir / "release.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for member in members:
                archive.writestr(member, "test")
        return archive_path

    def test_accepts_clean_versioned_archive(self):
        archive = self._archive(
            "network-incident-pack-v1.1.3/README.md",
            "network-incident-pack-v1.1.3/SECURITY.md",
            "network-incident-pack-v1.1.3/docs/live_demo_real.png",
            "network-incident-pack-v1.1.3/incidentpack/__init__.py",
        )
        verify_archive(archive)

    def test_rejects_missing_public_demo_asset(self):
        archive = self._archive(
            "network-incident-pack-v1.1.3/README.md",
            "network-incident-pack-v1.1.3/SECURITY.md",
        )
        with self.assertRaisesRegex(ValueError, "missing required files"):
            verify_archive(archive)

    def test_rejects_virtual_environment(self):
        archive = self._archive(
            "network-incident-pack-v1.1.3/README.md",
            "network-incident-pack-v1.1.3/SECURITY.md",
            "network-incident-pack-v1.1.3/docs/live_demo_real.png",
            "network-incident-pack-v1.1.3/.venv/bin/python",
        )
        with self.assertRaisesRegex(ValueError, "forbidden artifacts"):
            verify_archive(archive)

    def test_rejects_git_metadata_and_python_cache(self):
        for member in (
            "network-incident-pack-v1.1.3/.git/config",
            "network-incident-pack-v1.1.3/incidentpack/__pycache__/cli.pyc",
            "network-incident-pack-v1.1.3/network_incident_pack.egg-info/PKG-INFO",
        ):
            with self.subTest(member=member):
                archive = self._archive(
                    "network-incident-pack-v1.1.3/README.md",
                    "network-incident-pack-v1.1.3/SECURITY.md",
                    "network-incident-pack-v1.1.3/docs/live_demo_real.png",
                    member,
                )
                with self.assertRaisesRegex(ValueError, "forbidden artifacts"):
                    verify_archive(archive)


if __name__ == "__main__":
    unittest.main()
