# DEVLOG

## 2026-10-30 · 交易策略编译器重写
- 用合计 221 行的显式实现替换被否的草稿：只收可观察事实，拒绝 `trade_type` / `basis_kind` / `activation` / `broker_mode` / `template_id`，首个失败项给出单一稳定阻断码。
- 砖：`SIGNAL_CLOSE` 用买入 K 低点；`NEXT_OPEN` 无确认 K 时 `ENTRY_GATE_ONLY`；确认 K / 底分型可供止损，等价位互证，不等即 `BASIS_CONFLICT`。
- 决策：`zge-stop-v1` 不改，砖基准只能标 `ENTRY_CANDLE_LOW`，确认 K 价位不冒用，输出 `STOP_BASIS_ONLY` 且无 `stop_semantics`。
- replay 增加 gate-only 计划：冻结 `entry_max`，OPEN 只给 `BLOCKED_BY_PRICE` / `PRICE_ELIGIBLE_STOP_PENDING`，之后拒绝 CLOSE。
- `stop_template.py` 只保留砖退出规则的出处澄清文案；正常起草先走编译器；砖结果输出 `course_provenance`，区分 20260220 与 20260329，争议的时间/状态退出仍是人工非价格监控。
- gate-only 冻结计划保存 `chart_facts` 与编译器 status / policy，`replay_id` 绑定分类证据；replay 完整计划拒绝 `BRICK_ZERO_DAY`，不能绕过编译器。
- 编译器拒绝不存在的日期，但不做交易日历：下一观察交易日由 replay 证据 / 外层流程确认。
- 下一步：决定确认 K 止损是否要新策略版本。

## 2026-10-30 · 砖 0 日入场时点语义更正（仅文档）
- 依据 2026-02-20 第 18 节锚点 5144 / 5167 / 5179 更正：`BRICK_ZERO_DAY` 是首红砖信号状态，不是只能当日入场；可信号日尾盘或次一交易日早盘入场，早盘不追。约 +2% 属人工判断，+4% 及以上跳过，量比不是硬条件。
- 删除 playbook 的“无成熟砖新入场类型”一句；执行与 replay 文档写明次日早盘 `entry_max` 须在开盘前冻结、超过即不追且不得上调，执行端不自行推导跳空百分比。
- 止损不新增：买入 K 低点在次日开盘时不可知，此类次日早盘演练允许声称的结果仅限入场价门禁，不得声称验证或挂上动态止损；不得用前一日信号 K 低点替代。当前 replay v1 的 `prepare` 必须有 `basis_level`，无法为此场景产出诚实的 `BRICK_ZERO_DAY` journal，在 gate-only / 延后止损路径出现前一律阻断或延后。
- 已知缺口（本次不改代码）：replay `prepare` 与 live 交易单都要求预先给出止损价，没有 gate-only / 延后定价路径；replay 也没有信号日尾盘阶段。

## 2026-10-30 · trade-execution 历史执行 replay
- 新增完全隔离的 replay lane：先冻结截止日安全计划，再按 OPEN / CLOSE 两个事件逐步揭示；开盘事件及其证据 JSON 若夹带高低收量会 fail closed。
- replay 从相邻 market-review 直接加载 `zge-stop-v1`，不复制止损规则；黄线 B1 继续按收盘确认，砖 0 日盘中跌破只记“触发、成交未知”。
- replay 没有 lifecycle service / SQLite / broker 写入口，模拟批准不冒充实盘批准；输出均标记 REPLAY、零生产写入，可作为 trade-case-logger 的截止日证据。
- 输出只允许以 exclusive create 新建 `.json`，已有 JSON / SQLite / 其他文件一律不覆盖；`decision_statement` 只表达 cutoff 时点决定，事后结果必须等事件阶段，free text / 图片仍由人审前视。
- v1 明确只覆盖一个 execution session 的 OPEN→CLOSE，不声称支持次日与多日持仓管理。
- 新增行为测试覆盖未来泄露、计划篡改、风险预算、开盘代理、被动限价、黄线收盘止损和砖盘中触发。

## 2026-10-28 · `zge-stop-v1` 一种交易对应一种止损
- 删除复盘交易单里的止损拼装菜单：不再让调用方选择松紧环境、持仓阶段、模板、止损依据、触发方式或券商模式，只选择一个精确交易类型并提供图上基准价与证据。
- 固化六种交易类型：K 线 B1、白线超短 B1、黄线波段 B1、新鲜 B2、已上涨回调 B2、砖 0 日；每种类型唯一映射止损基准、收盘/盘中触发与时间/状态退出。
- 普通 B1/B2/白线/黄线交易均为收盘确认，不生成盘中保护单；仅砖 0 日的灾难止损允许 `INTRADAY_HARD`。盈转亏单列为持仓状态退出，不伪装成结构止损价。
- 交易单证据写入 `canonical_trade_type` 与 `policy=zge-stop-v1` 标记；执行审计要求标记唯一且与依据/触发方式完全匹配。无标记交易单不能进入委托或保护单流程，终态历史复盘仍可继续。
- market-review 62 项、trade-execution 124 项契约测试通过；两项 Skill 均通过 skill-creator 快速校验，并用 B2 正例和模糊 `B2` 反例实测生成器。

