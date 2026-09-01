"""巡检质检照片质量规则测试。"""

import numpy as np

from vision_inspection.quality import check_quality


def test_blank_black_image_is_underexposed():
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    r = check_quality(img)
    assert r["ok"] is False
    assert "欠曝" in r["issues"]


def test_white_image_is_overexposed():
    img = np.full((300, 300, 3), 255, dtype=np.uint8)
    r = check_quality(img)
    assert r["ok"] is False
    assert "过曝" in r["issues"]


def test_noise_image_passes():
    # 随机噪声: 高清晰度、亮度适中 → 判为正常
    rng = np.random.default_rng(42)
    img = rng.integers(0, 255, (300, 300, 3), dtype=np.uint8)
    r = check_quality(img)
    assert r["ok"] is True


def test_uniform_gray_is_blurry():
    # 纯色: 拉普拉斯方差≈0 → 模糊
    img = np.full((300, 300, 3), 128, dtype=np.uint8)
    r = check_quality(img)
    assert r["ok"] is False
    assert "模糊" in r["issues"]
