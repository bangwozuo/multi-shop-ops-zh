# -*- coding: utf-8 -*-
"""
库存同步与超卖预警工作流 —— 端到端编排脚本（与 SKILL.md 的 DAG 一致）。

流程：
  S1 库存水位计算（原子技能 stock-level-calculate）
      日均速率 = 近 7 日销量 ÷ 7；安全库存 = 周期预计销量 × 1.2；
      覆盖天数、到货前缺口、建议下单量
  S2 超卖预警（原子技能 oversell-alert）
      净可用 = 可用 - 在途订单 < 0 → 紧急；可用 < 安全水位 → 高
  S3 预警推送清单
      紧急项置顶 + 建议处置窗口（紧急 2 小时内 / 高 今日内）

本脚本承担 S1-S3 的确定性部分；补货决策与推送措辞由模型按 prompt.txt 完成。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/step1_水位测算.json / out/step2_预警清单.json   各步中间产物（每步读上一步产物）
  out/预警清单.csv / out/预警推送.md                  最终交付物
  out/flow_result.json                                机器可读汇总
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(HERE), "out"))

RULES = {"sales_days": 7, "lead_time_days": 7, "safety_factor": 1.2}


def demo_data():
    """来自 runs_v2 实跑输入（2026-10-08 14:00 三店库存同步任务）。"""
    return {
        "date": "2026-10-08",
        "calc": {"sku": "SKU-1002 玻璃双层水杯450ml", "sales_recent_days": 280,
                 "available": 120, "in_transit_purchase": 200, "eta_days": 4},
        "snapshot": [
            {"sku": "SKU-1001 316不锈钢保温杯", "available": 45, "in_transit_orders": 60, "water": 50},
            {"sku": "SKU-1002 玻璃双层水杯", "available": 120, "in_transit_orders": 30, "water": 50},
            {"sku": "SKU-1003 陶瓷马克杯", "available": 18, "in_transit_orders": 15, "water": 30},
            {"sku": "SKU-1004 便携榨汁杯", "available": 0, "in_transit_orders": 5, "water": 20},
            {"sku": "SKU-1005 家用烘鞋器", "available": 210, "in_transit_orders": 12, "water": 50},
        ],
    }


def step1_water_calc(payload, outdir):
    """S1 库存水位计算：读输入，产出水位测算。"""
    c = payload.get("calc") or {}
    need = ["sales_recent_days", "available", "in_transit_purchase"]
    missing = [k for k in need if c.get(k) is None]
    if missing:
        raise SystemExit(f"[错误] calc 缺少字段 {missing}：列出缺失清单让用户补齐，不估算")
    rate = c["sales_recent_days"] / RULES["sales_days"]
    cycle_sales = rate * RULES["lead_time_days"]
    safety = cycle_sales * RULES["safety_factor"]
    cover = math.floor(c["available"] / rate) if rate > 0 else 0
    eta = c.get("eta_days") or RULES["lead_time_days"]
    gap = max(0.0, rate * eta - c["available"])
    order_qty = max(0.0, cycle_sales + safety - c["available"] - c["in_transit_purchase"])
    result = {"sku": c.get("sku", ""), "rate": round(rate, 1),
              "cycle_sales": round(cycle_sales), "safety": round(safety),
              "cover_days": cover, "gap": round(gap), "order_qty": round(order_qty)}
    path = os.path.join(outdir, "step1_水位测算.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def step2_alerts(payload, outdir):
    """S2 超卖预警：读 S1 产物 + 全量快照，两级判定。"""
    water = json.load(open(os.path.join(outdir, "step1_水位测算.json"), encoding="utf-8"))
    rows = payload.get("snapshot") or []
    if not rows:
        raise SystemExit("[错误] snapshot 为空：请提供可用库存与在途订单快照，不估算")
    alerts = []
    for r in rows:
        avail, transit = int(r["available"]), int(r["in_transit_orders"])
        net = avail - transit
        w = r.get("water")
        if net < 0:
            alerts.append({"sku": r["sku"], "level": "紧急", "type": "超卖风险",
                           "avail": avail, "transit": transit, "net": net,
                           "water": w, "dev": (avail - w) if w is not None else None,
                           "rule": "可用-在途 < 0 判超卖"})
        elif w is not None and avail < w:
            alerts.append({"sku": r["sku"], "level": "高", "type": "低库存预警",
                           "avail": avail, "transit": transit, "net": net,
                           "water": w, "dev": avail - w,
                           "rule": "可用 < 安全水位判低库存"})
    result = {"water_calc": water, "alert_count": len(alerts), "alerts": alerts}
    path = os.path.join(outdir, "step2_预警清单.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def step3_push(step2, payload, outdir):
    """S3 预警推送：读 S2 产物，紧急置顶 + 处置窗口。"""
    alerts = json.load(open(os.path.join(outdir, "step2_预警清单.json"), encoding="utf-8"))["alerts"]
    alerts.sort(key=lambda a: 0 if a["level"] == "紧急" else 1)
    lines = ["**AI 生成内容**", "",
             f"# 库存预警推送（{payload.get('date', '')} 三店共享仓）", "",
             "| # | SKU | 级别 | 类型 | 可用 | 在途订单 | 净可用 | 水位 | 偏离 | 判定规则 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for i, a in enumerate(alerts, 1):
        lines.append(f"| {i} | {a['sku']} | {a['level']} | {a['type']} | {a['avail']} 件 "
                     f"| {a['transit']} 件 | {a['net']} 件 | {a['water']} 件 "
                     f"| {a['dev']} 件 | {a['rule']} |")
    lines += ["", "## 建议处置", ""]
    for i, a in enumerate(alerts, 1):
        window = "2 小时内下架或联系买家协商" if a["level"] == "紧急" else "今日内补货或调拨"
        lines.append(f"{i}. {a['sku']}（{a['type']}）：{window}")
    md_path = os.path.join(outdir, "预警推送.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    csv_path = os.path.join(outdir, "预警清单.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["#", "SKU", "级别", "类型", "可用件", "在途订单件", "净可用件", "水位件", "偏离件", "判定规则"])
        for i, a in enumerate(alerts, 1):
            w.writerow([i, a["sku"], a["level"], a["type"], a["avail"], a["transit"],
                        a["net"], a["water"], a["dev"], a["rule"]])
    return [md_path, csv_path]


def main():
    ap = argparse.ArgumentParser(description="库存同步与超卖预警工作流（水位→预警→推送）")
    ap.add_argument("--input", help="输入 JSON")
    ap.add_argument("--outdir", default=OUT_DEFAULT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = demo_data() if a.demo else (
        json.load(open(a.input, encoding="utf-8")) if a.input else ap.error("需要 --input 或 --demo"))
    os.makedirs(a.outdir, exist_ok=True)

    s1, p1 = step1_water_calc(payload, a.outdir)
    s2, p2 = step2_alerts(payload, a.outdir)
    files = step3_push(s2, payload, a.outdir)

    result_path = os.path.join(a.outdir, "flow_result.json")
    json.dump({"flow": "stock-sync-oversell-alert-flow", "steps": [p1, p2] + files,
               "summary": f"水位测算完成（建议下单 {s1['order_qty']} 件），"
                          f"预警 {s2['alert_count']} 条（紧急置顶）",
               "note": "数值由本脚本判定；补货决策与推送措辞由模型按 prompt.txt 完成"},
              open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"工作流完成 —— 建议下单 {s1['order_qty']} 件；预警 {s2['alert_count']} 条")
    for f in [p1, p2] + files + [result_path]:
        print(" 产物:", f)


if __name__ == "__main__":
    main()
