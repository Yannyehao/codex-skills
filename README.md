# Codex Skills

个人维护的可复用本地 Codex Skills。

| Skill | 用途 | 调用 |
|---|---|---|
| [ste-fr](skills/ste-fr/SKILL.md) | 法语、英语、中文逐段对照的自然对话 | `$ste-fr` 或 `/ste-fr` |
| [lexicon-ingest](skills/lexicon-ingest/SKILL.md) | 将明确批准的英法原文按词元与实际出现次数写入词库 | `$lexicon-ingest` 或“把刚才的词入库” |
| [market-review](skills/market-review/SKILL.md) | 美股 / A股全量复盘：当日候选、活跃机会、状态变化与月度台账 | `$market-review`、“美股复盘”或“A股复盘” |
| [trade-execution](skills/trade-execution/SKILL.md) | 实盘从已批准交易单校验并记录委托事实；历史 replay 按截止日、开盘、收盘分阶段模拟且零生产写入 | `$trade-execution`、“怎么下单”、“成交了”、“模拟当时怎么做”或持仓管理 |

## 安装与使用

```powershell
git clone https://github.com/Yannyehao/codex-skills.git
cd codex-skills
.\scripts\install.ps1
```

安装器使用 `$env:CODEX_HOME\skills`；没有设置时使用 `$env:USERPROFILE\.codex\skills`。也可使用 `-Destination <目录>` 指定目标。新聊天中可直接调用表格中的 Skill；说“美股复盘”会触发全量复盘，而不是只看当日短名单。

首次使用词库 Skill，复制安装目录内的 `config.example.json` 为 `config.local.json`，填写自己的 Notion data source URL。配置必须指向有权限访问的数据库；实际写入仍使用已连接的 Notion 工具。该配置不会提交到仓库，重复安装会保留它。

`ste-fr` 持续保持三语模式，直到 `/stop-ste-fr`。明确批准入库时，委托 `lexicon-ingest`；没有批准就不写库。

`market-review` 与 `trade-execution` 首次使用时，分别把安装目录内的 `config.example.json` 复制为 `config.local.json`，填写本机 zAI 项目、候选数据库和交易生命周期服务目标。该配置不会提交，重复安装会保留。复盘默认只读；生成交易单时只选择一个精确交易类型，`zge-stop-v1` 自动给出唯一的止损依据、触发方式和状态/时间退出。执行 Skill 只能读取已落库、已人工批准且统一策略标记与止损语义匹配的交易单，不代替用户操作券商，也不会把收盘确认止损翻译成盘中 STOP_LIMIT。

历史执行练兵走 trade-execution 的 replay lane，不需要也不读取本机服务配置：先用截止日安全证据生成明确标为 `REPLAY` 的模拟条款，再依次揭示开盘与收盘事件。replay 直接复用 market-review 的 `zge-stop-v1` 选择器，只输出带证据哈希的模拟 journal；它不调用 lifecycle `apply`、不写生产 SQLite，也不形成真实订单、成交或持仓。真实下单仍必须重新走固化、服务内人工批准和 live 审计。

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
- 历史 replay 必须用分阶段证据文件；开盘快照本身不得包含高低收量，结果始终保留 `production_writes: false` / `broker_actions: false`。
- 交易类型必须精确，模糊的 `B1` / `B2` / `BRICK` 或组合判断不能生成交易单；止损模板不再由人自由拼装。搬砖的状态/时间退出不能伪装成价格止损，普通交易与历史导入交易分别通过对应的事后复盘门禁。
- 提交前确认没有本机配置、令牌、原文批次或数据库审计。
