# -*- coding: utf-8 -*-
"""
竞品价格巡检工作流 —— 端到端编排脚本（与 SKILL.md 的 DAG 一致）。

流程：
  S1 快照结构化   把当日竞品采集快照整理成结构化数据（item/price/promo/baseline）
  S2 竞品价格巡检 偏离率 + 三级阈值判定 + 大促标记拦截（对应原子技能 competitor-price-patrol）
  S3 异动提醒     生成可推送的提醒清单（含建议处置窗口）

本脚本承担 S1-S3 的确定性部分：快照解析、偏离率计算、阈值判定、提醒落盘。
竞品降价动机解读、跟价策略措辞，由模型按 prompt.txt 完成。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/step1_快照.json / out/step2_巡检.json   各步中间产物（每步读上一步产物）
  out/预警清单.csv / out/异动提醒.md          最终交付物
  out/flow_result.json                        机器可读汇总
"""
from __future__ import annotations

import argparse
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(HERE), "out"))

RULES = {"drop_high": -8.0, "drop_mid": -5.0, "raise_mid": 8.0,
         "promo_keywords": ["百亿补贴", "限时直降", "秒杀", "大促"]}


def demo_data():
    """来自 runs_v2 实跑输入（2026-10-08 每日巡检定时任务，3 个监控链接）。"""
    return {
        "date": "2026-10-08",
        "shop": "云澜家居专营店",
        "items": [
            {"item": "竞品A 316不锈钢保温杯500ml", "price": 69.9, "promo": "限时直降", "avg7": 82.5},
            {"item": "竞品B 玻璃双层水杯450ml", "price": 35.0, "promo": "", "avg7": 34.8},
            {"item": "竞品C 陶瓷马克杯380ml", "price": 25.9, "promo": "百亿补贴", "avg7": 29.9},
        ],
    }


def step1_structure(payload, outdir):
    """S1 快照结构化：解析输入 → 结构化快照。"""
    items = []
    for it in payload.get("items") or []:
        if it.get("price") is None:
            continue
        items.append({"item": it["item"], "price": float(it["price"]),
                      "promo": it.get("promo") or "",
                      "avg7": float(it["avg7"]) if it.get("avg7") is not None else None})
    if not items:
        raise SystemExit("[错误] 输入中没有任何带价格的竞品条目：缺失清单让用户补齐，不估算")
    snapshot = {"date": payload.get("date", ""), "shop": payload.get("shop", ""),
                "count": len(items), "items": items}
    path = os.path.join(outdir, "step1_快照.json")
    json.dump(snapshot, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return snapshot, path


def step2_patrol(snapshot, outdir):
    """S2 竞品价格巡检：读 S1 产物，算偏离率并三级判定。"""
    items = json.load(open(os.path.join(outdir, "step1_快照.json"), encoding="utf-8"))["items"]
    alerts, no_alert, need_confirm = [], [], []
    for it in items:
        if it["avg7"] is None:
            need_confirm.append(f"{it['item']}：无 7 日均价基线，无法计算偏离")
            continue
        dev = (it["price"] - it["avg7"]) / it["avg7"] * 100
        promo = it["promo"]
        if dev <= RULES["drop_high"]:
            level, rule = "高", "下浮 ≥ 8% 判降价异动"
        elif dev <= RULES["drop_mid"]:
            level, rule = "中", "下浮 5%~8% 判关注"
        elif dev >= RULES["raise_mid"]:
            level, rule = "中", "上浮 ≥ 8% 判涨价异动"
        else:
            no_alert.append(f"{it['item']}：偏离 {dev:+.1f}%（±5% 以内，正常）")
            continue
        row = {"item": it["item"], "price": it["price"], "avg7": it["avg7"],
               "dev": round(dev, 1), "level": level, "rule": rule, "promo": promo}
        alerts.append(row)
        if any(k in promo for k in RULES["promo_keywords"]):
            need_confirm.append(f"{it['item']}：命中大促标记「{promo}」，人工确认后再决定跟价")
    result = {"alert_count": len(alerts), "alerts": alerts, "no_alert": no_alert,
              "need_confirm": need_confirm}
    path = os.path.join(outdir, "step2_巡检.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def step3_notify(step2, payload, outdir):
    """S3 异动提醒：读 S2 产物，生成提醒清单与最终交付物。"""
    alerts = json.load(open(os.path.join(outdir, "step2_巡检.json"), encoding="utf-8"))["alerts"]
    lines = ["**AI 生成内容**", "",
             f"# 竞品价格异动提醒（{payload.get('date', '')} · {payload.get('shop', '')}）", "",
             "| # | 竞品 SKU | 到手价 | 7日均价 | 偏离 | 级别 | 判定规则 |",
             "|---|---|---|---|---|---|---|"]
    for i, a in enumerate(alerts, 1):
        lines.append(f"| {i} | {a['item']} | {a['price']} 元 | {a['avg7']} 元 "
                     f"| {a['dev']:+.1f}% | {a['level']} | {a['rule']} |")
    lines += ["", "## 建议处置", ""]
    for i, a in enumerate(alerts, 1):
        window = "2 小时内核价" if a["level"] == "高" else "今日复盘"
        lines.append(f"{i}. {a['item']}：偏离 {a['dev']:+.1f}%，{window}，"
                     f"确认是活动价还是调价后再决定跟价")
    md_path = os.path.join(outdir, "异动提醒.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    csv_path = os.path.join(outdir, "预警清单.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["#", "竞品SKU", "到手价", "7日均价", "偏离%", "级别", "判定规则", "促销标记"])
        for i, a in enumerate(alerts, 1):
            w.writerow([i, a["item"], a["price"], a["avg7"], f"{a['dev']:+.1f}",
                        a["level"], a["rule"], a["promo"]])
    return [md_path, csv_path]


def main():
    ap = argparse.ArgumentParser(description="竞品价格巡检工作流（快照→巡检→提醒）")
    ap.add_argument("--input", help="输入 JSON")
    ap.add_argument("--outdir", default=OUT_DEFAULT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = demo_data() if a.demo else (
        json.load(open(a.input, encoding="utf-8")) if a.input else ap.error("需要 --input 或 --demo"))
    os.makedirs(a.outdir, exist_ok=True)

    s1, p1 = step1_structure(payload, a.outdir)
    s2, p2 = step2_patrol(s1, a.outdir)
    files = step3_notify(s2, payload, a.outdir)

    result_path = os.path.join(a.outdir, "flow_result.json")
    json.dump({"flow": "competitor-price-patrol-flow", "steps": [p1, p2] + files,
               "summary": f"巡检 {s1['count']} 个 SKU，异动 {s2['alert_count']} 条",
               "note": "数值由本脚本判定；动机解读与跟价策略由模型按 prompt.txt 完成"},
              open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"工作流完成 —— 巡检 {s1['count']} 个 SKU，异动 {s2['alert_count']} 条，"
          f"需人工确认 {len(s2['need_confirm'])} 条")
    for f in [p1, p2] + files + [result_path]:
        print(" 产物:", f)


if __name__ == "__main__":
    main()
