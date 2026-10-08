# 多店运营官 — 业务架构

## 四层视图

```mermaid
flowchart TD
    subgraph L1["① 用户层"]
        U["同时运营 2-4 个平台、SKU 20-500 的卖家"]
    end

    subgraph L2["② 数字员工层"]
        E["多店运营官<br/>一人店的"轻量 ERP"，只做真正用的 20% 功能"]
    end

    subgraph L3["③ 工作流层（5 条）"]
        W1["一稿多平台 Listing 生成"]
        WN["…共 5 条"]
    end

    subgraph L4["④ 原子技能层（5 个）"]
        SK1["类目属性映射"]
        SK2["标题多平台改写"]
        SK3["库存水位计算"]
        SK4["超卖预警"]
        SK5["竞品价格巡检"]
    end

    U -->|"提出需求"| E
    E -->|"编排调用"| W1
    W1 --> WN
    W1 --> SK1

    style L1 fill:#E8F4FD,stroke:#1976D2,color:#0D47A1
    style L2 fill:#FFF3E0,stroke:#E65100,color:#BF360C
    style L3 fill:#F3E5F5,stroke:#7B1FA2,color:#4A148C
    style L4 fill:#E8F5E9,stroke:#388E3C,color:#1B5E20
```

## 资产形态说明

本资产包为**纯提示词客户端资产**：

| 特性 | 说明 |
|------|------|
| 无运行时依赖 | 不调用任何模型 API，不需要 API Key |
| 平台无关 | 提示词为纯文本，可导入任意主流 AI 平台 |
| 用户自备算力 | 模型由用户自己的订阅提供 |
| 零服务端成本 | 资产方不产生任何调用费用 |

## 数据流

```mermaid
flowchart LR
    A["用户输入"] --> B["选择技能<br/>（粘贴 prompt.txt）"]
    B --> C["AI 按提示词处理"]
    C --> D["合规自检"]
    D --> E["人工审核"]
    E --> F["交付使用"]

    style D fill:#FFEBEE,stroke:#C62828,color:#B71C1C
    style E fill:#FFF9C4,stroke:#F9A825,color:#F57F17
```

> **关键设计**：所有对外输出必须经过「合规自检 → 人工审核」双闸门。

## 能力边界

| 维度 | 内容 |
|------|------|
| **目标用户** | 同时运营 2-4 个平台、SKU 20-500 的卖家 |
| **做** | Listing 生成、规格映射、库存水位监控、价格巡检 |
| **不做** | 不做：自动改价、自动采购下单 |
| **KPI** | 单款铺货耗时 90 分钟→15 分钟；超卖事故 = 0；价格异动发现 ≤1 小时 |
| **定价** | 50-100 元/月（R3 付费矩阵接受度最高项） |

---

*本图由 build_p0_assets.py 自动生成*
