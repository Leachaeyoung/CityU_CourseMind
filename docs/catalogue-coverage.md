# DSC 官方 Catalogue 覆盖审计

截至 2026-09-01，CourseMind 已导入 BSc Data Science Normative 4-year 培养方案列出的完整课程索引（62 门，含 DSC、CS、MA、GE、IS、LT、COM 等支撑课程）。每条记录保留课程代码、官方名称、学分和官方 Catalogue 课程页链接；即使某门课本学期没有 AIMS Section，仍可查询其培养方案归属和目录基本事实。

课程索引的权威来源是 CityU [BSc Data Science 2026/27 major page](https://www.cityu.edu.hk/catalogue/ug/current/Major/BSC1_DSC-1.htm)，结构化文件为 `data/dsc_curriculum_index_2026_27.json`。课程详细先修、课程目标和评核内容仅在对应官方课程页正文已核验时写入，不会用空壳/反爬页面补全。

本轮新增核验：DSC2002、DSC2004、DSC2005、DSC2102。四门课程的 Catalogue 先修课、课程主题、开课学期和评核比例已写入 `data/course_sources_2026_27.json`，并同步到课程结构化先修规则。

随后新增核验：DSC3003、DSC3004、DSC3005、DSC3010、DSC3011、DSC3013。对 Catalogue 标注“当前学年不开课”的课程，仅保留课程目录事实，不创建本学期 AIMS Section。

本轮对 DSC2001、DSC3001、DSC4070 进行了复核：CityU 当前 DSC 培养方案可核验三门课的当前代码、名称和学分，并确认 DSC2001 为核心课、DSC3001/DSC4070 为 DSC 课程体系中的课程；历史 `SDSC` 官方课程页可交叉核对 DSC2001 的 4 学分与先修课、DSC3001 的 3 学分与 CS3402 先修课。当前三个 `DSC.../course/*.htm` 直链仍返回 Incapsula 反爬空壳，DSC4070 的当前课程页正文和三门课的当前页完整课程描述/考核比例因此尚未宣称为已核验。只有已导入的 Section 才显示 CRN、时间、地点和教师，缺失字段不作为已确认事实；CS 支撑课程已纳入 Catalogue 检索，但本期仍不导入 CS 的 AIMS Section。

较早的 `SDSC` 页面是当前 `DSC` 课程的历史命名参考；系统将其课程代码归一为当前 `DSC` 代码，但不会用旧页面覆盖当前页面事实。AIMS Semester A 2026/27 快照继续负责该学期 Section、时间和资格规划事实。
