"""巡检质检：无参考照片质量评估（模糊 / 过曝 / 欠曝 / 对比度）。

纯规则实现，不依赖训练模型，可随时对任意照片执行。
"""

from __future__ import annotations

from pathlib import Path

import cv2


def check_quality(
    image, blur_threshold: float = 50.0, brightness_min: float = 60.0, brightness_max: float = 200.0
) -> dict:
    """评估单张图片质量。image 可为文件路径或 numpy 数组(BGR)。

    指标:
      - sharpness  清晰度(拉普拉斯方差)，越大越清晰
      - brightness 亮度均值，~128 正常，过低欠曝、过高过曝
      - contrast   对比度(灰度标准差)
    """
    if isinstance(image, (str, Path)):
        img = cv2.imread(str(image))
        if img is None:
            return {"ok": False, "error": "图片读取失败"}
    else:
        img = image

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())

    issues = []
    if sharpness < blur_threshold:
        issues.append("模糊")
    if brightness < brightness_min:
        issues.append("欠曝")
    elif brightness > brightness_max:
        issues.append("过曝")

    return {
        "ok": len(issues) == 0,
        "sharpness": round(sharpness, 1),
        "brightness": round(brightness, 1),
        "contrast": round(contrast, 1),
        "issues": issues or ["正常"],
    }
