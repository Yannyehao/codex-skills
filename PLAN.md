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
4. 固化两市全量复盘契约，统一当日机器产物、持续观察状态与月度台账。
5. 固化交易执行契约：只从已落库且已人工批准的交易单开始，校验委托语义并按券商证据记录完整生命周期。
6. 固化止损语义与复盘闭环：把有出处的 B1 / B2 / 搬砖规则收敛为 `zge-stop-v1` 的精确交易类型；每种类型唯一决定止损依据、触发时点与状态/时间退出，执行端不得再自由拼装；历史导入交易使用独立追加式复盘，不事后改写原计划。
7. 为交易执行加入隔离的历史 replay：截止日计划、单个执行日的开盘和收盘分阶段揭示，复用 `zge-stop-v1`，只以 exclusive create 生成明确标记的模拟 JSON journal，零生产账本 / 券商副作用；后续 session / 持仓管理不在 v1。

## 风险与边界
- 公开内容仅包括可复用规则，不包含词库快照、批次审计、认证信息或本机配置。
- 配置文件只留本机；重复安装须保留本机配置。
- 安装成功不代表所有产品均支持本地 Skill；此安装目标为本机 Codex。

## 状态
已完成：ste-fr、lexicon-ingest、market-review 与 trade-execution 均纳入统一维护。market-review 以“当日全集 + 完整活跃机会 + 状态变化 + 月度全表”为两市复盘边界；交易单只选择一个精确 `trade_type`，由 `zge-stop-v1` 唯一生成止损依据、触发方式和状态/时间退出。当前六类为 K 线 B1、白线超短 B1、黄线波段 B1、新鲜 B2、已上涨回调 B2、砖 0 日；松紧环境不再参与止损选择。trade-execution 的 live lane 只处理已落库、已批准、带统一策略标记且语义匹配的交易单，阻止把收盘确认翻译成盘中硬止损；独立 replay lane 不读生产服务，以 cutoff → 单日 open → 单日 close 三阶段模拟历史执行并只增不改地输出可审计 JSON journal，v1 不延伸到后续 session。无标记旧单只能做终态历史复盘，不能重新进入执行。旧 us-market-review 已收窄为只能显式调用的无逻辑兼容别名。官方校验、契约测试、安装副本比对和本机配置保留是发布门禁。
