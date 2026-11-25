# QA3-04：后端统一权威分数与排序（本地已修复）

状态：**本地修复、验证通过**，2026-11-25。已保存于 QA 分支并整合团队最新更新，见[整合验证](../delivery-2026-11-25.md)。远端状态以该分支 PR 的 Checks 为准；最终 main 尚未验收。
关联 FP-MATCH-1、FP-CAN-2、FP-EMP-3。用户选定“后端统一提供权威分数和排序”方案。

## 原始反例与修复结果

| candidate / required | 原 Python / JS | 当前 API / Candidate / Employer |
|---|---|---|
| `["\u1C89"]` / `["\u1C8A"]` | 0 / 100 | **0 / 0 / 0** |
| `["\uA7CB"]` / `["\u0264"]` | 0 / 100 | **0 / 0 / 0** |

沿用 Python 3.12 的现有 lowercase、共同空白集合和课程公式。没有仅修两个字符的特殊表。
API 交付 `score` / `rank`，两端在线页面投影这些事实；修改返回新 snapshot，并有焦点、
可见性及 5 秒轮询刷新。技能预览通过只读 API，保留草稿和现有权限。

## 修改与验证

下列为原 QA3-04 修复阶段结果；整合后 121 项 Python、22 组浏览器结果见整合验证。

实现与全量证据见 [修复报告](../qa3-04-fix-2026-11-25.md)。
主要位置：`recruiting/jobs.py`、`api.py`、`present.py`、
`shared/match.js`、Candidate/Recruiter 的共享数据层和相关页面。

- Windows/Docker **106 项 Python 通过**；**15 项 JS 单测通过**。
- 实际认证 API -> 前端：**1,243 组分数、8 组顺序通过**。
- 浏览器 **20 组通过**，其中 **8 组**专门验证 Unicode、排序、保存/要求修改后刷新、
  只读预览、未保存草稿、Dashboard 和禁止调用旧 JS 计算器。
- HTTP 原子竞争及数据卷重建通过。
- 默认 Unicode CI 门禁已退出 0；无 skip、xfail 或 continue-on-error。远端 Actions 尚未触发。

## 原失败没有被删除或屏蔽

`unicode_version_probe.py` 默认检验真实在线链路；`--browser` 检验部署页面。
原函数级诊断保留在 `legacy_unicode_probe.py`，可用 `--legacy-functions` 运行。
它仍能复现运行时差异并返回 1，但它只描述离线 demo 计算器，不再是在线页面决策来源。
浏览器回归让旧 JS 打分、匹配规范化与排序函数“被调用就抛错”，实际调用次数为 0。

```powershell
D:\CSC4801\.venv\Scripts\python.exe tests/acceptance/unicode_version_probe.py
$env:QA_BASE_URL = 'http://127.0.0.1:8087'
D:\CSC4801\.venv\Scripts\python.exe tests/acceptance/unicode_version_probe.py --browser
# 历史诊断，当前仍明确返回 1：
D:\CSC4801\.venv\Scripts\python.exe tests/acceptance/unicode_version_probe.py --legacy-functions
```

剩余：团队审阅、核对 PR 的真实远端 CI、最终 main 验证。本地修复状态不等同于已合并。
