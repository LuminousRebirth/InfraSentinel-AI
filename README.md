# InfraSentinel AI

Windows 本地部署的企业级管道缺陷与安全帽智能检测、分析和预警平台。

当前开发里程碑为 **v1.2 vision-detection**：在身份、项目权限和审计基础上，增加本地 YOLO 图片、视频与单路 OBS 虚拟摄像头检测、持久任务队列、双 worker、检测记录和中英文 Web 界面。

## 初始化

```powershell
conda env update -n infrasentinel -f environment.yml --prune
powershell -ExecutionPolicy Bypass -File scripts/init.ps1
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

系统界面：`http://127.0.0.1:8090/`；OpenAPI：`http://127.0.0.1:8090/docs`。

首次使用前，在 `.env` 中填写 `INFRASENTINEL_BOOTSTRAP_ADMIN_EMAIL`、`INFRASENTINEL_BOOTSTRAP_ADMIN_USERNAME`、`INFRASENTINEL_BOOTSTRAP_ADMIN_PASSWORD` 与 `INFRASENTINEL_BOOTSTRAP_ADMIN_DISPLAY_NAME`，然后运行：

```powershell
conda run -n infrasentinel infrasentinel init-admin
```

普通用户可以在系统界面申请账户，管理员批准并分配项目后即可登录。云端模型 API 尚未接入；相关凭据后续仅通过环境变量配置。

## 本地视觉模型

模型文件不复制进仓库。在 `.env` 中配置已有只读资产路径：

```dotenv
INFRASENTINEL_PIPELINE_PT=E:/path/to/pipeline/best.pt
INFRASENTINEL_PIPELINE_ENGINE=E:/path/to/pipeline/best.engine
INFRASENTINEL_PPE_PT=E:/path/to/ppe/best.pt
INFRASENTINEL_PPE_ENGINE=E:/path/to/ppe/best.engine
```

启动脚本会执行迁移、同步模型并启动 API 和两个独立视觉 worker。也可以单独同步：

```powershell
conda run -n infrasentinel python -m infrasentinel.cli sync-vision-models
```

登录后从“智能检测”提交图片或视频，或在 OBS Virtual Camera 已启动时开启实时检测；“检测记录”提供进度、取消、重试、原始/标注媒体和检测对象详情。视频标注输出为 H.264 MP4，当前版本不保留音频。

常用运维命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/health.ps1
powershell -ExecutionPolicy Bypass -File scripts/stop.ps1
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

## 验证

```powershell
conda run -n infrasentinel python -m pytest -q
conda run -n infrasentinel python scripts/verify_environment.py
docker compose --env-file .env config --quiet
Push-Location frontend; npm run lint; npm run test -- --run; npm run build; Pop-Location
```

详细范围见 [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md)、[CAPABILITY_MAP.md](CAPABILITY_MAP.md)、[SPEC-platform-foundation.md](SPEC-platform-foundation.md)、[SPEC-identity-access.md](SPEC-identity-access.md) 和 [SPEC-vision-detection.md](SPEC-vision-detection.md)。
