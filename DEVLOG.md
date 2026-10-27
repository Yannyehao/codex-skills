# DEVLOG

## 2026-10-27 · 对齐 zAI 冻结核心契约 54ba4cb6（生命周期卡片 + 持久化审批面）
- 只读对照 zAI 提交 54ba4cb6 的 `opportunity_episode_contract.md`（§5 卡片、§14 规范语法、§15 TrendAlive）与 `trade_lifecycle_contract.md` §9a（`ticket_state` 现在直接暴露 `profile` 与 `approval`）；未碰 Notion/TDX/券商/本机配置/数据库，未复制整套业务语法。
- market-review：review-contract.md 新增「规范表示：生命周期卡片」一节，只写阅读规则、语法本体留在服务契约：高召回 OR（新原始信号 + 每个未终结的活跃 episode，一 episode 一卡，闸 FAIL 不抹卡）；六个闸是可读的 PASS/WAIT/FAIL 证据，不是 AND 过滤也不是分数；TrendAlive（仅父趋势确认终结）是唯一的宽泛活跃工作集排除，警告保持可见；单针＝发现/观察；触发永不自动 ACTIONABLE；人工复核最多建 DRAFT；所有证据保留 knowledge_class。复盘只读命令扩为 list/state/cards/audit/hierarchy；ticket-draft 增加「阶段与 ACTIONABLE 永不由复核者设定」的前置条件。美股/A股画像保持薄，不重述语法；不新建 A 股重复 Skill；us-market-review 仍是显式兼容别名。
- trade-execution：audit_ticket.py 改为直接读 `state.approval`（持久化的 APPROVED 事件审批哈希，须等于 `terms_sha256`、`matches_ticket_terms` 为真、与唯一 APPROVED 事件的人/时间/序号一致）与 `state.profile`（须重算等于 `profile_sha256`；每手股数与 T+N 取自它，不再内置表）。删除 `--approved-terms-sha256`（命令行传入会被 argparse 拒绝）；`approval` 缺失/为 null/不一致一律 BLOCKED，绝不推断、不替人批准、不自动化券商。文档（SKILL/service-cli/ticket-contract/profiles）同步。
- 测试：test_audit_ticket 扩到 62 项（持久化审批、缺失/篡改、画像哈希、画像驱动的手数与 T+1、命令行拒收哈希参数）；新增两份 test_skill_contract.py（market-review 18 项、trade-execution 11 项），证明上述阅读规则/边界在文档里、画像保持薄、别名仅显式、示例配置只含占位符、无机器绝对路径、本机配置被忽略。做过变异验证（删规则/删哈希比较均令测试失败）。
- 验证：market-review 31 项（audit_review 13 + 契约 18）、trade-execution 73 项（audit_ticket 62 + 契约 11）单元测试通过；四个脚本与两份契约测试 py_compile 通过；market-review、trade-execution、us-market-review 的系统 quick_validate 均 valid。未安装、未提交、未推送。
- 下一步：Codex 复核后安装并提交；用真实 `state` 输出做一次只读 pre-submit 演练，确认 `approval`/`profile` 形状与此一致。

