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

## 风险与边界
- 公开内容仅包括可复用规则，不包含词库快照、批次审计、认证信息或本机配置。
- 配置文件只留本机；重复安装须保留本机配置。
- 安装成功不代表所有产品均支持本地 Skill；此安装目标为本机 Codex。

## 状态
骨架建立，待导入和发布。
