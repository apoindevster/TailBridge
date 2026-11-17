"""Contrast checks for the small physical display's actual foreground pairs."""
import unittest
from tailbridge.ui import BG, PANEL, INK, MUTED, ACCENT, CYAN, ORANGE, LINE, SELECTED


def luminance(color):
    channels = [int(color[n:n + 2], 16) / 255 for n in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return sum(v * w for v, w in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(first, second):
    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


class ThemeTests(unittest.TestCase):
    def test_small_text_contrast(self):
        for foreground, background in ((INK, BG), (INK, PANEL), (MUTED, BG), (MUTED, PANEL),
                                       (BG, ACCENT), (BG, CYAN), (CYAN, BG), (CYAN, SELECTED), (ORANGE, BG)):
            with self.subTest(foreground=foreground, background=background):
                self.assertGreaterEqual(contrast(foreground, background), 4.5)

    def test_control_edges_and_focus_contrast(self):
        for foreground in (LINE, CYAN):
            for background in (BG, PANEL):
                self.assertGreaterEqual(contrast(foreground, background), 3)
