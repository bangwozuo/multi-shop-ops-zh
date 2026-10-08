# Changelog

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.3.0] - 2026-09-29

### Added

- **独立 `workflows/` 目录**：工作流（复合技能）从 `skills/` 迁出，物理独立、规范不变
- **技能级 / 工作流级 `docs/`**：每个资产自带 10 项文档
  （安装使用手册 / 业务架构图 / 流程图 / 使用示例 / 截图和录屏 / 使用场景 / 用户群体 / 解决问题与价值 / 测试报告 + README）
- **自动生成的流程示意图**：`docs/assets/overview.svg`
- **RAG wiki 知识库**：`knowledge/` 升级为 `wiki/`（索引 + 模板 + 分主题词条）+ RAG 接入指南
- **结构化连接器**：`connectors/` 含索引 + 每个连接器一份说明 + `COMPLIANCE.md` 合规红线
- 资产校验测试覆盖上述新结构

### Changed

- 技能命名全面业务化（去 `S1`/`W1` 编号与「（复用）」前缀）
- 原子技能能力族标签由生成器统一推导

## [0.2.0] - 2026-09-29

### Changed

- **BREAKING**：资产形态从「含模型调用代码」重构为「纯提示词资产」
- 移除 `_shared/llm.py` 与 `skills/*/skill.py`
- 移除 `openai` 依赖与 API Key 要求
- 测试改为资产质量校验（无需任何密钥）

### Added

- `skills/*/schema.json` — 输入输出契约
- 跨平台导入指引（Coze / WorkBuddy / Dify / Claude / ChatGPT）
- `knowledge/template.md` — 知识库填写模板
- 资产校验测试套件

### Removed

- `_shared/` 目录（LLM 客户端与编排器）
- `requirements.txt` 中的 `openai`

## [0.1.0] - 2026-09-29

### Added

- 初始脚手架（含模型调用代码，已于 v0.2.0 废弃）
