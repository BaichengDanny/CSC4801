# 2026-11-25 XSS、匹配与 CI 补测报告

本轮执行用户更新后的 QA_NEXT_ROUND_PLAN；保留既有本地修改。按用户指示，老师简历权限澄清及其相关文档、测试调整全部暂缓；本记录只补转义、匹配、CI 和入口边界。

## 修复前先记录的规范解释

FP-MATCH-1 要求去除首尾空白、lowercase、去重、整数下取整，未指定语言内建 trim 的 Unicode 字符集合。[Python 空白定义](https://docs.python.org/3.12/library/stdtypes.html#str.isspace) 与 [ECMAScript 的空白/BOM 规则](https://tc39.es/ecma262/multipage/ecmascript-language-lexical-grammar.html#sec-white-space) 并不相同。本项目采用明确的共同集合，保留已有 Python 识别的空白，并兼容 JS 已识别的 U+FEFF；这是项目对规范边界的解释，不宣称课程额外规定 BOM 必须删除。

共同首尾集合：U+0009–000D、U+001C–0020、U+0085、U+00A0、U+1680、U+2000–200A、U+2028/2029、U+202F、U+205F、U+3000、U+FEFF。内部空白、U+200B、U+180E 保持不变；不做 NFC/NFKC 或 casefold。lowercase 仍使用各运行时标准 Unicode lowercase。排序在 lowercase 后按 Unicode code point 比较，稳定数据库 ID 用十进制字符串精确比较，不经 JS Number 丢失精度。

独立预期：FEFFPython 对 Python 应为 100；NBSP/全角空格包裹应命中，零宽 U+200B 前缀不命中；1/3=33，2/3=66；同分同名时 ID 2 在 10 前，2^53 两侧 ID 仍精确排序，BMP 私有区 U+E000 在 U+10000 前。这些预期先于实现修复记录。

本轮保留修复前快照 output/qa-supplement/.baseline 与 SHA-256 manifest。不同 Unicode 版本中新增字符的 lowercase 行为将作为对照测试剩余风险单独说明，不能用有限词表冒充全 Unicode 等价证明。


> 后续状态更新：本记录的 QA3-04 待修结论为历史基线；现已按后端权威方案修复并通过验证，见 [修复报告](qa3-04-fix-2026-11-25.md)。原始失败证据保留。

## 本轮结论

优先补测和可直接处理的修复已执行，保留了此前全部工作。修复共同空白、Unicode 文本排序和精确 ID 排序三类边界，提取了页面共用的真实转义函数，替换了 API 测试弱断言。**仍有一个已复现、待团队修复的 Unicode 版本问题 QA3-04，两个失败反例没有被计为通过。**

工作区 `D:\CSC4801-qa`，分支 `qa/spec-verification-20261124`；基于 `a48647fbefb0065deec27cb92fa674db68f38552` 及开始本轮时已有的本地修改。精确开始文件由 `output/qa-supplement/baseline-manifest.json` 和隐藏 `.baseline/` 保存。没有提交或推送。原有第二轮报告和快照保留为历史证据。

## 执行结果

以下证据从 `output/qa-supplement/` 起算；不同层级的案例数不相加。

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 统一入口，含完整 Python/并发 | **100 passed**：99 个后端 unit + 1 个同步 race | `final-native.log`、`final-native.xml` |
| Docker 完整 Python | **100 passed**，从本轮镜像运行 | `docker-tests.log` |
| 实际共享 JS 单元测试 | **12 passed**：9 个 HTML 转义场景，3 个匹配/排序测试 | `npm-test.log`、`frontend-unit.log` |
| 固定语料 Python/JS 分数对照 | **1,241 组通过**：11 个 golden、30 个空白边界、600 个生成样例及其 600 个变换 | `parity-after.json` |
| 两端排序对照 | **8 组通过**：5 个 jobs、3 个 applicants | `parity-after.json` |
| 修复前的同数据对照 | 702 条失败记录，含同一根因的重复表现/蜕变失败；不是 702 个独立缺陷 | `parity-before.json`、`parity-before.log` |
| 原有完整浏览器流程 | **7/7 组通过**：注册、发布到预订、匹配、真实 DOM/XSS、DST、移动端、登出 | `browser-rerun/results.json` |
| FEFF/API/页面与实际 helper 绑定 | **3/3 组通过**；profile 保存成 python，两个页面分数均为 33 | `normalization-rerun/results.json` |
| 同名招聘方身份回归 | **2/2 组通过** | `identity-rerun/results.json` |
| 直接核对运行容器里的 FEFF 分数 | candidate_backend=33，employer_backend=33；修复前同数据为 0，而页面为 33 | `feff-backend-before.json`、`feff-backend-after.json` |
| 真实 HTTP/并发 | 5 组通过；一方 200，一方 409 / Slot already booked，数据库一条预订 | `http-final.log`、`http-race-database-count.log` |
| 数据卷重建 | 通过：重建前后记录计数和 synthetic sentinel 完全相同，随后仅恢复本轮演示 DB | `persistence-final.log` |
| 既有有限语义变异 | **17 killed、0 survived、1 equivalent、0 errors**；正常产品源文件未被修改 | `mutation/results.json` |
| 已知 Unicode 版本回归 | **仍失败：2 个差异**；Python 0 / Node 100 / 实际 Edge 100；原始快照也失败 | `unicode-version-before.json`、`unicode-version-open.json`、`unicode-version-browser.json` |
| 交付一致性 | 25 个需求映射、54 个完整具名 Python 测试引用、文档链接通过；37 个运行文件与 Docker 一致；课程原文、原有认证/简历权限段和相关断言未改动 | `delivery-check.json`、`docker-source-check.json`、`final-health.log` |
| CI | 本地对应命令、npm ci 和 YAML 结构已校验；远端 Actions **未运行** | `ci-config-check.json`；源码 `.github/workflows/tests.yml` |

第一批并行浏览器运行碰到工具会话/协议断言，部分运行没有完整结果，相关日志保留但不作为通过证据。重新创建独立浏览器会话、串行运行后取得表中的 12 组有效结果；没有吞掉错误或把初次工具故障计为产品缺陷。

## XSS 渲染单测：补上真实调用边界

新增产品模块 `shared/html.js::escape`，由 live candidate/recruiter 页面导入，门户里的 `esc` 绑定到这个函数；candidate dashboard 原先的重复 esc 也改为调用同一产品函数。既有 UI 转义行为保持一致，没有往测试里复制一个 escape 实现。

`tests/frontend/html.test.cjs` 直接 require 产品模块，具名覆盖：

- `product escape: script-tag`：`<script>alert(1)</script>`。
- `event-attribute` 与 `attribute-breakout`：img/onerror、单双引号、autofocus/onfocus。
- `all-delimiters`、`entity-is-text`：`&<>"'` 与已经像实体的文本。
- Unicode/换行、空值、数字，以及放回真实“文本节点 + 双引号属性”模板后的精确边界。

这些是对真实转义函数的单元测试，不仅检查 JSON 返回。浏览器既有 DOM 检查仍执行，并断言两个门户的 `esc === MWHTML.escape`，验证被单测的函数确实被页面使用。helper 的适用上下文是 HTML 文本和带引号属性，不能拿它替代 URL/CSS 校验。

## 已修复的匹配问题

### QA3-01 首尾空白集合不一致

对应 FP-MATCH-1、FP-CAN-2、FP-EMP-3。最小样例：candidate `["\uFEFFPython"]`、required `["Python"]`。修复前后端函数 0，JS 100。反方向的 NEL/U+001C–1F 则有 Python 100、JS 0 的反例。

本轮按前文先记录的共同空白集合修复两端，保留原有 Python 识别空白并兼容 JS 的 BOM 行为。公式、合法长度与内部文本解释未更换。使用 Python/JS 对照、具名后端 API 保存测试及实际浏览器验证。

真实链路：保存 FEFFPython，职位要求 Python/SQL/Rust。旧容器后端两个服务都为 0、页面 33；新容器保存为 `["python"]`，后端和两端页面均为 33。旧技能在读取打分时也经过 normalization，不需要重置既有 DB。

### QA3-02 Unicode 字符排序顺序不一致

对应 FP-MATCH-1 的同分排序。原生 JS 字符串比较使用的顺序与 Python code-point 顺序在非 BMP 字符上有差异：同分标题 `"\uE000"` 应排在 `"\U00010000"` 前，原 JS 反序；申请人姓名也有同样函数级反例。

共享 JS 比较器现在明确按 code point 比较 lowercase 后文本。既有 ASCII 顺序保留。同数据排序、真实创建职位到 API/页面列表均复现过修复前失败、验证过修复后通过。

### QA3-03 数字字符串与大整数稳定 ID 排序

对应 FP-MATCH-1。原 compareJobs 的 ID fallback 把 `"10"` 排在 `"2"` 前；使用 seq Number 时，`9007199254740993` 与 `9007199254740992` 可能折叠到同一个数，无法稳定破同分。

现按真实 id 的十进制字符串精确比较，不把 SQLite ID 转成 JS Number。Node 单元测试与 Python/JS 排序对照均覆盖。API 仍保留原有 seq 字段兼容页面，但排序不再依赖它。

## 入口、生成测试与弱断言

新增 `tests/unit/test_entry_boundaries.py` 共 11 项 pytest 案例：

- 实际 register/login 的非法 role，以及 email/password/name 的错误类型；拒绝请求后 users 与 auth_sessions 不改变。
- 密码 7/8/256/257 字符、邮箱 254/255 字符边界与大小写规范化后的唯一性。这里的上限是项目已有约定，不新增课程 MUST。
- 登录轮换撤销旧 token；恰好过期时拒绝，重新登录可继续。
- 6 个 Unicode 首尾空白参数，调用实际 profile API，核对持久化结果及两端后端业务得分。
- 种子 `48012027` 的 120 组合法日期/时区：跨月、闰年日期、正负/半小时 offset，精确核对 UTC；非法 1799 秒输入拒绝且无新增 slot。
- 同种子 120 步申请状态/预约/删时段/读取组合，独立模型检查成功和 400/403/404/409，错误操作不改四张有关联的表，状态改变保留预订。反例包含 seed、步骤及操作 trace，可重复。

`test_api.py` 中的 `assert ... if False else ...` 已改为显式预期：空要求职位 100 分、命中两个要求中一个的职位 50 分，API 返回 ID 顺序及实际服务分数都检查。没有调整该文件原有的简历权限断言。

## 覆盖率与 CI 范围

| Python 指标，范围 recruiting/ | 第二轮基线 | 本轮 |
|---|---|---|
| 语句 | 825 / 868，95.05% | **829 / 869，95.40%** |
| 分支出口 | 181 / 208，87.02% | **184 / 208，88.46%** |
| coverage 综合值 | 93.49% | **94.06%** |
| 未覆盖分支出口 | 27 | **24** |

原始数据：`coverage-final.json`、`coverage-final.txt`。未为提高数字而排除入口/异常分支；剩余主要是旧表单 CSRF、进程入口/路由跳转、防御性角色/缺失 profile、seed/展示回退及错误恢复路径。匹配和预约服务的 Python 语句/分支仍为 100%，但 QA3-04 说明这个数字不能证明所有 Unicode 输入都正确。

Node 的独立覆盖率（`frontend-coverage.log`）只统计 `shared/html.js` 与 `shared/match.js`：整体行 98.70%、分支 81.82%、函数 100%；HTML helper 行 100%、分支 75%，matcher 行 98.44%、分支 84%。它不包含全部页面脚本，也没有与浏览器/ Python 覆盖率合并；浏览器挂载分支和非数字 demo ID 等仍有未覆盖路径。

既有 CI 扩为 18 个步骤，复用 Docker/pytest，加入 Node 24、锁定 Playwright、实际前端单测、bounded parity、原有完整浏览器流程、API/页面匹配、同名雇主和 HTTP 并发，保留失败工件和 cleanup。Linux 用 Playwright 管理的 Chromium，Windows 本次用独立 Edge。

**QA3-04 的探测作为末端 CI 门禁，不设 continue-on-error。** 在当前 Node 24/Python 3.12 组合上它预期失败；远端尚未触发，不能称整条 Actions 已绿。放在末端可以先收集其余流程证据，再如实因已知问题失败。扩展变异与额外 probe 保持独立命令。CI browser 配置参考 [Playwright 官方 CI 文档](https://playwright.dev/docs/ci-intro)。

## 复跑与剩余事项

```powershell
D:\CSC4801\.venv\Scripts\python.exe tests/run_units.py --include-concurrency
npm.cmd ci
npm.cmd test
D:\CSC4801\.venv\Scripts\python.exe tests/acceptance/matching_parity.py
# 已知待修回归；当前明确以 1 退出：
D:\CSC4801\.venv\Scripts\python.exe tests/acceptance/unicode_version_probe.py --browser
```

本轮镜像 `csc4801-qa-supplement:20261125`，容器 `csc4801-qa-supplement-20261125`，数据卷 `csc4801-qa-supplement-data-20261125`。预览 http://127.0.0.1:8085 ，演示账号仍见 README。本轮 reset 仅作用于该专用 DB。旧容器没有被 reset；8084 的修复前复现只新增独立合成账号/职位。

```powershell
$env:QA_BASE_URL = "http://127.0.0.1:8085"
$env:QA_OUTPUT = "output/qa-supplement/browser-repeat"
npm.cmd run test:browser
$env:QA_OUTPUT = "output/qa-supplement/normalization-repeat"
npm.cmd run test:normalization
node tests/browser/round2.cjs
D:\CSC4801\.venv\Scripts\python.exe tests/acceptance/http_smoke.py --base-url http://127.0.0.1:8085
```

剩余工作明确区分：

1. **待修缺陷**：[QA3-04](issues/QA3-04-unicode-version.md)，两个较新字符的 casing 差异已在实际 Python/Node/Edge matcher 复现；需要统一 Unicode 策略或权威打分数据流，并补这些字符完整 API/页面回归。其他本轮已确认的小问题已修复。
2. **按用户指示暂缓**：老师简历权限澄清及相关文档/测试调整。本轮没有借 XSS/匹配补测改动那部分规则。
3. **未执行/边界**：远端 GitHub Actions 与最终 main 永久 commit 验收尚未执行；不是全 Unicode、全浏览器或所有页面 sink 的穷举，未进行负载或部署目标测试。
4. 审阅改动和新 CI 门禁后，由团队修复 QA3-04、合并并在最终 main 构建/seed/test/browser，以及受影响的 HTTP/并发/持久化上复验。没有发布、推送或联系其他同学。
