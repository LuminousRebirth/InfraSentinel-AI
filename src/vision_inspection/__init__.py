"""视觉巡检小模型：管道缺陷 / 安全行为 / 设备异常 / 巡检质检。"""

import os
import sys
from pathlib import Path

__version__ = "0.1.0"

# 处理 ultralytics 源码目录遮蔽：
# 项目根下的 `ultralytics/`（源码 git 仓库根，无 __init__.py）会以 namespace 包
# 遮蔽真正安装的 ultralytics 包。检测到该情况时把项目根从 sys.path 剔除，
# 让可编辑安装的真实包生效。目录改名为 ultralytics-src 后可移除此段。
_project_root = Path(__file__).resolve().parent.parent.parent
_yolo_config_root = _project_root / "runtime" / "ultralytics"
_yolo_config_root.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(_yolo_config_root))
_shadow = _project_root / "ultralytics"
if _shadow.exists() and not (_shadow / "__init__.py").exists():
    for _p in list(sys.path):
        try:
            if Path(_p).resolve() == _project_root:
                sys.path.remove(_p)
        except OSError:
            pass
