# Codex Skills

个人维护的可复用本地 Codex Skills。

| Skill | 用途 | 调用 |
|---|---|---|
| [ste-fr](skills/ste-fr/SKILL.md) | 法语、英语、中文逐段对照的自然对话 | `$ste-fr` 或 `/ste-fr` |
| [lexicon-ingest](skills/lexicon-ingest/SKILL.md) | 将明确批准的英法原文按词元与实际出现次数写入词库 | `$lexicon-ingest` 或“把刚才的词入库” |
| [us-market-review](skills/us-market-review/SKILL.md) | 全量核对当日美股、持续观察、状态变化与月度台账 | `$us-market-review` 或“美股复盘” |

## 安装与使用

```powershell
git clone https://github.com/Yannyehao/codex-skills.git
cd codex-skills
.\scripts\install.ps1
```

安装器使用 `$env:CODEX_HOME\skills`；没有设置时使用 `$env:USERPROFILE\.codex\skills`。也可使用 `-Destination <目录>` 指定目标。新聊天中可直接调用表格中的 Skill；说“美股复盘”会触发全量复盘，而不是只看当日短名单。

首次使用词库 Skill，复制安装目录内的 `config.example.json` 为 `config.local.json`，填写自己的 Notion data source URL。配置必须指向有权限访问的数据库；实际写入仍使用已连接的 Notion 工具。该配置不会提交到仓库，重复安装会保留它。

`ste-fr` 持续保持三语模式，直到 `/stop-ste-fr`。明确批准入库时，委托 `lexicon-ingest`；没有批准就不写库。

`us-market-review` 首次使用时，把安装目录内的 `config.example.json` 复制为 `config.local.json`，填写本机 zAI 项目和候选数据库目标。该配置不会提交，重复安装会保留。复盘默认只读；只有用户明确要求写回时才更新外部状态。

## 维护

以后在 `skills/<name>/` 创建或修改规则，再安装、校验、提交和推送。这里是源文件；安装目录是供 Codex 使用的副本。

每个 Skill 至少包含有 `name`、`description` frontmatter 的 `SKILL.md`。需要时添加 `agents/openai.yaml`、参考文件和脚本。

## 验证清单

- 使用系统 skill-creator 的 `scripts/quick_validate.py <skill-folder>` 校验每个 Skill；Windows 中文环境可加 Python `-X utf8`。
- 安装后比对源文件与安装副本，确认本机配置仍保留。
- 新聊天测试发现、触发、持续模式和退出规则。
- 词库写入只测试已获明确批准的原文，必须回读核验。
- 美股复盘先运行随附审计脚本，再核对实时数据库与逐张图；不能用旧快照冒充全量状态。
- 提交前确认没有本机配置、令牌、原文批次或数据库审计。
