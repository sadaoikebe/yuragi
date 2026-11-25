"""Windows' keyboard setting picks the keyboard (docs/JIS.md §2)."""
from __future__ import annotations

import unittest

from yuragi.chord.keys import KEYBOARDS, VK_OEM_3, VK_OEM_4
from yuragi.ime.keyboard_setting import keyboard_for


class KeyboardSettingTest(unittest.TestCase):
    def test_the_key_right_of_p_names_the_keyboard(self):
        self.assertIs(keyboard_for(VK_OEM_3), KEYBOARDS["jis106"])  # @ on kbd106
        self.assertIs(keyboard_for(VK_OEM_4), KEYBOARDS["ansi101"])  # [ on kbd101
        self.assertIs(keyboard_for(None), KEYBOARDS["ansi101"])  # no Japanese layout


if __name__ == "__main__":
    unittest.main()
