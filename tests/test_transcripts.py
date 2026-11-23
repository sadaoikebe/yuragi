from __future__ import annotations

from pathlib import Path
import unittest

from tests.transcript import run_transcript
from tests import support  # noqa: F401 (Mozc の品詞名)

CASES = sorted((Path(__file__).parent / "transcripts").glob("*.json"))
if not CASES:
    raise RuntimeError("no IME transcripts found")


class TranscriptTest(unittest.TestCase):
    pass


def transcript_test(path):
    def test(self):
        run_transcript(self, path)
    return test


for path in CASES:
    setattr(TranscriptTest, "test_" + path.stem, transcript_test(path))

if __name__ == "__main__":
    unittest.main()
