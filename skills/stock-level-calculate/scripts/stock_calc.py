# -*- coding: utf-8 -*-
"""
库存水位计算 —— 销量速率 / 安全库存 / 断货窗口 / 建议下单量确定性测算 + 产物生成。

职责边界（重要）：
  本脚本只做**确定性计算与产物生成**：四步公式逐步算出并保留算式、
  敏感性口径（日销波动、到货延迟）的确定性重算、CSV/JSON/MD 落盘。
  「要不要按建议下单」「是否紧急加单」的决策措辞，由模型按 prompt.txt 完成。

计算公式（与 prompt.txt 一致，可用 rules 覆盖）：
  F1 日均销量速率   = 近 7 日合计销量 ÷ 7
  F2 补货周期内预计销量 = 日均销量速率 × 补货周期（默认 7 天）
  F3 安全库存       = 补货周期内预计销量 × 安全系数（默认 1.2）
  F4 库存覆盖天数   = 当前可用库存 ÷ 日均销量速率（向下取整）
  F5 到货前缺口     = 日均销量速率 × 到货等待天数 - 当前可用库存（为负则 0）
  F6 建议下单量     = F2 + F3 - 当前可用库存 - 在途库存（为负则 0）

用法：
  python stock_calc.py --input input.json --outdir out
  python stock_calc.py --demo --outdir out

产物：
  out/测算明细.csv     逐项算式（项目/计算式/结果/说明）
  out/库存测算报告.md  人类可读报告（结果 + 测算明细 + 假设与敏感性）
  out/stock_calc.json  机器可读结果（供工作流/下游技能读取）
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(HERE), "out"))

DEFAULT_RULES = {
    "sales_days": 7,          # F1 统计窗口（天）
    "lead_time_days": 7,      # 补货周期（天）
    "safety_factor": 1.2,     # F3 安全系数
}


def demo_data():
    """来自 runs_v2 实跑输入（SKU-1002 玻璃双层水杯450ml 三店共享仓）。"""
    return {
        "sku": "SKU-1002 玻璃双层水杯450ml（三店共享仓）",
        "params": {
            "sales_recent_days": 280,   # 近 7 日三店合计销量（件）
            "available": 120,           # 当前可用库存（件）
            "in_transit": 200,          # 在途采购单（件）
            "eta_days": 4,              # 在途到货等待（天，10-08 → 10-12）
        },
        "rules": {},
    }


def calc(payload):
    rules = {**DEFAULT_RULES, **(payload.get("rules") or {})}
    p = payload.get("params") or {}
    need = ["sales_recent_days", "available", "in_transit"]
    missing = [k for k in need if p.get(k) is None]
    if missing:
        raise SystemExit(f"[错误] params 缺少字段 {missing}：列出缺失清单让用户补齐，不估算")

    sales = float(p["sales_recent_days"])
    avail = float(p["available"])
    transit = float(p["in_transit"])
    eta = float(p.get("eta_days") or rules["lead_time_days"])

    f1 = sales / rules["sales_days"]
    f2 = f1 * rules["lead_time_days"]
    f3 = f2 * rules["safety_factor"]
    f4 = math.floor(avail / f1) if f1 > 0 else 0
    f5 = max(0.0, f1 * eta - avail)
    f6 = max(0.0, f2 + f3 - avail - transit)

    breakdown = [
        {"项目": "日均销量速率", "计算式": f"{sales:.0f} 件 ÷ {rules['sales_days']} 天",
         "结果": f"{f1:.0f} 件/天", "说明": f"近 {rules['sales_days']} 日合计销量的日均值"},
        {"项目": "补货周期内预计销量", "计算式": f"{f1:.0f} 件/天 × {rules['lead_time_days']} 天",
         "结果": f"{f2:.0f} 件", "说明": f"补货周期 {rules['lead_time_days']} 天"},
        {"项目": "安全库存", "计算式": f"{f2:.0f} 件 × {rules['safety_factor']}",
         "结果": f"{f3:.0f} 件", "说明": f"安全系数 {rules['safety_factor']}"},
        {"项目": "库存覆盖天数", "计算式": f"{avail:.0f} 件 ÷ {f1:.0f} 件/天",
         "结果": f"{f4} 天", "说明": f"自今日起约 {f4} 天售罄"},
        {"项目": "到货前缺口", "计算式": f"{f1:.0f} 件/天 × {eta:.0f} 天 - {avail:.0f} 件",
         "结果": f"{f5:.0f} 件", "说明": f"在途 {transit:.0f} 件 {eta:.0f} 天后入仓"},
        {"项目": "建议下单量", "计算式":
            f"{f2:.0f} + {f3:.0f} - {avail:.0f} - {transit:.0f}",
         "结果": f"{f6:.0f} 件", "说明": "周期内预计销量 + 安全库存 - 可用库存 - 在途库存"},
    ]
    result = (f"安全库存 {f3:.0f} 件；当前可用库存可支撑 {f4} 天；"
              f"到货前缺口 {f5:.0f} 件；建议下单 {f6:.0f} 件")

    # 敏感性口径（确定性重算）
    sensitivity = [
        f"若日销速率升至 {f1 * 1.5:.0f} 件/天（+50%），覆盖天数缩短为 "
        f"{math.floor(avail / (f1 * 1.5))} 天，到货前缺口扩大至 {max(0.0, f1 * 1.5 * eta - avail):.0f} 件。",
        f"若在途 {transit:.0f} 件延迟 2 天入仓（等待 {eta + 2:.0f} 天），"
        f"到货前缺口扩大至 {max(0.0, f1 * (eta + 2) - avail):.0f} 件。",
        f"若安全系数改为 1.5，安全库存升至 {f2 * 1.5:.0f} 件，建议下单量相应增至 "
        f"{max(0.0, f2 + f2 * 1.5 - avail - transit):.0f} 件。",
    ]
    assumptions = [
        "假设近 7 日销量速率在未来两周保持稳定；大促脉冲需单独按活动预测重算。",
        "假设在途采购按预计入仓日准时到货；供应商延迟按敏感性第 2 条口径放大缺口。",
        f"安全系数 {rules['safety_factor']} 与补货周期 {rules['lead_time_days']} 天为本技能声明值，可用 rules 覆盖。",
    ]
    stats = {
        "日均销量速率": round(f1, 1), "安全库存": round(f3),
        "覆盖天数": f4, "到货前缺口": round(f5), "建议下单量": round(f6),
    }
    return result, breakdown, sensitivity + assumptions, stats


def write_outputs(result, breakdown, assumptions, stats, outdir):
    os.makedirs(outdir, exist_ok=True)
    files = []

    csv_path = os.path.join(outdir, "测算明细.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["项目", "计算式", "结果", "说明"])
        w.writeheader()
        for r in breakdown:
            w.writerow(r)
    files.append(csv_path)

    md = ["**AI 生成内容**", "", "## 结果", "", result, "", "## 测算明细", "",
          "| 项目 | 计算式 | 结果 | 说明 |", "|---|---|---|---|"]
    for r in breakdown:
        md.append(f"| {r['项目']} | {r['计算式']} | {r['结果']} | {r['说明']} |")
    md += ["", "## 假设与敏感性", ""] + [f"{i}. {x}" for i, x in enumerate(assumptions, 1)]
    md_path = os.path.join(outdir, "库存测算报告.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    files.append(md_path)

    js_path = os.path.join(outdir, "stock_calc.json")
    with open(js_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "result": result, "breakdown": breakdown,
                   "assumption": assumptions,
                   "note": "全部数值由本脚本按公式计算；下单决策措辞由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(js_path)
    return files


def main():
    ap = argparse.ArgumentParser(description="库存水位计算（速率/安全库存/缺口/建议下单量）")
    ap.add_argument("--input", help="输入 JSON（params/rules）")
    ap.add_argument("--outdir", default=OUT_DEFAULT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = demo_data() if a.demo else (
        json.load(open(a.input, encoding="utf-8")) if a.input else ap.error("需要 --input 或 --demo"))

    result, breakdown, assumptions, stats = calc(payload)
    files = write_outputs(result, breakdown, assumptions, stats, a.outdir)
    print(f"测算完成 —— 日均 {stats['日均销量速率']} 件/天，覆盖 {stats['覆盖天数']} 天，"
          f"缺口 {stats['到货前缺口']} 件，建议下单 {stats['建议下单量']} 件")
    for f in files:
        print(" 产物:", f, f"({os.path.getsize(f) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
