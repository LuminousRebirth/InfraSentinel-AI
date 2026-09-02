# InfraSentinel AI — Codex 工作交接台账

> 此文档是跨 Codex 对话的唯一工作交接入口。开始任何工作前先阅读；完成任何可验证工作后立即更新。不要只在对话中描述进度。

## 1. 项目摘要

- 项目：InfraSentinel AI
- 仓库目标：`https://github.com/LuminousRebirth/InfraSentinel-AI.git`
- 当前源码目录：`E:\python_code\InfraSentinel_AI`
- 旧 Demo（只读迁移来源）：`E:\python_code\yolo`
- 目标：基于现有 YOLO26 Demo 构建 Windows 本地部署的企业级管道缺陷与安全帽智能检测分析预警系统。
- 详细需求：[PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md)
- 当前阶段：v1.2 `vision-detection` 已于 2026-09-02 通过用户审阅，后续开发继续留在独立分支。
- 当前版本：v1.2 位于 `codex/v1.2-vision-detection`；按用户要求，后续提交仅推送此开发分支，整个系统完成前不合并 `main`、不推送新标签。v1.1 为提交 `4509f8b`、标签 `v1.1`。

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
| v1.2 | YOLO26 图片/视频/OBS 检测与记录 | 完成，用户审阅通过 | 53 个 Python 测试、9 个前端测试及实机图片/视频检测通过；真实 OBS 摄像头未启用。 |
| v1.3 | LLM、多点分析、规则与预警闭环 | 未开始 | 依赖 v1.1、v1.2。 |
| v1.4 | 数据集、标注、训练、评估、模型治理 | 未开始 | 依赖 v1.0、v1.2。 |
| v1.5 | 工作台、报告、点位、健康、成本与设置 | 未开始 | 依赖 v1.3、v1.4。 |
| v1.6 | Electron 离线与同步、回归、部署验收 | 未开始 | 依赖 v1.1-v1.5。 |

## 4. 下一次工作应执行

1. 后续模块继续在 `codex/v1.2-vision-detection` 开发并只推送该分支；整个系统完成后再由用户决定何时合并 `main` 和建立标签。
2. 启动 OBS Virtual Camera 后补做真实单路一小时验收；仿真 OBS 流程已通过。
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
- GitHub：提交 `4509f8b`，标签 `v1.1`，均已推送。

### 2026-09-01 — v1.2 vision-detection specification
- 状态：规格已于 2026-09-02 获用户批准，并授权不中断实施至最终审阅。
- 范围：YOLO26 图片、视频、单路 OBS 检测；PostgreSQL 持久任务队列；双 Windows worker；原始/标注媒体和检测记录；项目与所有者权限；中英文 Web 流程。
- 默认：旧 Demo 的 `.pt`/ONNX/TensorRT 仅作为环境配置指向的只读验收资产，不复制、不下载、不提交；TensorRT 优先、`.pt` 回退；项目暂作点位边界；事件合并、规则、LLM、预警、报告、删除、模型生命周期和 Electron 后移至既定里程碑。
- 技术约束：只新增 `python-multipart`；不引入 Celery/RQ/通用工作流框架，使用 PostgreSQL 原子认领与租约恢复，Redis 仅保存短期 OBS 预览。
- 下一步：按已生成的 v1.2 实施计划和 15 项任务连续构建，完成后交用户最终审阅。

### 2026-09-01 — v1.1 password policy override
- 状态：按用户明确要求完成。
- 变更：密码长度由 12–128 调整为 6–128；将已注册的 `admin` 账号提升为启用管理员并重置指定初始密码；停用替代账号 `system-admin` 并撤销其会话。
- 验证：Python `38 passed`，前端 `7 passed`，Ruff/ESLint/TypeScript/Vite 全部通过；真实登录、管理员角色、退出和 readiness 验证成功。
- 风险或偏差：用户指定的六位初始密码强度较低，但仍仅以 Argon2 哈希保存；建议在密码修改界面完成后更换。
- GitHub：包含在提交 `4509f8b` 与标签 `v1.1` 中，均已推送。

### 2026-09-02 — v1.2 vision-detection implementation
- 状态：实现、审查与除真实 OBS 一小时运行外的验收已完成，并于 2026-09-02 通过用户审阅。
- 变更：新增视觉模型部署登记与可逆迁移；图片批量和视频流式上传、解码验证、容量/频率限制与安全存储；PostgreSQL 持久队列、租约恢复、取消/重试和两个 Windows worker；图片/视频/OBS 推理、H.264 标注视频、关键帧、观测与性能指标；项目/所有者权限和审计；中英文智能检测、历史、详情与可重连 OBS 预览界面。
- 模型：外部管道 `.pt` 版本 `40bc77143faf`、PPE `.pt` 版本 `ac797446c4e5` 已幂等登记，文件保持只读且未复制进仓库；TensorRT 配置存在但当前实机验收自动回退到 PyTorch，任务结果记录实际 backend。
- 验证：Python `53 passed`（保留一条已知 Starlette TestClient 弃用警告）；Ruff、`pip check` 通过；前端 `9 passed`，ESLint、TypeScript/Vite 构建通过；PowerShell 5.1 解析、Compose 配置、Alembic `upgrade → downgrade → upgrade`、模型重复同步通过；CUDA 可用（RTX 4060 Laptop GPU）；真实管道图片得到 1 个 `SG`，真实 PPE 短视频 10/10 帧、71 个 helmet、H.264 输出成功；最终在线任务 `1c4d61c3-2700-4e31-ad56-71dcf7d2fe50` 由双 worker 完成，进度 100%、PT 后端、1 个检测、2 个媒体、1 条观测；readiness 为 ready、2/2 worker、2/2 模型和五个 healthy 容器；360px 页面无横向溢出。
- 审查：修复上传事务失败的孤儿文件、列表 N+1、耗尽重试任务卡死、模型加载异常逃出 worker、视频转码临时文件、PID 复用误停、健康检查只数 PID 文件、OBS 资源清理/分辨率/重连、前端异步错误和 Blob URL 泄漏；普通用户横向越权被 API 和媒体测试拒绝，管理员访问通过。无未解决的关键/必改审查项。
- 风险或偏差：OBS Virtual Camera 在索引 0 未开启，仿真捕获/Redis/取消/设备失败已通过但真实一小时验收待补；视频元数据使用 OpenCV 而非独立 FFprobe；模型同步不单独跑 TensorRT smoke，而由 worker 加载时验证并回退；详情暂取前 200 条观测且未提供游标分页；GPU 利用率/显存字段预留但未采样。E 盘约 11.9 GB 可用，仍处于容量告警。
- 运维：`scripts/start.ps1` 自动迁移、同步模型、构建前端并启动 API + 2 worker；`scripts/health.ps1` 检查依赖；`scripts/stop.ps1` 仅停止校验过命令行的项目进程并保留 Docker 卷和媒体。Docker Desktop 4.50 再次生成不可访问的 AI/secrets socket 时，已备份设置到 `settings-store.pre-recovery-20260902-145004.json`，并将故障目录移动为 `run-stale-20260902-145004`、`docker-secrets-engine-stale-20260902-145334`、`run-stale-20260902-145649`；均可恢复，未删除容器、镜像或卷。
- 下一步：在 `codex/v1.2-vision-detection` 提交并推送，保留独立回退点；后续模块继续只推送此分支，整个系统完成前不合并主分支、不推送新标签。
