# Codex Skills 规划

## 目标
用公开 GitHub 仓库统一维护个人编写的可复用 Skills。

## 结构与环境
- `skills/<name>/SKILL.md`：规则源文件。
- `skills/<name>/agents/openai.yaml`：发现与调用元数据。
- `scripts/install.ps1`：复制安装到本机 Skills 目录。
- Windows PowerShell 5.1、Git、GitHub CLI；Skills 为纯文本指令。
- 仓库预定地址：https://github.com/Yannyehao/codex-skills

## 路线图
1. 初始化文档和 Git 骨架。
2. 导入 ste-fr 与 lexicon-ingest，将本机目标地址移入忽略配置。
3. 校验、安装、创建公开远端并推送，验证远端可见性和提交。
4. 固化美股全量复盘契约，统一当日机器产物、持续观察状态与月度台账。
5. 拆出跨市场 market-review（美股/A股画像）与 trade-execution（已批准交易单的下单核对与持仓生命周期）；us-market-review 降为显式兼容别名。

## 风险与边界
- 公开内容仅包括可复用规则，不包含词库快照、批次审计、认证信息或本机配置。
- 配置文件只留本机；重复安装须保留本机配置。
- 安装成功不代表所有产品均支持本地 Skill；此安装目标为本机 Codex。
- 复盘只读；交易单草稿须用户明确要求才固化（仅 `create_draft`，分类 setup 质量，预算/尺寸/最低盈亏比由用户或账户政策给出），批准、下单、成交永远由人完成并以证据记入本地生命周期服务（SQLite 为唯一真源，Notion 仅投影）。Skill 不点击券商提交、不自动化券商。
- 资金成熟度：A_CIRCLE（质量 A）与 PRACTICE（质量 VALID）可批准，AMBIGUOUS/REJECT 永不可执行；练习只缩仓不降 setup 有效性；max_loss ≤ risk_budget；不内置任何美元/R 阈值；放大只能由服务的同战法真实成交指标与调用方政策提议，绝不因单笔或兴奋。
- 契约对齐（zAI 冻结提交 54ba4cb6）：trade-execution 直接读取 `python -m zradar.trade_lifecycle state/audit` 的原始输出（schema v6），不做字段映射；审批闸直接读 `state.approval`（持久化的人工审批哈希，须等于 `terms_sha256`）与 `state.profile`（须重算等于 `profile_sha256`），不再让人手输 `--approved-terms-sha256`，缺失/不一致即 BLOCKED。market-review 以生命周期卡片为规范表示：高召回 OR、六闸是 PASS/WAIT/FAIL 可读证据而非过滤或分数、TrendAlive（仅确认终结）是唯一宽泛排除、单针只观察、触发永不自动 ACTIONABLE、人工复核最多建 DRAFT、证据保留 knowledge_class；语法本体只在服务契约，Skill 只写阅读规则。
- 费用、涨跌停比例、生命周期服务地址只放忽略的本机配置，不写死、不臆造。

## 状态
已完成：ste-fr、lexicon-ingest 与 us-market-review 均纳入统一维护。us-market-review 以“当日全集 + 数据库持续观察 + 状态变化 + 月度全表”为复盘边界，并用本地审计脚本拦截错日、漏图与伪读图；官方校验、真实产物审计、安装副本比对和本机配置保留均已通过。后续 Skills 统一在此维护。
进行中（待监督者审阅后安装）：market-review 与 trade-execution 已建，各带只读审计脚本与合成数据测试；trade-execution 已对齐生命周期服务契约 v6（原始 state JSON、CLI 映射、资金成熟度、放大提议）；us-market-review 仅作兼容别名。
