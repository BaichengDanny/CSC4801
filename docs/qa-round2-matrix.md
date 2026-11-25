# 第二轮需求—用例对照表

日期：2026-11-25。规范来源为 [REQUIREMENTS.md](../final_project_spec/REQUIREMENTS.md)，结果与复跑命令见 [执行报告](qa-2026-11-25.md)。本表补充 README 的全量映射，不改变课程要求。

下表 R2 指 `tests/unit/test_round2_contracts.py`。Python 命令 `python -m pytest -q` 共 89 项（88 项单元测试，1 项同步并发测试）。生成器循环不是额外的 pytest 项目，浏览器和独立探测也不计入该数字。

本表保留第二轮基线结果。后续转义、匹配和 CI 补测见 [补测报告](qa-supplement-2026-11-25.md)，不要把历史 89 项数字当作最新结果。

## 按需求核对

| 需求 | 本轮预期、方法与证据 | 状态及限制 |
|---|---|---|
| FP-ARCH-1 | Docker 构建、迁移、seed、health、89 项测试；两个浏览器门户和真实 HTTP | 本地通过；最终 main 需再验证 |
| FP-AUTH-1 | 原有注册/重复邮箱/登录/登出用例；浏览器真实注册和会话注销 | 通过 |
| FP-AUTH-2 | 原有带盐 scrypt 用例；R2 `test_role_owner_matrix_with_direct_requests` 检查响应不含哈希 | 通过；仅合成账号 |
| FP-AUTH-3 | R2 `test_role_owner_matrix_with_direct_requests`，实际匿名/两名候选人/两名招聘方请求；401、403、404；JSON ID 边界 | 通过；不把非法请求格式与权限的先后顺序增加为新规范 |
| FP-CAN-1 | R2 `test_failed_writes_leave_all_related_and_unrelated_rows`；原有 owner-only 简历读取/替换；浏览器保存刷新和隐私 | 通过 |
| FP-CAN-2 | R2 `test_both_views_recompute_oracle_and_stable_ties`；独立确定所有职位、分数、大小写标题/稳定 ID 排序；原有浏览器匹配组 | 通过 |
| FP-CAN-3 | R2 `test_failed_writes_leave_all_related_and_unrelated_rows`、`test_json_resource_id_does_not_coerce_or_crash`；一次投递、Pending、重复 409、非法 ID 不写入 | 通过；QA2-01 已修复 |
| FP-EMP-1 | 原有公司更新用例；R2 非法字段全表状态比较、`test_same_name_companies_remain_distinct_in_candidate_api`；同名公司浏览器详情 | 通过；QA2-03 已修复 |
| FP-EMP-2 | R2 非法创建/编辑、最大合法长度、其他记录不变、关联删除 409；原有无依赖成功删除 | 通过 |
| FP-EMP-3 | R2 两端独立分数与姓名/稳定候选人 ID 排序；角色矩阵；状态转换及预订保留 | 通过 |
| FP-MATCH-1 | R2 `test_independent_golden_scores`、`test_seeded_score_oracle_and_metamorphic_relations`、`test_documented_skill_limits_and_types`、两端重新计算；原有浏览器共享 JS 算例 | 通过；400 组固定种子，包含变换和单调性断言 |
| FP-MATCH-2 | 未实现可选 AI | N/A |
| FP-SCHED-1 | R2 `test_time_boundaries_offsets_and_failed_state`、`test_new_employer_cannot_offer_slots_without_a_job`、`test_booked_slot_is_redacted_and_unavailable_to_other_candidate`；浏览器 DST 和非法删除 | 通过 |
| FP-SCHED-2 | R2 `test_booking_state_machine_and_exact_future_boundary`、角色矩阵、同名招聘方时段、同招聘方跨职位可预约 | 通过；QA2-01、QA2-03 已修复 |
| FP-SCHED-3 | 原有 `test_booking_conflict_contract`、同步 SQLite race；真实 HTTP Barrier 双客户端 + SQL 直接核对；R2 `test_storage_contention_is_distinct_and_transaction_recovers` | 通过；正确区分 409 预约冲突与 503 写锁冲突 |
| FP-SEC-1 | R2 角色/所有者矩阵、简历 sentinel 不出现在其他账号、他人预约申请 403；浏览器错误招聘方时段 API 403 | 通过；页面 HTML 是公开壳，敏感数据由 API 保护 |
| FP-SEC-2 | 源码 SQL 参数绑定审查 + 原有恶意登录/职位文本用例 + 真实 HTTP SQL 元字符 | 通过；动态标识符来自内部常量，非用户输入 |
| FP-SEC-3 | HTML 插入位置审查；原有 JSON/隐私单测；浏览器实际 DOM 验证 script/img 不执行并保留文字 | 通过；代表性字段和页面，未穷尽每个渲染位置 |
| FP-SEC-4 | 所有生成/状态/变异用例使用临时 DB 或明确命名的本地容器与合成账号；依赖/环境示例审查 | 通过；未联系外部服务，不把真实数据作为测试数据 |
| FP-PROC-1 | SPEC、README、AGENTS、报告同步；修复前/后证据及变异补丁可查 | 文档已更新；全体成员理解代码需团队落实 |
| FP-DOC-1 | 本轮独立 Docker build/start/migrate/seed/test 与同卷重建 | 本地通过；命令见 INSTALL 和报告 |
| FP-DOC-2 | README 的每个 FP 行保留，新增本轮具名用例及文档索引 | 已核对全部 25 个需求 ID |
| FP-DOC-3 | 新容器执行一次显式 seed，最后恢复本轮专用演示 DB；原有 seed 覆盖及会话失效测试 | 通过；不重置用户已有容器 |
| FP-TEST-1 | 全部 89 项 + 本轮 29 项 Python 用例；17 个非等价变异被检出，1 个等价单列；固定种子 99 个独立探测 | 通过所列范围；变异为人工挑选的有限样本 |
| FP-SUB-1 | 保留原始 base SHA 与本轮文件快照/证据，构建本地镜像 | 尚未提交：公开 main、永久 commit URL、CI 和课程提交由团队办理 |

