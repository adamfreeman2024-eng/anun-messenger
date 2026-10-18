"""The local command writes a WAV and does not claim a call."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spike.demo import run


class DemoTest(unittest.TestCase):
    def test_local_run_writes_wav(self) -> None:
        with TemporaryDirectory() as tmp:
            result = run(Path(tmp))
            self.assertEqual(result["sent"], 4)
            self.assertEqual(result["letter"], "տեղային")
            self.assertTrue(result["file_ok"])
            self.assertEqual(result["frames"], 2)
            self.assertTrue(Path(result["wav"]).is_file())
            self.assertFalse(result["private_on_disk"])
            self.assertIn("աուդիտ", result["alert"])


if __name__ == "__main__":
    unittest.main()
