# InfraSentinel AI — Codex 工作交接台账

> 此文档是跨 Codex 对话的唯一工作交接入口。开始任何工作前先阅读；完成任何可验证工作后立即更新。不要只在对话中描述进度。

## 1. 项目摘要

- 项目：InfraSentinel AI
- 仓库目标：`https://github.com/LuminousRebirth/InfraSentinel-AI.git`
- 当前源码目录：`E:\python_code\InfraSentinel_AI`
- 旧 Demo（只读迁移来源）：`E:\python_code\yolo`
- 目标：基于现有 YOLO26 Demo 构建 Windows 本地部署的企业级管道缺陷与安全帽智能检测分析预警系统。
- 详细需求：[PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md)
- 当前阶段：v1.1 `identity-access` 已完成实现、验收与用户审查，准备归档到 GitHub。
- 当前版本：v1.1（用户审查通过，归档中）。

## 2. 已确认决策

| 项目 | 决策 |
|---|---|
| 交付形态 | Web 平台 + Windows Electron 桌面端；功能一致，桌面端额外支持离线检测与恢复同步。 |
| 部署 | Windows 本地服务器；当前 RTX 4060 笔记本为验收基准。 |
| 环境 | Conda 统一管理，必须维护 `environment.yml`。 |
| 数据 | PostgreSQL 管理业务数据；Milvus 首期部署作 RAG 预留；Redis 支撑异步任务。 |
| 视觉 | YOLO26，首期仅单路 OBS 虚拟摄像头；图片、视频、实时检测均需支持。 |
| LLM | Qwen、DeepSeek、GLM 等可扩展 API；系统级与个人 API Key 均可用；支持自动或手动分析。 |
| 权限 | 普通用户自助注册，管理员审核；仅管理员和普通用户两种角色。 |
| 数据集 | 支持已标注 YOLO 数据集导入与系统内图片/视频抽帧标注。 |
| 保留 | 原始和标注媒体默认长期保存，可授权手动删除并审计。 |
| 预警 | 规则引擎决定等级，LLM 提供多点分析；连续事件合并；完整闭环和证据链。 |
| 国际化 | 简体中文 + 英文。 |
| RAG | 第一版只预留 PostgreSQL + Milvus 与接口，不实现 Agent/RAG 问答。 |
| 版本存档 | 每完成大型模块，测试/文档完成后提交 GitHub，并按 v1.0、v1.1…打标签。 |

## 3. 版本与任务进度

| 版本 | 模块 | 状态 | 验证/备注 |
|---|---|---|---|
| v1.0 | 工程基线、Conda、Docker、数据服务、安全配置 | 完成 | 提交 `b77d245`；标签 `v1.0` 已推送；23 tests passed；健康检查 overall ready、存储容量 warning。 |
| v1.1 | 认证、审批、权限、国际化、审计基础 | 完成，用户审查通过 | 38 个 Python 测试、7 个前端测试通过；界面、深链接、API 文档和全部依赖实时健康。 |
| v1.2 | YOLO26 图片/视频/OBS 检测与记录 | 未开始 | 复用现有 `src/vision_inspection` 推理能力。 |
| v1.3 | LLM、多点分析、规则与预警闭环 | 未开始 | 依赖 v1.1、v1.2。 |
| v1.4 | 数据集、标注、训练、评估、模型治理 | 未开始 | 依赖 v1.0、v1.2。 |
| v1.5 | 工作台、报告、点位、健康、成本与设置 | 未开始 | 依赖 v1.3、v1.4。 |
| v1.6 | Electron 离线与同步、回归、部署验收 | 未开始 | 依赖 v1.1-v1.5。 |

## 4. 下一次工作应执行

1. 提交 v1.1、打 `v1.1` 标签并推送 GitHub。
2. 归档完成后为 v1.2 `vision-detection` 编写规格；未经用户批准不得提前实现。
3. 继续保护 `E:\python_code\yolo\datasets`、权重和训练产物；不得复制或提交到新仓库。

## 5. 当前风险与未决项

- 本地 `.env` 由 `scripts/init.ps1` 生成随机密钥并被 Git 忽略；任何数据集、权重、视频、运行目录和密钥均不得提交。
- E 盘仅剩 12.04 GB，已触发 900 GB 存储容量告警；进入视频、数据集和模型阶段前需要清理或扩容。
- FastAPI 0.141.1 的兼容层在测试中发出 Starlette `TestClient`/`httpx` 弃用警告，不影响运行；在官方迁移方案稳定后单独升级，禁止为消除警告盲目换依赖。
- Milvus v2.6.22 官方 Windows Compose 包实际固定服务镜像 `milvusdb/milvus:v2.6.21`，本项目跟随该官方组合。
- Docker Desktop 4.50 的 AI Inference 本地 socket 导致引擎崩溃，已备份设置并关闭 `EnableDockerAI`；运行目录仅移动到可恢复备份，未删除镜像、容器、卷或项目数据。

## 6. 交接更新模板

完成工作后复制并更新：

