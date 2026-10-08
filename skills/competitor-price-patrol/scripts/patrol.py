# -*- coding: utf-8 -*-
"""
竞品价格巡检 —— 偏离率计算 + 阈值分级 + 大促标记拦截 + 产物生成。

职责边界（重要）：
  本脚本只做**确定性计算与产物生成**：偏离率、三级阈值判定、大促标记附加人工确认、
  CSV/JSON/MD 落盘。竞品降价背后的动机解读、跟价策略建议，由模型按 prompt.txt 完成。

判定规则（与 prompt.txt 一致，可用 rules 覆盖）：
  R1 下浮 ≥ 8%        → 「降价异动」，级别 高
  R2 下浮 5% ~ 8%     → 「关注」，级别 中
  R3 上浮 ≥ 8%        → 「涨价异动」，级别 中
  R4 其余（±5% 以内） → 正常，进「未命中项」
  R5 命中百亿补贴/限时直降等大促标记 → 无论偏离幅度，一律附加「需人工确认」
  偏离 = (当前价 - 7日均价) / 7日均价 × 100%

用法：
  python patrol.py --input input.json --outdir out
  python patrol.py --demo --outdir out

产物：
  out/预警清单.csv     逐条判定（指标/当前值/基线/偏离/级别/判定规则）
  out/巡检报告.md      人类可读报告（预警清单 + 未命中项 + 需人工确认）
  out/patrol.json      机器可读结果（供工作流/下游技能读取）
"""
from __future__ import annotations

import argparse
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(HERE), "out"))

DEFAULT_RULES = {
    "drop_high_pct": 8.0,     # R1 下浮 ≥ 8% 判降价异动（高）
    "drop_mid_pct": 5.0,      # R2 下浮 5%~8% 判关注（中）
    "raise_mid_pct": 8.0,     # R3 上浮 ≥ 8% 判涨价异动（中）
    "promo_keywords": ["百亿补贴", "限时直降", "秒杀", "大促"],
}


def demo_data():
    """来自 runs_v2 实跑输入（云澜家居专营店 5 个监控 SKU 快照）。"""
    return {
        "metrics": [
            {"item": "竞品A 316不锈钢保温杯500ml", "price": 79.0,
             "promo": "限时直降", "promo_price": 69.9},
            {"item": "竞品B 玻璃双层水杯450ml", "price": 35.0, "promo": ""},
            {"item": "竞品C 陶瓷马克杯380ml", "price": 25.9, "promo": "百亿补贴"},
            {"item": "竞品D 便携榨汁杯400ml", "price": 59.0, "promo": ""},
            {"item": "竞品E 家用烘鞋器", "price": 88.0, "promo": ""},
        ],
        "baseline": [
            {"item": "竞品A 316不锈钢保温杯500ml", "avg7": 82.5},
            {"item": "竞品B 玻璃双层水杯450ml", "avg7": 34.8},
            {"item": "竞品C 陶瓷马克杯380ml", "avg7": 29.9},
            {"item": "竞品D 便携榨汁杯400ml", "avg7": 58.5},
            {"item": "竞品E 家用烘鞋器", "avg7": 87.0},
        ],
        "rules": {},
    }


