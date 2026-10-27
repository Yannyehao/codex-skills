# Codex Skills

个人维护的可复用本地 Codex Skills。

| Skill | 用途 | 调用 |
|---|---|---|
| [ste-fr](skills/ste-fr/SKILL.md) | 法语、英语、中文逐段对照的自然对话 | `$ste-fr` 或 `/ste-fr` |
| [lexicon-ingest](skills/lexicon-ingest/SKILL.md) | 将明确批准的英法原文按词元与实际出现次数写入词库 | `$lexicon-ingest` 或“把刚才的词入库” |
| [market-review](skills/market-review/SKILL.md) | 美股/A股全量复盘：最近完整收盘日候选、持续观察、状态变化与月度台账 | “美股复盘”“A股复盘”或 `$market-review` |
| [trade-execution](skills/trade-execution/SKILL.md) | 已批准交易单的下单核对、成交/撤单记录、持仓管理与放大提议（对接生命周期服务，不点击券商） | “怎么下单”、成交/撤单截图或 `$trade-execution` |
| [us-market-review](skills/us-market-review/SKILL.md) | 兼容别名，仅显式调用，转交 market-review 美股画像 | `$us-market-review` |

## 安装与使用

```powershell
git clone https://github.com/Yannyehao/codex-skills.git
cd codex-skills
.\scripts\install.ps1
```

安装器使用 `$env:CODEX_HOME\skills`；没有设置时使用 `$env:USERPROFILE\.codex\skills`。也可使用 `-Destination <目录>` 指定目标；加 `-Prune` 会清除安装副本中源码已删除的旧文件（保留 `*.local.json`）。新聊天中可直接调用表格中的 Skill；说“美股复盘”或“A股复盘”会触发 `market-review` 的全量复盘，而不是只看当日短名单。

首次使用词库 Skill，复制安装目录内的 `config.example.json` 为 `config.local.json`，填写自己的 Notion data source URL。配置必须指向有权限访问的数据库；实际写入仍使用已连接的 Notion 工具。该配置不会提交到仓库，重复安装会保留它。

`ste-fr` 持续保持三语模式，直到 `/stop-ste-fr`。明确批准入库时，委托 `lexicon-ingest`；没有批准就不写库。

`market-review` 首次使用时，把安装目录内的 `config.example.json` 复制为 `config.local.json`，按 `profiles.us` / `profiles.a` 填写本机项目与候选数据库目标；没有时美股画像会回退读取旧 `us-market-review/config.local.json`（旧平铺格式仍可用）。复盘默认只读；只有用户明确要求“写回”或“固化/生成交易单”时才写外部状态，且交易单只是 DRAFT，批准、下单、成交永远由人完成。

`trade-execution` 复制自己的 `config.example.json` 为 `config.local.json`，填写生命周期服务（`python -m zradar.trade_lifecycle` 所在项目、账本路径、人工/导入身份、放大政策文件）与可选的 tick/涨跌停比例（未配置的不会被臆造）。交易单只从该服务的 `state`/`audit` 原始输出读取，缺失、非 human 审批、terms_sha256 不符、AMBIGUOUS/REJECT 通道或已过期即停止；Notion 只是投影。`market-review` 的 `config.local.json` 同样可加 `lifecycle_service` 段（仅用于只读查询与明确 固化 时的 `create_draft`）。`us-market-review` 依赖同仓库的 `market-review`，两者一起安装。

## 维护

以后在 `skills/<name>/` 创建或修改规则，再安装、校验、提交和推送。这里是源文件；安装目录是供 Codex 使用的副本。

每个 Skill 至少包含有 `name`、`description` frontmatter 的 `SKILL.md`。需要时添加 `agents/openai.yaml`、参考文件和脚本。

## 验证清单

- 使用系统 skill-creator 的 `scripts/quick_validate.py <skill-folder>` 校验每个 Skill；Windows 中文环境可加 Python `-X utf8`。
- 安装后比对源文件与安装副本，确认本机配置仍保留。
- 新聊天测试发现、触发、持续模式和退出规则。
- 词库写入只测试已获明确批准的原文，必须回读核验。
- 美股复盘先运行 `market-review/scripts/audit_review.py --profile us`，再核对实时数据库与逐张图；不能用旧快照冒充全量状态。脚本选最新完整产物包并列出被跳过的更新日期。
- 脚本测试只用合成数据：在 `scripts/` 目录运行 `python -X utf8 -B -m unittest test_audit_review test_skill_contract`（market-review）与 `test_audit_ticket test_skill_contract`（trade-execution，使用含 `approval`/`profile` 的服务 `state` 形状合成 JSON）。`test_skill_contract` 只读仓库内文件，校验阅读规则/边界写在文档里、示例配置只含占位符、无机器绝对路径、本机配置被忽略。绝不读生产库、产物或券商。
- 交易单审计 `audit_ticket.py pre-submit`/`protective` 直接读取 `python -m zradar.trade_lifecycle state` 与 `audit --ticket-id` 的原始输出（审批哈希取自其中持久化的 `approval`、市场画像取自 `profile`，不需要也不接受手输哈希），只读演算并输出 BLOCKED 或 READY_FOR_HUMAN_CONFIRMATION；`check-args` 校验 `apply --args-json`，`scale-up-proposal` 校验放大结果仅为提议。它们不记录、不联网、不下单，也不内置任何美元/R 阈值。
- 提交前确认没有本机配置、令牌、原文批次或数据库审计。
