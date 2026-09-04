# InfraSentinel AI

Windows 本地部署的企业级管道缺陷与安全帽智能检测、分析和预警平台。

当前开发分支已完成 **v1.4 dataset-model-lifecycle**：在 v1.3 告警研判基础上，增加项目级数据集、版本与质检、浏览器框选标注、YOLO 导入导出、异步训练/评估、模型发布、项目部署与回滚。云端模型未配置时规则告警和本地数据/模型生命周期仍可完整运行。

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

普通用户可以在系统界面申请账户，管理员批准并分配项目后即可登录。管理员可在“模型设置”中配置系统模型地址和写入式密钥，普通用户可在“告警中心”配置个人密钥；密钥加密保存且不会回显。

## 本地视觉模型

模型文件不复制进仓库。在 `.env` 中配置已有只读资产路径：

```dotenv
INFRASENTINEL_PIPELINE_PT=E:/path/to/pipeline/best.pt
INFRASENTINEL_PIPELINE_ENGINE=E:/path/to/pipeline/best.engine
INFRASENTINEL_PPE_PT=E:/path/to/ppe/best.pt
INFRASENTINEL_PPE_ENGINE=E:/path/to/ppe/best.engine
```

启动脚本会执行迁移、同步模型、写入默认告警规则，并启动 API、两个视觉 worker 和一个智能分析 worker。也可以单独执行：

```powershell
conda run -n infrasentinel python -m infrasentinel.cli sync-vision-models
conda run -n infrasentinel python -m infrasentinel.cli seed-alert-rules
conda run -n infrasentinel python -m infrasentinel.cli backfill-intelligence
```

登录后从“智能检测”提交图片或视频，或在 OBS Virtual Camera 已启动时开启实时检测；“检测记录”提供进度、取消、重试、原始/标注媒体和检测对象详情。视频标注输出为 H.264 MP4，当前版本不保留音频。

## 数据与模型生命周期

管理员从“数据与训练”创建项目数据集，可导入 JPEG/PNG/WebP、常见视频或 YOLO ZIP。草稿版本支持框选标注、复核、撤销/重做、稳定的 80/10/10 拆分和质量检查；冻结后可导出、训练与评估。发布会再次校验评估结果、模型卡和权重哈希，部署与回滚均按项目显式执行并保留审计记录。

开发验收默认使用完整流程的假训练器，不下载任何模型权重：

```dotenv
INFRASENTINEL_LIFECYCLE_FAKE_RUNNER=true
```

使用真实 Ultralytics 训练时将该值设为 `false`，并在训练配置中提供已经存在的可信本地 `.pt` 路径。数据、导出、训练运行与权重均保存在 `INFRASENTINEL_STORAGE_ROOT`，不进入 Git。

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

详细范围见 [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md)、[CAPABILITY_MAP.md](CAPABILITY_MAP.md)、[SPEC-platform-foundation.md](SPEC-platform-foundation.md)、[SPEC-identity-access.md](SPEC-identity-access.md)、[SPEC-vision-detection.md](SPEC-vision-detection.md)、[SPEC-alert-intelligence.md](SPEC-alert-intelligence.md) 和 [SPEC-dataset-model-lifecycle.md](SPEC-dataset-model-lifecycle.md)。
