# CourseMind 部署与运行

## 本地启动

```bash
cd "/Users/wangjinyu/Desktop/Agent咨询项目/CourseMind"
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --env-file .env
```

长期保存大模型配置时，复制 `.env.example` 为项目根目录的 `.env`，只在本机填写 `LLM_API_KEY`。`.env` 已加入 `.gitignore`，不会提交到 Git；不要把真实密钥写入前端、JSON、README 或聊天消息。

默认使用 `backend/coursemind.db`。可以通过 `COURSEMIND_DATABASE_URL` 指向 PostgreSQL 等 SQLAlchemy 支持的数据库。

## 首次导入

```bash
backend/.venv/bin/python scripts/load_seed_catalogue.py
backend/.venv/bin/python scripts/load_aims_offerings.py
```

课程目录和培养方案来自官方 Catalogue；AIMS 文件是 Semester A 2026/27 的历史快照，不是实时注册接口。导入时保留来源 URL、适用学期和核验时间，不向用户展示座位容量字段。

## 验证

```bash
backend/.venv/bin/python -m pytest -q
backend/.venv/bin/python scripts/run_eval.py
backend/.venv/bin/python scripts/run_evidence_eval.py
backend/.venv/bin/python scripts/run_rule_eval.py
backend/.venv/bin/python scripts/run_planning_eval.py
```

运行时可访问 `GET /health` 和 `GET /metrics`。生产环境应把 `/metrics` 放在认证或内网之后，并把内存指标替换为持久化监控系统。

## 安全与边界

- 不保存或代理学生 AIMS 凭据。
- 不提供 AIMS 注册、退选或账户设置操作。
- 未核验的 Catalogue/PDF 内容不能作为确定性规则依据。
- 快照只能支持对应学期的规划和冲突分析，不能表述为当前可注册状态。
- 生产环境必须关闭 `--reload`，使用 HTTPS、受控数据库凭据和日志脱敏。