```markdown
### YYYY-MM-DD — [模块/任务]
- 状态：完成 / 进行中 / 阻塞
- 变更：
- 验证：
- 风险或偏差：
- 下一步：
- GitHub：提交 <sha>；标签 <version>（如适用）
```

### 2026-09-01 — v1.0 platform-foundation
- 状态：完成并通过用户审查，以 `v1.0` 里程碑归档。
- 变更：建立能力地图、模块规格和任务账本；创建并安装 `infrasentinel` Conda/Python 3.11.16 环境；初始化新项目；迁移旧 Demo 的白名单 Python/YAML/测试文件；实现 FastAPI v1 健康接口、类型化安全配置、本地存储路径隔离、SQLAlchemy/Alembic 初始 schema；增加 PostgreSQL/Redis/Milvus Compose 依赖及 Windows 初始化/启停/健康脚本。
- 验证：`23 passed`；Ruff `All checks passed`；`pip check` 无破损依赖；Docker Compose 配置通过；Windows PowerShell 5.1 解析通过；Alembic `upgrade → downgrade → upgrade` 通过并位于 `20260901_0001 (head)`；五个容器均 healthy；根路径跳转 `/docs` 且文档页返回 200；`/api/v1/health/ready` 返回 overall ready，其中 PostgreSQL/Redis/Milvus 为 ok，storage 因 E 盘仅剩 12.04 GB（低于 900 GB 告警阈值）返回 warning；停止脚本释放 8090 后重新启动成功；CUDA 可用。
- 审查：修复数据服务对所有网卡暴露、Conda 包装进程 PID 导致停止不可靠、磁盘容量警告不可见、单元测试读取 `.env` 导致假通过四项问题。未发现未解决的关键/必改项。
- 风险或偏差：E 盘剩余空间不足以支撑后续视频/数据集/模型工作；测试存在 FastAPI/Starlette `TestClient` 弃用警告；第一版尚未进入业务功能。
- 下一步：规格化并实现 v1.1 `identity-access`。
- GitHub：里程碑标签 `v1.0`；准确提交号以 Git 历史为准。

### 2026-09-01 — v1.1 identity-access specification
- 状态：规格已获用户批准；计划和任务草案待审，尚未进入实现。
- 变更：定义注册/登录/审批、数据库不透明会话、两角色与项目成员关系、首位管理员 CLI、只追加审计、统一双语错误，以及最小 React/TypeScript 身份管理界面。
- 决策：采用 `pwdlib[argon2]`；浏览器仅使用 HttpOnly Cookie；不引入 JWT、OAuth/SSO/MFA、通用权限引擎或大型前端组件库。
- 验证：规格覆盖目标、命令、目录、代码风格、测试、边界、API、数据模型和可执行成功标准；无开放问题。
- 风险或偏差：v1.1 新依赖与数据库迁移尚未实施；E 盘容量告警仍在。
- 下一步：用户批准 `tasks/plan.md` 与 `tasks/todo.md` 后，按测试驱动顺序实施 18 项任务。
- GitHub：v1.0 已推送，提交 `b77d245`，标签 `v1.0`；本规格尚未提交。

### 2026-09-01 — v1.1 identity-access implementation
- 状态：实现、测试、审查与实时验收完成，用户审查通过。
- 变更：增加 Argon2 密码、不透明数据库会话、注册与管理员审批、最后管理员并发保护、项目访问范围、Redis 原子限流、同源校验、只追加审计、统一中英文错误；新增 React/TypeScript 双语 Web UI、匿名/待审核/用户/管理员路由、用户与项目管理、审计页面及 FastAPI SPA 托管。
- 验证：Python `38 passed`；Ruff 通过；前端 `7 passed`、ESLint 与 TypeScript/Vite 构建通过；`pip check`、Compose 配置和 PowerShell 解析通过；端到端生命周期测试通过；360px/1280px 无横向溢出且交互控件具可见焦点；`/`、深链接、`/docs` 均为 200，readiness 为 ready，五个容器 healthy。
- 审查：修复管理员列表 N+1、并发降权可能留下零管理员、Redis 计数与过期非原子、状态排序不满足待审核优先、前端错误字段类型不一致及管理员操作错误不可见。无未解决的关键/必改项。
- 风险或偏差：E 盘容量告警仍在；FastAPI/Starlette 测试兼容层仍有一条已知弃用警告；云端模型 API 按用户要求留待后续提供。
- 下一步：提交、打 `v1.1` 标签并推送，再进入 v1.2 规格阶段。
- GitHub：用户已批准归档，正在提交与推送。

### 2026-09-01 — v1.1 password policy override
- 状态：按用户明确要求完成。
- 变更：密码长度由 12–128 调整为 6–128；将已注册的 `admin` 账号提升为启用管理员并重置指定初始密码；停用替代账号 `system-admin` 并撤销其会话。
- 验证：Python `38 passed`，前端 `7 passed`，Ruff/ESLint/TypeScript/Vite 全部通过；真实登录、管理员角色、退出和 readiness 验证成功。
- 风险或偏差：用户指定的六位初始密码强度较低，但仍仅以 Argon2 哈希保存；建议在密码修改界面完成后更换。
- GitHub：变更仍未提交或推送。
