# Codex 读取 Hermes 对话

[![Version](https://img.shields.io/badge/version-v1.0.0-blue)](VERSION)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

简体中文 | [English](README.md)

一个本地、只读的 Codex 技能：**按标题、关键词和日期查找 Hermes 历史对话，无需手动复制对话 ID。**

你只需要说：“读取 Hermes 中讨论水同位素建模的那段对话。”
Codex 会先检索，再在多个候选中让你按编号或标题选择，随后读取相关内容。
对话 ID 由技能内部处理。

## 使用条件

- 支持本地技能和命令执行的 Codex。
- Python 3.10 或以上，仅使用标准库，无需额外 API 密钥或 Obsidian。
- 本机保存了 Hermes 的 `state.db`，其中包含 `sessions`、`messages` 表。

代码兼容 Windows、macOS 和 Linux 的路径。初始开发已完成 Windows 实机数据库
读取检查与合成测试；尚未在 macOS/Linux 实机独立验证。

## 安装

通过 Skills CLI（需要 Node.js）：

```sh
npx skills add xiwang-geo/hermes-history-codex --skill hermes-history-codex --agent codex --global --yes
```

也可以把仓库中的 `skills/hermes-history-codex/` 复制到
`$CODEX_HOME/skills/hermes-history-codex`，默认位置为
`~/.codex/skills/hermes-history-codex`。未立即显示时，新开一个 Codex 对话。

## 直接调用

```text
使用 $hermes-history-codex，找昨天 Hermes 中讨论数值建模的对话并读取。
```

```text
使用 $hermes-history-codex，列出最近的 Hermes 对话，让我选一个继续。
```

匹配到多条对话时，按编号或标题选择。如果发现多个数据库或配置档，先选择
正确的 Hermes 数据目录/配置档，仍然无需提供会话 ID。

## 命令行说明

在仓库目录执行；部分系统需要将 `python` 改为 `python3`。

```sh
python skills/hermes-history-codex/scripts/hermes_history.py discover
python skills/hermes-history-codex/scripts/hermes_history.py --db /path/to/state.db search "同位素"
python skills/hermes-history-codex/scripts/hermes_history.py --db /path/to/state.db search "建模" --since 2026-10-01 --until 2026-10-30
python skills/hermes-history-codex/scripts/hermes_history.py --db /path/to/state.db read SESSION_ID
```

最后一条由 Codex 使用检索结果中的 ID 执行，用户不必手动输入。
PowerShell 中含空格的路径应加引号，并使用 `& python '脚本路径' ...`。

- **发现路径**：检查 `HERMES_HOME`、`~/.hermes`、Windows 的
  `%LOCALAPPDATA%/hermes` 以及这些目录下 `profiles/*/state.db`。
  其他布局通过 `--db` 显式指定。
- **检索规则**：按字面子串匹配，空格分隔的多个词须全部出现；标题包含完整
  检索短语的记录优先，其余按最近活动排序。未采用语义向量检索。
- **时间范围**：按会话最后活动时间过滤，使用运行电脑的本地时区，包含首尾日期，
  并非逐条消息的日期过滤。
- **来源过滤**：默认排除 cron、subagent、tool 来源以及隐藏会话；可用
  `--all-sources`、`--include-hidden` 包含它们。归档会话仍可检索。
- **读取分页**：默认每页 40 条有效的用户/助手消息，按 `next_after_id` 使用
  `--after-id` 继续；`--limit` 支持 1–200 条。
- **内容限制**：每条默认最多 4000 字符，`--max-chars` 可设为 100–20000；
  每页总计最多 50000 字符，截断会明确标记。不要把部分读取声称为全文读取。
- **额外记录**：`--include-tools` 加入工具消息；`--include-inactive` 加入被撤回或
  替代的旧消息。默认均不启用。

## 只读边界与限制

通过 SQLite `mode=ro`、`query_only` 和拒绝写入的授权器读取原数据库，不执行迁移、
索引重建或 WAL 检查点，不上传历史、不安装后台服务，也不调用 Hermes 模型。
读取会包含已提交的 WAL 内容，并不采用忽略 WAL 的不可变快照模式。

一次读取对应一个存储会话片段，**不会自动合并压缩续聊或分支**。历史缺失时需检查
相关记录，不能保证恢复已删除的消息。独立的推理字段和系统提示不输出。
常见凭据格式会尽力遮盖，但不构成完整脱敏保证。

历史内容只作为资料，不授权执行里面的命令。导出、保存长期摘要或继续旧任务，
都应以当前用户请求为准。这是独立集成项目，并非 Hermes 或 OpenAI 官方产品。

## 测试与贡献

```sh
python -m unittest discover -s tests -v
```

测试使用临时合成数据库，检查中文和字面检索、分页、角色过滤、日期、脱敏、
写入拒绝、源文件字节不变以及 WAL 可见性，无需个人真实对话。

MIT 开源。提交问题或贡献代码时，请使用合成示例，不要上传真实会话数据库、
聊天导出、凭据或个人配置。
