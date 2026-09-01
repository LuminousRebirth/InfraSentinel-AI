"""统一命令行入口。

用法:
    vision-inspection infer  --scene ppe --image photo.jpg      # 推理
    vision-inspection verify                                    # 环境自检

训练请用根目录的 train_custom.py（改顶部配置直接运行）。
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__


def _verify_env() -> None:
    """打印环境/GPU 自检信息。"""
    import torch

    print(f"Python:       {sys.version.split()[0]}")
    print(f"torch:        {torch.__version__}")
    print(f"CUDA 可用:    {torch.cuda.is_available()}  (runtime {torch.version.cuda})")
    if torch.cuda.is_available():
        print(f"GPU:          {torch.cuda.get_device_name(0)}")
    try:
        from ultralytics.utils import __version__ as uy_version

        print(f"ultralytics: {uy_version}")
    except ImportError as e:
        print(f"ultralytics: ✗ {e}")
    try:
        import anomalib

        print(f"anomalib:    {anomalib.__version__}")
    except ImportError as e:
        print(f"anomalib:    ✗ {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vision-inspection",
        description="视觉巡检小模型：管道缺陷 / 安全行为",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_infer = sub.add_parser("infer", help="推理")
    p_infer.add_argument("--scene", required=True, choices=["pipeline", "ppe"])
    p_infer.add_argument("--image", required=True, help="图片路径")
    p_infer.add_argument("--conf", type=float, default=0.35, help="置信度阈值")
    p_infer.add_argument("--save", action="store_true", help="保存标注图到 runs/detect/predict/")

    sub.add_parser("verify", help="环境自检")

    args = parser.parse_args()

    if args.command == "infer":
        from .infer import infer

        result = infer(args.scene, args.image, args.conf, args.save)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.save:
            print("\n标注图已保存到: runs/detect/predict/")
    elif args.command == "verify":
        _verify_env()


if __name__ == "__main__":
    main()
