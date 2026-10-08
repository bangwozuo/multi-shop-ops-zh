# 多店运营官 — 使用手册

## 一、获取资产

```bash
git clone https://github.com/bangwozuo/multi-shop-ops-zh.git
cd multi-shop-ops-zh
```

无需安装任何依赖即可使用——**本资产包是纯提示词资产**。

## 二、最少三步上手

### 第 1 步：挑一个技能

打开 `skills/` 目录，选择你需要的技能。例如：

```
skills/category-attribute-mapping/
├── README.md       ← 先读这个，了解技能做什么
├── SKILL.md        ← 技能定义与契约
├── prompt.txt      ← 提示词本体，等下要复制这个
├── schema.json     ← 输入输出规格
├── examples/       ← 示例输入输出
└── docs/           ← 该技能自己的 10 项配套文档
```

### 第 2 步：复制提示词

打开 `prompt.txt`，**全文复制**。

### 第 3 步：粘贴到你常用的 AI 工具

| 平台 | 操作 |
|------|------|
| **Coze / 扣子** | 新建 Bot → 「人设与回复逻辑」→ 粘贴 → 发布 |
| **WorkBuddy** | 新建 Skill → 填入内容 → 保存 |
| **Dify** | 新建应用 → 「提示词编排」→ 粘贴 → 发布 |
| **Claude** | New Project → Instructions → 粘贴 |
| **ChatGPT** | 新建 GPT → Instructions → 粘贴 |
| **任意工具** | 直接作为系统提示词使用 |

然后按 `SKILL.md` 的「输入规格」提供数据即可。

## 三、工作流怎么用

单技能只能解决一件事。要跑完整流程，用 `workflows/` 目录下的**工作流**（复合技能）：

```
workflows/listing-multiplatform-flow/
├── README.md       ← 工作流说明
├── SKILL.md        ← 编排定义（含 DAG）
├── prompt.txt      ← 编排提示词（可直接粘贴）
├── schema.json     ← 输入输出规格
├── examples/       ← 示例
└── docs/           ← 该工作流自己的 10 项配套文档
```

也可以按 DAG 顺序手动串联：

```text
第 1 步：技能 A 的 prompt.txt → 输入数据 → 得到输出 A
第 2 步：技能 B 的 prompt.txt → 输入 A → 得到输出 B
第 3 步：技能 C 的 prompt.txt → 输入 B → 得到输出 C
```

### 在支持工作流的平台上

| 平台 | 编排方式 |
|------|---------|
| **Coze** | 新建工作流 → 按 DAG 添加节点，每节点用对应 prompt.txt |
| **Dify** | 新建 Workflow → 添加 LLM 节点链 |
| **WorkBuddy** | 新建 Skill，在指令中按顺序串联 |

## 四、知识库（可选但强烈建议）

`knowledge/` 目录是一个 **RAG wiki 结构**的知识库，填入你自己的业务信息后，
在 AI 工具中作为附件或 RAG 数据源挂载，效果会显著提升。

结构：

```text
knowledge/
├── README.md          使用说明
├── RAG-接入指南.md     切片 / 嵌入 / 召回策略
├── template.md        单文件快速模板
└── wiki/
    ├── index.md       词条索引
    ├── _template.md   词条模板
    └── entries/       分主题词条（业务基础 / 目标用户 / 语气人设 / 历史资产 / 规则手册）
```

适合填入的内容：

- 产品 / 商品的真实资料
- 历史高表现内容
- 平台规则手册
- 品牌语气规范

## 五、连接器（数据从哪来）

`connectors/` 目录说明每个数据源的**接入方式、授权方式、字段、合规边界、降级方案**：

```text
connectors/
├── README.md           索引 + 合规总原则
├── COMPLIANCE.md       合规红线清单
└── <连接器>.md          每个连接器一份说明
```

⚠️ 连接器**只有文档，没有代码**。两条合规路径：官方 API、用户自行导出的数据。

## 六、资产清单

| 目录 | 内容 | 数量 |
|------|------|------|
| `skills/` | 原子技能（每个含四件套 + 10 项 docs） | 5 |
| `workflows/` | 工作流（复合技能，每个含四件套 + 10 项 docs） | 5 |
| `knowledge/` | RAG wiki 知识库 | 5+ 文件 |
| `connectors/` | 连接器说明 + 合规清单 | 3+ 文件 |
| `docs/` | 员工级文档交付物 | 7 |
| `quality/` | 质量基线与追踪 | 2 |

## 七、常见问题

### Q1：需要 API Key 吗？

**不需要。** 本资产包是纯提示词，不含任何模型调用代码。
你用的模型和算力来自你自己的订阅。

### Q2：为什么没有 `.py` 脚本？

因为资产形态就是提示词。脚本会引入运行时依赖与 API Key 管理问题，
而提示词可以直接导入任何平台，零门槛。

### Q3：提示词太长了，平台有字数限制怎么办？

`prompt.txt` 已控制在 1200 字以内。若平台仍有上限，
可以删除「工作原则」中的次要条目，保留「角色」「输出格式」「禁止事项」「合规」四段核心。

### Q4：效果不好怎么办？

1. 先确认输入是否符合 `SKILL.md` 的输入规格
2. 检查是否挂载了知识库（有知识库的效果通常显著更好）
3. 参考 `examples/` 中的示例输入输出对照
4. 在仓库提 Issue 反馈

### Q5：能改提示词吗？

可以，Apache-2.0 协议允许修改与商用。建议改完后跑一遍 `pytest`
确认资产结构校验仍通过。

## 八、运行资产校验

```bash
pip install -r requirements.txt
pytest tests/ -v
```

这会校验：技能四件套完整性、提示词必需区块、schema 契约一致性、
工作流 DAG 完整性、技能级与工作流级 docs 完整性、知识库 wiki 与连接器结构。
**不需要任何 API Key。**

---

*需要帮助？请提 [Issue](https://github.com/bangwozuo/multi-shop-ops-zh/issues)*
