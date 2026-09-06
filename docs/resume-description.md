# CourseMind 简历项目描述

## 中文版

**CourseMind｜CityU 数据科学选课规划与课程社区 Agent 系统**

- 面向香港城市大学本科数据科学专业，设计“我的画像—课程事实—学期课表—规则审计—规划推荐—社区评价”完整产品链路。
- 使用 FastAPI、SQLAlchemy 和 SQLite 构建后端，将 DSC 培养方案的 62 门课程目录索引，以及 15 门课程的 28 条 Semester A 2026/27 AIMS Section 结构化入库；未开课课程不虚构 CRN、教师或时间。
- 设计证据优先的 Agent 路由：CourseInfoAgent、AcademicRulesAgent、ScheduleWorkloadAgent、PlannerAgent；课程事实、培养规则和时间冲突均不能绕过官方证据。
- 实现 DSC/DSE/DSE1 分流权限、先修课、Section eligibility、时间冲突、学分审计和 DSC4116 两学期课程规则的确定性校验。
- 构建关键词 + 轻量向量相似度的混合检索原型，并按 Catalogue Year、term_id、来源状态过滤证据；将历史 SDSC 代码归一为当前 DSC 代码。
- 建立课程评价和比较接口，将官方硬事实与学生主观体验分层；AIMS 快照明确不作为实时座位或注册状态使用。
- 建立离线评测和运行监控：50 条路由、30 条证据、30 条规则、20 条端到端规划评测，以及请求延迟、证据命中率和 AIMS 快照核验时间指标。

## English Version

**CourseMind | Agentic Course Planning and Course Community Platform for CityU Data Science**

- Designed an end-to-end course planning workflow covering student profile, official course facts, term schedules, rule auditing, planning, and community reviews.
- Built a FastAPI/SQLAlchemy backend and structured 22 DSC course records and 28 AIMS section/component records across 15 courses for Semester A 2026/27.
- Implemented evidence-first routing across CourseInfoAgent, AcademicRulesAgent, ScheduleWorkloadAgent, and PlannerAgent.
- Added deterministic prerequisite, DSC/DSE/DSE1 eligibility, section restriction, timetable conflict, credit audit, and two-term capstone checks.
- Prototyped hybrid keyword/vector retrieval with Catalogue Year, term, and source-status filtering, including SDSC-to-DSC legacy code normalization.
- Separated official facts from subjective community signals and explicitly treated AIMS data as a historical planning snapshot rather than live registration data.
- Added offline evaluation and observability: 50 routing, 30 evidence, 30 rule, and 20 end-to-end planning cases, plus latency and evidence-hit metrics.

## 面试时的诚实边界

当前版本是可本地演示的 Agent 产品 MVP；LLM provider 已提供 OpenAI-compatible 适配层，前端已完成咨询、社区、课程详情/比较和画像进度页面。仍不要表述为“已接入 AIMS 实时系统”或“模型自动决定学术规则”。
