# 质量基线：多店运营官

> 本资产包的**可量化验收指标**。任何版本发布前必须全部达标。

---

## 一、资产完整性

| 指标 | 阈值 | 验证方式 |
|------|------|---------|
| 技能四件套齐全率 | 100% | `test_skill_four_pieces` |
| 技能 examples 齐全率 | 100% | `test_skill_examples_exist` |
| 工作流定义齐全率 | 100% | `test_workflow_required_sections` |
| 文档交付物齐全率 | 100% | `test_docs_complete` |
| README 链接可解析率 | 100% | `test_readme_links` |

## 二、提示词质量

| 指标 | 阈值 | 验证方式 |
|------|------|---------|
| 必需区块覆盖率 | 100% | `test_prompt_required_sections` |
| 字数范围 | 300-1200 字 | `test_prompt_length` |
| 禁止事项非空 | 100% | `test_prompt_forbidden_section` |
| 合规声明存在 | 100% | `test_prompt_compliance_section` |

## 三、契约一致性

| 指标 | 阈值 | 验证方式 |
|------|------|---------|
| schema.json 合法 | 100% | `test_schema_valid_json` |
| schema 与 SKILL.md 一致 | 100% | `test_schema_matches_skill_md` |
| 输入字段在 prompt 中有说明 | 100% | `test_inputs_documented` |

## 四、安全

| 指标 | 阈值 | 验证方式 |
|------|------|---------|
| API Key 泄漏 | 0 | `test_no_api_key_leaked` |
| 运行时外部依赖 | 0 | `test_requirements_minimal` |
| 可执行脚本 | 0 | 目录扫描 |

## 五、图表

| 指标 | 阈值 |
|------|------|
| Mermaid 代码块配对 | 100% |
| 架构图存在 | ✅ |
| 工作流图存在 | ✅ |

---

## 六、当前状态

| 维度 | 状态 |
|------|------|
| 技能 | 5 个，四件套齐全 |
| 工作流 | 5 条，定义完整 |
| 文档 | 7 份，齐全 |
| 外部依赖 | 仅 pytest |

---

*基线版本：v2.0 · 2026-09-29*
