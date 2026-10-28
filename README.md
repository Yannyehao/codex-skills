# Codex Skills

个人维护的可复用本地 Codex Skills。

| Skill | 用途 | 调用 |
|---|---|---|
| [ste-fr](skills/ste-fr/SKILL.md) | 法语、英语、中文逐段对照的自然对话 | `$ste-fr` 或 `/ste-fr` |
| [lexicon-ingest](skills/lexicon-ingest/SKILL.md) | 将明确批准的英法原文按词元与实际出现次数写入词库 | `$lexicon-ingest` 或“把刚才的词入库” |
| [market-review](skills/market-review/SKILL.md) | 美股 / A股全量复盘：当日候选、活跃机会、状态变化与月度台账 | `$market-review`、“美股复盘”或“A股复盘” |
| [trade-execution](skills/trade-execution/SKILL.md) | 从已落库、已人工批准的交易单开始，校验并记录委托、成交、撤单、保护单与持仓事实 | `$trade-execution`、“怎么下单”、“成交了”或持仓管理 |

## 安装与使用

```powershell
git clone https://github.com/Yannyehao/codex-skills.git
cd codex-skills
.\scripts\install.ps1
```

安装器使用 `$env:CODEX_HOME\skills`；没有设置时使用 `$env:USERPROFILE\.codex\skills`。也可使用 `-Destination <目录>` 指定目标。新聊天中可直接调用表格中的 Skill；说“美股复盘”会触发全量复盘，而不是只看当日短名单。

首次使用词库 Skill，复制安装目录内的 `config.example.json` 为 `config.local.json`，填写自己的 Notion data source URL。配置必须指向有权限访问的数据库；实际写入仍使用已连接的 Notion 工具。该配置不会提交到仓库，重复安装会保留它。

`ste-fr` 持续保持三语模式，直到 `/stop-ste-fr`。明确批准入库时，委托 `lexicon-ingest`；没有批准就不写库。

`market-review` 与 `trade-execution` 首次使用时，分别把安装目录内的 `config.example.json` 复制为 `config.local.json`，填写本机 zAI 项目、候选数据库和交易生命周期服务目标。该配置不会提交，重复安装会保留。复盘默认只读；执行 Skill 只能读取已落库并经人工批准的交易单，不代替用户操作券商。

`us-market-review` 只是兼容旧 `$us-market-review` 命令的显式别名，不保存复盘逻辑，也不会被“美股复盘”自动触发；普通请求统一进入 `market-review`。

## 维护

以后在 `skills/<name>/` 创建或修改规则，再安装、校验、提交和推送。这里是源文件；安装目录是供 Codex 使用的副本。

每个 Skill 至少包含有 `name`、`description` frontmatter 的 `SKILL.md`。需要时添加 `agents/openai.yaml`、参考文件和脚本。

## 验证清单

- 使用系统 skill-creator 的 `scripts/quick_validate.py <skill-folder>` 校验每个 Skill；Windows 中文环境可加 Python `-X utf8`。
- 安装后比对源文件与安装副本，确认本机配置仍保留。
- 新聊天测试发现、触发、持续模式和退出规则。
- 词库写入只测试已获明确批准的原文，必须回读核验。
- 市场复盘先运行随附审计脚本，再核对实时生命周期数据与逐张图；不能用旧快照冒充全量状态。
- 交易执行先用服务输出和随附审计器过门；没有持久化交易单、批准记录或券商证据就必须停止。
- 提交前确认没有本机配置、令牌、原文批次或数据库审计。