## 2026-10-27 · 对齐生命周期服务契约 v6（消除虚构导出）
- 只读对照 zAI 兄弟工作树的 trade_lifecycle.py、opportunity_ledger.py、trade_lifecycle_contract.md（未碰其它文件、本机配置、数据库、网络）。
- audit_ticket.py 重写：直接读取 `python -m zradar.trade_lifecycle state` 的原始 JSON（market US/A、大写状态、MARKETABLE_LIMIT/PASSIVE_LIMIT、expiry_date YYYYMMDD、entry_planned/entry_max、stop_trigger/stop_limit、targets、risk_budget/capital_budget、quantity、review、setup_quality/decision_lane/capital_stage/min_reward_risk，金额为十进制文本）。旧的虚构字段（status/approval/entry/protective/risk/portfolio…）一律拒绝，不映射。
- 审批闸：唯一 APPROVED 事件的 actor 必须是 `human:<name>`，且与 approved_by/approved_at 一致；`--approved-terms-sha256` 必须等于 ticket 的 terms_sha256；`audit --ticket-id` 必须对该票干净；state 与 journal_state 一致。不接受聊天重建。
- 资金成熟度：A_CIRCLE/质量 A、PRACTICE/质量 VALID 可批准，AMBIGUOUS/REJECT 永不可执行；PRACTICE 要求落库的 min_reward_risk、完整逻辑与明确止损；max_loss ≤ risk_budget、worst cost ≤ capital_budget、r_multiple ≥ min_reward_risk 对所有通道成立；金额按服务公式重算并与落库值比对。脚本不含任何美元/R 阈值；capital_stage 只检查是否存在。
- 新增 `check-args`（按服务函数签名校验 `apply --args-json`，禁止 approve/create_draft/mark_reviewed、禁止 now、禁止 float 与错误演员）、`scale-up-proposal`（校验服务 scale-up 结果仅为提议：同战法、样本>1、四道闸全过、政策回显、proposal_only）；`idempotency-key` 改按服务操作名。
- 取舍：移除了旧的组合集中度/账户权益与手输 `--veto`，因为服务票据不落库这些输入（否决复核已随票据落库，MARKETABLE 以落库的 veto_review 为准）；`state` 只导出 profile_sha256，不含 profile 主体，市场字段决定画像。
- 新增 references/service-cli.md（具体 CLI 命令、退出码、事件→操作→参数表）与 capital-maturity.md；ticket-contract/order-semantics/profiles/SKILL 全部重写；market-review 增加 ticket-draft.md（仅 `create_draft`，质量分类，预算由用户/账户政策提供）并在契约中声明复盘不定尺寸、不提放大。
- 验证：audit_ticket 56 项、audit_review 13 项合成数据单元测试全部通过；四个脚本 py_compile 通过；market-review、trade-execution、us-market-review 的 quick_validate 均 valid；未安装、未提交、未推送。
- 下一步：监督者审阅后安装；把本机 config.local.json 补上 lifecycle_service 段；用真实服务输出做一次只读 `pre-submit` 演练。

## 2026-10-27 · 跨市场复盘与交易单执行 Skills
- 新增 market-review：共享复盘契约（最近一个完整收盘交易日、新候选 + 全部活跃行 + 状态变化 + 月度全表、人工状态优先、必须真实读图、每个活跃项一个可观察阻碍与期限）+ 美股/A股画像；复盘只读，明确要求才可固化 DRAFT 交易单，永不批准或下单。
- 审计脚本重写为 audit_review.py，修复已知缺陷：不再取字典序最新的不完整日期，而是选最新的完整同日产物包，并列出被跳过的更新日期；所选包内的哈希、读图证据、token 错误仍直接失败，不回退旧日期。兼容旧版平铺配置。
- 新增 trade-execution：只对已持久化且人工批准、未过期的交易单工作，缺项一律 fail closed；audit_ticket.py 只读演算（整数股数、成本、最大亏损、R、集中度、止损限价方向、A股 100 股/T+1/涨跌停），并给出事件幂等键。不点击券商提交。
- us-market-review 改为 allow_implicit_invocation:false 的薄别名，依赖同仓库安装的 market-review，不复制契约；旧契约、脚本、示例配置迁入 market-review，本机 config.local.json 不动。
- install.ps1：默认列表加入两个新 Skill；新增 -Prune（默认关闭）清除安装目录里源码已删除的旧文件，保留 *.local.json，并跳过 __pycache__。
- 验证：两套合成数据单元测试通过，临时目录安装验证 -Prune 与本机配置保留；未读生产数据、未联网、未提交。
- 下一步：监督者审阅后安装（建议带 -Prune，清掉旧别名目录里的旧脚本），把本机 us-market-review 配置按需迁成 market-review 的 profiles 格式（也可继续沿用旧配置），接入真实生命周期服务并核对字段映射。

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
