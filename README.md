# InfraSentinel AI

Windows 本地部署的企业级管道缺陷与安全帽智能检测、分析和预警平台。

当前开发里程碑为 **v1.1 identity-access**：在 v1.0 平台基础上增加中英文 Web 界面、账户申请与审核、会话认证、项目访问范围和不可变审计轨迹。

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

## 验证

```powershell
conda run -n infrasentinel python -m pytest -q
conda run -n infrasentinel python scripts/verify_environment.py
docker compose --env-file .env config --quiet
Push-Location frontend; npm run lint; npm run test -- --run; npm run build; Pop-Location
```

详细范围见 [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md)、[CAPABILITY_MAP.md](CAPABILITY_MAP.md) 和 [SPEC-platform-foundation.md](SPEC-platform-foundation.md)。