## 分区、边界及状态不变量

| 输入/状态 | 合法与临界值 | 非法/冲突值与独立预期 |
|---|---|---|
| 技能 | 空列表、全空白、顺序变化、重复、大小写、Unicode；100 个唯一技能、80 字符技能 | 非列表/非文本成员、101 个唯一项、81 字符：400；前两类来自技能列表契约，长度是既有实现上限 |
| 匹配 | 课程 100/50/0/空要求 100；1/3=33、2/3=66；给定职位要求增加命中技能 | 次序/空白/大小写/重复不改变得分；增加命中不得降低分数；简历文字不作为得分输入 |
| ID | 正整数、浏览器使用的数字字符串 | true、1.5、1.0、1e309、空值、数组、对象、越界、SQL 字符串：404 且不写入；不把这些值转换成其他记录 |
| JSON | 显式对象；部分更新的 `{}` 保持可用 | null、截断正文、空正文、数组/标量：400；1 MiB 以上：413；全表状态不变 |
| 文本 | name 100、resume 50000、title 150、body 10000、summary 300、location 120 的既有上限仍可保存 | 空必填值、NUL、越界及“合法字段 + 非法字段”：400，字段、关系及不相关记录均不变 |
| 时间 | NOW+1 秒、30 分钟、多个 offset 指向同一 UTC、合法闰日、浏览器 .000Z | NOW 与过去、1799/1801 秒、倒序、无时区、非零微秒、非法月/闰日、UTC 越界：400 且无 slot |
| 预约序列 | Pending → Interviewing → 预订 → Accepted/Rejected/Pending，原预订保留；同公司不同职位可预约 | 非 Interviewing、其他招聘方、其他候选人申请、过期、重复预订、重复投递、有关联删除：各自 403/404/409，全表不部分改变 |
| 写锁 | 锁释放后仍能成功写入；内层回滚后外层能提交其余合法操作 | 实际 SQLite 写锁耗尽：503；无关数据库错误不伪装成预约冲突 |

## 仍需清楚区分

- 分支覆盖率用于找遗漏。Python 语句/分支统计不包含浏览器 JS；浏览器实测是独立证据。
- 固定种子探测与蜕变测试规模有限，没有负载测试，也没有穷举所有 Unicode/日期/操作序列。
- 变异检查限于 Python 的打分、权限、重复投递、依赖删除、排序、预约和 JSON 边界；未进行数据库约束与前端全量变异。
- 课程没有规定长度上限和所有错误优先级。本轮验证已有约定，没有另造新的评分要求。