def patrol(payload):
    rules = {**DEFAULT_RULES, **(payload.get("rules") or {})}
    base = {b["item"]: b["avg7"] for b in payload.get("baseline") or []}
    rows = payload.get("metrics") or []
    if not rows:
        raise SystemExit("[错误] metrics 为空：请提供竞品当日采集价，缺失清单让用户补齐，不估算")

    alerts, no_alert, need_confirm = [], [], []
    for r in rows:
        item, price = r["item"], float(r["price"])
        if item not in base:
            need_confirm.append(f"{item}：无 7 日均价基线，无法计算偏离，请补充基线数据")
            continue
        avg = float(base[item])
        dev = (price - avg) / avg * 100
        eval_price = float(r["promo_price"]) if r.get("promo_price") else price
        dev_eval = (eval_price - avg) / avg * 100

        if dev_eval <= -rules["drop_high_pct"]:
            level, tag, rule = "高", "降价异动", f"到手价下浮 ≥ {rules['drop_high_pct']:.0f}%"
        elif dev_eval <= -rules["drop_mid_pct"]:
            level, tag, rule = "中", "关注", f"下浮 {rules['drop_mid_pct']:.0f}%~{rules['drop_high_pct']:.0f}%"
        elif dev_eval >= rules["raise_mid_pct"]:
            level, tag, rule = "中", "涨价异动", f"上浮 ≥ {rules['raise_mid_pct']:.0f}%"
        else:
            no_alert.append(f"{item}：当前价 {price} 元 vs 7 日均价 {avg} 元，偏离 {dev:+.1f}%（±5% 以内，正常）")
            continue

        promo = r.get("promo") or ""
        hit_promo = any(k in promo for k in rules["promo_keywords"])
        row = {"#": str(len(alerts) + 1), "指标": f"{item} 到手价",
               "当前值": f"{eval_price} 元" + (f"（{promo}）" if promo else ""),
               "基线": f"7 日均价 {avg} 元",
               "偏离": f"{dev_eval:+.1f}%", "级别": level,
               "判定规则": rule, "异动类型": tag}
        alerts.append(row)
        if hit_promo:
            need_confirm.append(f"{item}：命中大促标记「{promo}」，无论偏离幅度一律人工确认后再决定跟价")

    stats = {
        "巡检 SKU 数": len(rows), "预警条数": len(alerts),
        "高": len([a for a in alerts if a["级别"] == "高"]),
        "中": len([a for a in alerts if a["级别"] == "中"]),
        "正常条数": len(no_alert), "需人工确认条数": len(need_confirm),
    }
    return alerts, no_alert, need_confirm, stats


def write_outputs(alerts, no_alert, need_confirm, stats, outdir):
    os.makedirs(outdir, exist_ok=True)
    files = []

    csv_path = os.path.join(outdir, "预警清单.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["#", "指标", "当前值", "基线", "偏离", "级别", "判定规则", "异动类型"])
        w.writeheader()
        for r in alerts:
            w.writerow(r)
    files.append(csv_path)

    md = ["**AI 生成内容**", "", "## 预警清单", "",
          "| # | 指标 | 当前值 | 基线 | 偏离 | 级别 | 判定规则 |",
          "|---|---|---|---|---|---|---|"]
    for r in alerts:
        md.append(f"| {r['#']} | {r['指标']} | {r['当前值']} | {r['基线']} | {r['偏离']} | {r['级别']} | {r['判定规则']} |")
    md += ["", "## 未命中项", ""] + [f"{i}. {x}" for i, x in enumerate(no_alert, 1)]
    md += ["", "## 需人工确认", ""] + [f"{i}. {x}" for i, x in enumerate(need_confirm, 1)]
    md_path = os.path.join(outdir, "巡检报告.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    files.append(md_path)

    js_path = os.path.join(outdir, "patrol.json")
    with open(js_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "alerts": alerts, "no_alert": no_alert,
                   "need_confirm": need_confirm,
                   "note": "偏离率与级别由本脚本判定；跟价策略与动机解读由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(js_path)
    return files


def main():
    ap = argparse.ArgumentParser(description="竞品价格巡检（偏离率三级阈值 + 大促标记拦截）")
    ap.add_argument("--input", help="输入 JSON（metrics/baseline/rules）")
    ap.add_argument("--outdir", default=OUT_DEFAULT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = demo_data() if a.demo else (
        json.load(open(a.input, encoding="utf-8")) if a.input else ap.error("需要 --input 或 --demo"))

    alerts, no_alert, need_confirm, stats = patrol(payload)
    files = write_outputs(alerts, no_alert, need_confirm, stats, a.outdir)
    print(f"巡检完成 —— {stats['巡检 SKU 数']} 个 SKU：预警 {stats['预警条数']} 条"
          f"（高 {stats['高']} / 中 {stats['中']}），需人工确认 {stats['需人工确认条数']} 条")
    for f in files:
        print(" 产物:", f, f"({os.path.getsize(f) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
