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

## 风险与边界
- 公开内容仅包括可复用规则，不包含词库快照、批次审计、认证信息或本机配置。
- 配置文件只留本机；重复安装须保留本机配置。
- 安装成功不代表所有产品均支持本地 Skill；此安装目标为本机 Codex。

## 状态
已完成：ste-fr、lexicon-ingest、market-review 与 trade-execution 均纳入统一维护。market-review 以“当日全集 + 完整活跃机会 + 状态变化 + 月度全表”为两市复盘边界；trade-execution 只处理已落库、已批准的交易单和有券商证据的委托/成交事实。旧 us-market-review 已收窄为只能显式调用的无逻辑兼容别名，普通美股复盘不会重复触发。官方校验、契约测试、安装副本比对和本机配置保留是发布门禁。
