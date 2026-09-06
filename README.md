# CourseMind

CourseMind 是一个面向香港城市大学本科数据科学专业学生的下一学期选课规划与课程交流社区。本期候选范围先限定为 DSC 课程，CS 暂不接入 Section 规划。

项目的核心原则：

- 官方课程资料、培养方案和结构化规则决定事实与硬约束；
- 学生画像区分 `DSC`、`DSE`、`DSE1` Major；`DSE1` 按 DSE 分流家族参与 Section eligibility 判断；
- 学生社区评价只提供主观体验与软偏好，不会覆盖官方规则；
- 仅为已正式发布开课与 Section 信息的下一学期生成正式选课方案；
- LLM 负责理解、解释和整合，先修、学分与时间冲突由确定性工具判断。
- 对当前学期注册事实，AIMS 优先于 Catalogue：Section、CRN、时间、容量、候补、WEB 状态和 Major/Programme 限制均以 AIMS 为准；Catalogue 负责课程定义和培养方案。

## 当前实施阶段

当前已完成可演示 MVP：学生画像、完整 DSC 培养方案课程索引、已导入学期 Section、课程评价、先修核验、学分审计、时间冲突检查、请求路由、可选 OpenAI-compatible LLM 回答，以及带来源/版本/核验时间的官方证据入库。`/chat/route` 先输出确定性路由和证据，`/chat/execute`/`/consultation/context` 再生成面向用户的简洁回答；没有合格证据或未发布课表时会阻断正式结论。

这不是把 RAG 交给模型“想用就用”：

- 课程事实：`CourseInfoAgent`，必须取官方课程证据；
- 毕业审计：`AcademicRulesAgent`，必须取对应 catalogue year 的官方规则并调用确定性工具；
- 无冲突排课：`ScheduleWorkloadAgent`，必须取目标学期已发布的官方课表；
- 个性化方案：`PlannerAgent` 在硬约束通过后，才使用用户画像与社区体验信号排序。

## 目录

```text
backend/app/domain/   领域模型和确定性规则
backend/app/agents/   可解释路由与证据检索边界
backend/app/storage/  事务数据与版本化官方证据
backend/tests/        规则单元测试
docs/                 产品、数据与架构文档
```

## 当前本地运行

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --reload
```

启动后可访问 `http://127.0.0.1:8000/docs` 查看当前 API。开发默认使用本地 SQLite；部署时通过 `COURSEMIND_DATABASE_URL` 切换到 PostgreSQL。

课程详情接口 `GET /courses/{course_code}/details?term_id=2026-A` 会同时返回 Catalogue 课程事实与 AIMS 当学期 Section，并明确标注 AIMS 对注册事实具有优先级。

候选课程接口 `GET /planning/candidates?user_id=...&term_id=...` 会先按学生画像、培养方案范围、先修课和 AIMS Section 限制筛选，再由可解释的 Planner 排序器按先修状态和兴趣匹配产生 `ranked_candidates`。座位余量暂不参与排序，因为当前 AIMS 数据是快照而非实时接口。

课程比较接口 `GET /courses/compare?codes=DSC3006,DSC4008` 同时返回官方课程事实和社区评价统计，并明确将社区内容限制为主观软信号。

## 导入首批官方资料

首批资料位于 `data/seed_catalogue_2026_27.json`，内容来自 CityU 官方 Catalogue 的已核验条目；评分比例被标记为 indicative，不能替代详细课程信息。启动后端前可运行：

```bash
backend/.venv/bin/python scripts/load_seed_catalogue.py
```

脚本只载入项目内已审核的 JSON，不会自动抓取网页，也不会覆盖其他来源的记录。

## 重要数据边界

`SDSC` 是当前 `DSC` 的历史命名。CourseMind 会将学生专业和课程记录中的 `SDSC`/`SDSCxxxx` 统一标准化为 `DSC`/`DSCxxxx`，保留来源上下文但避免把同一门课重复计数。课程社区包含培养方案课程卡片、筛选、课程详情、比较和评价入口；“我的”页面显示已修课程和毕业进度。

官方数据的收集、时效和入库规则见 [数据来源与时效契约](docs/data-source-contract.md)。

评测与监控基线见 [评测与监控](docs/evaluation-and-monitoring.md)，当前路由回归运行规模为 50 条；可运行 `backend/.venv/bin/python scripts/run_eval.py` 执行。
官方课程证据回归可运行 `backend/.venv/bin/python scripts/run_evidence_eval.py`，当前为 30/30；规则回归可运行 `backend/.venv/bin/python scripts/run_rule_eval.py`。

部署与运行说明见 [部署文档](docs/deployment.md)。

简历项目描述见 [resume-description.md](docs/resume-description.md)，面试讲解材料见 [interview-material.md](docs/interview-material.md)。

## AIMS 首批快照

Semester A 2026/27 的课程索引已覆盖 AIMS 列出的 DSC 课程（含 0 学分实习）；其中已有 15 门课程的 28 个 Section/组件被逐行结构化，包含 CRN、学分、座位、时间、教师、教室、WEB 状态和 Major/Programme 限制。审核数据见 `data/aims_offerings_2026_A.json`，导入命令为 `backend/.venv/bin/python scripts/load_aims_offerings.py`。这是 2026-08-30 的点时快照，不是实时注册接口；PDF 内容暂不入库。
