---
name: trade-case-logger
description: 用户真实表达要把某票某日留成案例时，一次操作存好证据、诊断注释和「我的案例」成员关系。自然说法（「这个留着」「可以入案例」）和对具体提议的确认都算；普通裁决（「应该入选」「结束观察」「写回」）不算授权，不触发。不改任何阈值/战法。
---

# trade-case-logger · 案例标注

**一份事实账本，多个视图。** 案例不是登记簿：它是对 zAI 统一账本里某条 observation / episode 的**注释**，
从 `v_cases` 派生出来看。账本入口是 `zradar.opportunity_ledger`（US + A 股）。

## 开始前

读 `../market-review/config.local.json` 的 `lifecycle_service`（`python`、`project_root`、`database`），以 `project_root` 为工作目录运行；
下文 `<python>`、`<db>` 都指它。缺文件或仍是占位符就说明不可用，不猜库，也不写。若未安装 market-review，同样停止。

先遵守 `project_root` 自身的会话和写入规则。**生产账本是单写者资源**：项目规则未分配写入权时，只在临时库演练。
不碰 Notion / 通达信 UI；不跑生产管线。

## 硬规矩（API 会替你拒绝，但别靠它）

1. **不看未来数据。** 案例的事实只能用 `target_date` 当天及以前的信息：
   证据里的 K 线 `last_bar_date <= target_date`。用户的原始截图常常带着目标日**之后**的 K 线——
   它只能当**出处（`user_evidence`，`as_of_safe=false`）**，**不得**冒充截止日证据。
2. **必须两类证据各至少一条**，且都落盘、带 sha256（API 现算现比，不符即拒）：
   - `user_evidence`：用户给的原图/原话出处；
   - `cutoff_safe`：按 `target_date` 截止重画/重导出的图或数据，声明 `last_bar_date`，`as_of_safe=true`。
     同一个文件不能同时当两类。
3. **用户原图是案例主图，截止图是审计证据，两者不互相顶替。** 有用户 / 通达信原图时，它（`user_evidence` 的图片行）就是案例库读者看到的主图；
   `as_of_safe=false` 只表示它不能当截止日证据，不影响它当主图。`cutoff_safe` 图只进折叠的审计证据，不算案例图。
   原图从对话附件、上传目录、案例目录和 transcript 自己恢复，不让用户填表。真恢复不出来时：`user_evidence` 放用户原话文本（`kind: user_quote`），
   在 `--note` 里写明「原图未保存」并在汇报里说出来；**不得**把重画图、截止图登记成 `user_evidence` 去凑图。案例库会如实显示「原图尚未保存」。
4. **`production_change` 恒为 `none`。** 标注永不自动改阈值、不改战法、不改产线。
   「能力缺口」只是**假设**（`capability_gap`），改判据由用户另行决定。
5. 必填：`user_verdict`（用户的裁决，原话为准）、`case_type`、`capability_gap`（没有就明写 `none`）、
   `knowledge_class`（这条知识的证据档次，如 原话 / 推断）。
6. 锚点：优先链接已有 observation / episode（按 market+symbol+target_date 自动找当日 current run 的信号，
   其次当日未终结的 episode）。扫描**没报**的案例，先 `add-manual-observation`（挂在专用 run 下，
   不进月度候选 / 动作队列 / 生命周期，只给案例一个事实锚）。
7. 市场与代码：`--market US|A`；A 股代码 6 位数字（丢了前导零会补齐），美股 ticker 原样大写、不补零。

## 什么算授权

由你理解自然语言，代码不解析人话。用户真实表达「要把这个留成案例」才算，授权范围就是说到的那只票、那一日；
自然说法和对具体提议（票、日期、留存内容都说清）的确认都算。
普通裁决、复盘评语、`写回`、「算是个例子」这类随口话只留在复盘审计里：不写案例，也不追问。只有两种交易含义确实不同时才问一句具体的。
交易判断来自用户；日期、图、之前的话、证据和建议分类都由你恢复和准备，不让用户填表。进「我的案例」不等于正例 / 完美 / 可交易；分类要显式。

## 流程

1. 从对话、账本和图恢复市场、代码、`target_date`（YYYYMMDD）和用户裁决原话。恢复不出来、或会改变交易含义时才问。
2. 备好两类证据文件，写成 `evidence.json`（路径可相对该 json 所在目录）：
   ```json
   [
     {"role": "user_evidence", "kind": "user_screenshot", "path": "user.png", "sha256": "<64hex>", "as_of_safe": false},
     {"role": "cutoff_safe", "kind": "cutoff_chart", "path": "cutoff.png", "sha256": "<64hex>",
      "last_bar_date": "<YYYYMMDD>", "as_of_safe": true}
   ]
   ```
3. （需要时）`<python> -X utf8 -m zradar.opportunity_ledger add-manual-observation --db <db> --market <US|A> --symbol <SYMBOL> --date <YYYYMMDD> --case-type <类型> --note "<出处>"`
4. 写标注：
   ```
   <python> -X utf8 -m zradar.opportunity_ledger save-case ^
     --db <db> --market <US|A> --symbol <SYMBOL> --target-date <YYYYMMDD> ^
     --user-verdict "<用户原话>" --case-type <类型> ^
     --capability-gap "<假设，或 none>" --knowledge-class "<档次>" --evidence-json evidence.json ^
     --authorization-json auth.json --recorded-by "agent:<name>" --effective-date <YYYYMMDD> [--classification-json c.json]
   ```
   `auth.json`＝`{source_kind: chat|transcript, source_ref, source_sha256, quote, object: {market, symbol, target_date}, action: "SAVE_CASE"}`，
   quote 逐字抄用户的话，`source_sha256` 为 64 位小写十六进制；这些文件放在仓库之外。一次调用写完证据、注释和成员关系，不需要第二次确认。
   退出码：0 成功（同内容重跑返回同一 `annotation_id`，不新增）；3 = 被拒（原因在 JSON `error`，
   常见：缺证据 / 哈希不符 / 未来泄露 / 截图冒充 / production_change 非 none）；1 = 其他错误。
5. 看案例视图：`<python> -X utf8 -m zradar.opportunity_ledger list-cases --db <db> [--market <US|A>] [--symbol <SYMBOL>]`。
6. 汇报：annotation_id、链接到哪条 observation/episode、两类证据各是什么、原图有没有存到（没有就明说缺原图）、被拒时的原因。
   **不要**顺手建议改阈值；缺口假设留在 `capability_gap` 里等用户裁决。

## 不做

- 不把案例写成独立台账 / Notion 库 / CSV；唯一事实在账本。
- 不用目标日之后的数据补全案例的任何一格。
- 不在案例里写「应该把阈值改成 X」。
- 不把证据原件、对话记录、审计记录或本机配置提交进本公开仓库。