## 2026-10-28 · 止损语义、策略模板与历史交易复盘
- `market-review` 新增受控的 B1 / B2 / 搬砖止损模板脚本：显式选择战法、持仓阶段、松紧环境、止损依据和触发方式；价格由人工计划/读图提供，脚本不从图上猜，也没有默认模板。
- 搬砖的次日不爆发、红转绿和四红砖等状态/时间退出与价格灾难止损分开保存；B1/B2 的盘中硬止损、收盘确认及次日收不回分别建模，避免执行端擅自改语义。
- `trade-execution` 在展示或挂保护单前确定性校验 `review.stop_semantics`；只有 `INTRADAY_HARD` 能生成实时 STOP_LIMIT，收盘确认只给人工监控/退出流程。
- 新增普通交易和历史导入交易两条独立的事后复盘门禁；MSFT 这类上线前成交使用 `mark_historical_reviewed`，保留原成交与错误委托，不事后篡改原计划。
- fresh-context 审计后修正四处跨层契约：B1 盘中硬止损仅限手紧模式；B2 新入场“两日不爆发”与已上涨回调拆成独立模板；Skill 的字段/价位约束与底层服务完全一致；历史复盘只接受恰好一笔历史交易的定向审计。
- market-review 63 项、trade-execution 118 项契约测试通过；两项 Skill 均通过 skill-creator 快速校验。

## 2026-10-27 · 复盘与执行 Skill 正式回收源仓库
- 将本机已验证的 `market-review` 与 `trade-execution` 完整源码回收到 `skills/`，包含引用文档、审计脚本、契约测试和 UI 元数据；真实本机目标继续只留在忽略的 `config.local.json`。
- `market-review` 统一美股 / A股复盘，`trade-execution` 只处理已落库、已批准的交易单；旧 `us-market-review` 收窄为只能显式调用、不携带复盘逻辑的兼容别名，防止与新 Skill 重复触发。
- 默认安装清单已切到四个活跃 Skill；发布前须通过 skill-creator 快速校验、两套契约测试、重装与源/安装哈希比对。

## 2026-10-22 · 美股复盘审计兼容非 B1 图
- 修正真实产物复验发现的误报：搬砖、单针等非 B1 候选可以带有已读的 TDX 图证据，不再因此被错误要求存在 B1 review result。
- B1 图仍必须与 B1 复核结果对应；所有候选图仍继续校验文件、哈希和实际读图证据。

## 2026-10-22 · 美股全量复盘 Skill
- 新增 us-market-review：把“美股复盘”固定为当日候选、数据库持续观察、状态变化和月度全表的一次性核对。
- 加入本地产物审计，校验报告日期、complete、图片哈希、读图证据和图内 token；脚本只做完整性门禁，不替代逐图判断。
- 观点仓 XDV/BNC 使用独立段落，保留周线确认、祖宗目标、止损、赔率和 CAD 20,000 机会池约束。
- 本机项目与数据库地址只进入忽略的 config.local.json；公开仓库只保留占位模板。
- 官方 Skill 校验、Python 编译、2026-10-22 真实产物审计均通过；安装副本逐文件一致，重复安装保留本机配置。

## 2026-10-22 · 发布确认
- main 推送成功，GitHub 确认仓库 PUBLIC，远端 main 与本机提交一致。
- 本机全局规则已保存源仓库位置、安装流程和公开内容边界。
- 后续直接在 skills/ 维护，安装、校验、commit、push。

## 2026-10-22 · 导入、安装及公开仓库创建
- 导入 ste-fr 和 lexicon-ingest，加入安装脚本和 config.example.json。
- 词库目标从指令迁入忽略的 config.local.json；ste-fr 使用 Skills 清单或相邻目录解析委托。
- 两个 Skill 官方校验通过，安装后逐文件哈希一致；临时目录重复安装验证本机配置不变。
- 创建 https://github.com/Yannyehao/codex-skills，公开历史从干净骨架开始。
- 发布文件检查通过，不包含旧聊天词库审计、本机绝对路径或数据库标识。
- 下一步：推送 main 并核对远端可见性与提交；后续 Skills 从本仓库维护。

## 2026-10-22 · 初始化
- 用户授权创建公开仓库，后续个人 Skills 统一放在这里。
- 选择独立仓库，避免公开包含个人词库审计的旧聊天历史。
- 下一步：导入规则、校验安装并推送。
