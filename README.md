# InfraSentinel AI

Windows 本地部署的企业级管道缺陷与安全帽智能检测、分析和预警平台。

当前里程碑为 **v1.0 platform-foundation**：Conda、配置、安全存储、PostgreSQL、Redis、Milvus 预留、健康检查及既有 YOLO26 推理能力迁移。

## 初始化

```powershell
conda env update -n infrasentinel -f environment.yml --prune
powershell -ExecutionPolicy Bypass -File scripts/init.ps1
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

API 默认地址：`http://127.0.0.1:8090`；OpenAPI：`http://127.0.0.1:8090/docs`。

## 验证

```powershell
conda run -n infrasentinel python -m pytest -q
conda run -n infrasentinel python scripts/verify_environment.py
docker compose --env-file .env config --quiet
```

详细范围见 [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md)、[CAPABILITY_MAP.md](CAPABILITY_MAP.md) 和 [SPEC-platform-foundation.md](SPEC-platform-foundation.md)。
