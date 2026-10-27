import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from growth_photos import date_of, grow, iou, merge_boxes, mosaic  # noqa: E402

B = lambda x, y, w, h, **k: {"x": x, "y": y, "w": w, "h": h, **k}


class BoxTest(unittest.TestCase):
    def test_date(self):
        self.assertEqual(date_of("photo_2024-02-20_19-04-10.jpg"), "2024-02-20")
        self.assertEqual(date_of("KakaoTalk_20250316_1321.jpg"), "2025-03-16")
        self.assertEqual(date_of("a.jpg"), "")

    def test_iou_and_merge(self):
        self.assertEqual(iou(B(0, 0, 10, 10), B(20, 20, 5, 5)), 0)
        m = merge_boxes([B(0, 0, 100, 100), B(10, 10, 100, 100), B(300, 300, 20, 20), B(20, 20, 10, 10)])
        self.assertEqual(len(m), 2)
        self.assertEqual((m[0]["x"], m[0]["w"]), (0, 110))

    def test_grow_small_more(self):
        big = grow(B(100, 100, 100, 100), 1000, 1000)
        small = grow(B(100, 100, 40, 40), 1000, 1000)
        self.assertEqual(big, (75, 65, 225, 225))
        self.assertLess(small[0], 100 - 40 * 0.25)
        self.assertEqual(grow(B(0, 0, 50, 50), 60, 60)[:2], (0, 0))          # 사진 밖으로 안 나감


class MosaicTest(unittest.TestCase):
    def test_masks_others_keeps_owner(self):
        rng = np.random.default_rng(0)
        img = rng.integers(0, 255, (200, 300, 3), dtype=np.uint8)
        out = mosaic(img, [B(20, 20, 60, 60), B(200, 20, 60, 60, keep=True)])
        self.assertFalse(np.array_equal(out[30:70, 30:70], img[30:70, 30:70]))   # 다른 사람: 바뀜
        self.assertLess(out[30:70, 30:70].std(), img[30:70, 30:70].std() / 3)   # 세부가 뭉개짐
        self.assertTrue(np.array_equal(out[20:80, 200:260], img[20:80, 200:260]))   # 본인: 그대로
        self.assertTrue(np.array_equal(img, img.copy()))                         # 원본은 안 건드림


if __name__ == "__main__":
    unittest.main()
