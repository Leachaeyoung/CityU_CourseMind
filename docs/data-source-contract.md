# CourseMind 数据来源与时效契约

CourseMind 不把“网上搜到的内容”直接当作可用于选课决策的事实。每份数据都必须有来源、适用版本与最后核验时间；缺少其中任一项，就只能作为说明材料，不能参与硬约束计算。

## 1. 事实的四个层次

| 层次 | 数据 | 可做什么 | 不可做什么 |
| --- | --- | --- | --- |
| 官方稳定事实 | 课程目录中的课程名、学分、先修课、课程描述 | 课程说明、先修课校验、知识检索引用 | 推断本学期一定开设 |
| 官方版本化规则 | DSC programme scheme、毕业要求、catalogue year | 毕业审计、培养方案说明 | 跨 catalogue year 套用规则 |
| 官方临时事实 | AIMS / Master Class Schedule 的开课、CRN、section、上课时间 | 当前已发布学期的冲突检测和组合规划 | 对未来未发布学期生成具体课表 |
| 社区体验 | 学生的评分、工作量、难度、评核压力、文字评价 | 偏好匹配与风险提示 | 替代先修课、时间或毕业规则 |

## 2. V1 认可的来源

### 当前学期注册事实的优先级

对于同一已发布学期，AIMS Master Class Schedule 是当前注册事实的优先来源，覆盖 Section、CRN、当学期学分、时间、容量、候补、WEB 状态及 `only for Major/Programme` 限制。Catalogue 与 AIMS 出现差异时，规划和可注册性判断以 AIMS 为准，并保留差异记录供人工复核。Catalogue 不得覆盖 AIMS 的实时 Section 数据。

但本项目当前导入的是用户于 2026-08-30 提供的 AIMS 快照，适用范围明确为 Semester A 2026/27。它可以作为该学期课程规划、Section、时间和资格限制的有效依据，但不是实时连接，不能确认当前座位或当前是否仍可注册。用户端不展示容量字段，也不会把快照状态用于推荐排序。

Catalogue 仍是课程定义、课程目标、先修规则、培养方案和长期课程属性的来源；它不能替代 AIMS 的实时开课信息。

- **课程目录**：`https://www.cityu.edu.hk/catalogue/ug/current/course/{COURSE_CODE}.htm`。
- **DSC programme scheme**：CityU Undergraduate Catalogue 中对应学生 catalogue year 的 BSc Data Science major 页面。
- **下一学期课表**：仅接受由学生从 CityU Portal / AIMS 的 Master Class Schedule 导出的文件，或之后取得的、经验证的官方读取接口。
- **课程教学大纲 PDF**：仅接受课程页面直接链接的官方 PDF，且要记录下载时间和源 URL。

CityU 的课程目录和 programme scheme 会随版本更新；学生个人的 catalogue year 是审计的锚点。学校也说明 Master Class Schedule 每年发布、开学前可能变动，并通过 Portal/AIMS 提供访问。因此项目不能把课程目录中“可能开设”的课程当成某个学期的确定排课。

## 3. 入库必填元数据

每一条官方课程/规则/开课记录都应记录：

```text
source_url          原始官方链接或导出来源标识
catalogue_year      规则适用版本（课程/培养方案）
term_id             例如 2026-A；仅开课数据需要
source_published_at 来源标称发布日期（若有）
verified_at         CourseMind 最后核验时间
status              published | stale | unavailable
```

跨学期课程还必须区分 `course.credits`（整门课程总学分）、`course.duration_terms`（持续学期数）和 `offering.credit_units`（该学期开课承担的学分）。例如 year-long 课程可以在两个学期各显示 3 credits，但毕业要求按整门课累计 6 credit units 计算。

当 `status != published` 时，规划器必须拒绝输出“已验证无冲突”的结论，并告诉用户缺少哪份官方数据。

## 4. 首次数据准备流程

1. 选定一个 catalogue year（第一版以实际目标学生 cohort 为准）。
2. 从官方课程目录逐门录入 DSC 与纳入范围的 CS 课程，保留课程页链接和先修课原文。
3. 从同一 catalogue year 的 programme scheme 录入必修、选修组和学分要求；录入前由人工复核一次。
4. 临近开学时，由管理员导入官方 Master Class Schedule 的已发布 section / CRN / 时间；每次导入产生新版本，不覆盖历史快照。
5. 用户评价独立入库，并始终在 UI 和 Agent 回答中标为“学生经验”。

## 5. 首版明确不做的事

- 不抓取登录后的 AIMS 页面，不保存学生 AIMS 凭据。
- 不通过搜索结果或历史开课规律预测未来某门课一定开设。
- 历史 `SDSCxxxx` 课程代码按 CityU 当前命名约定归一为 `DSCxxxx`；原始来源文本仍可保留，但内部检索、先修校验和学分审计使用归一后的当前代码。
- 不把评论均分或 LLM 的推断当成正式学术建议。
