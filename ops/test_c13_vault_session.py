import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from c13_vault_session import save_session


class SessionTests(unittest.TestCase):
    def test_private_file_outside_git_and_atomic_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            save_session("SYNTHETIC-ONLY", 1000, path)
            if os.name != 'nt':
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text())["token"], "SYNTHETIC-ONLY")
            save_session("SYNTHETIC-REFRESH", 2000, path)
            self.assertEqual(json.loads(path.read_text())["expires_at"], 2000)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    @unittest.skipIf(os.name == "nt", "symlinks non garantis sous Windows ; test exécuté sous Ubuntu")
    def test_refuses_symbolic_link(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.write_text("unchanged")
            link = Path(directory) / "session.json"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                save_session("SYNTHETIC-ONLY", 1000, link)
            self.assertEqual(target.read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()
