"""
全球库存覆盖 — OECD 商业库存 + 浮仓代理 + 全球隐含库存变化

数据源（全部免费）：
  1. EIA STEO — OECD 商业石油库存月度估算
  2. 隐含库存变化 — 从全球 供给-需求 差值推算
  3. 浮仓代理 — 油轮运价时间序列 + VLCC 日费率代理
     （运价低+Contango大 → 浮仓经济性上升 → 浮仓增加）
  4. 战略储备(SPR) — 全球主要国家 SPR 水平

输出：data/global_inventory.json
"""
import json
import requests
from datetime import datetime, timedelta

from config import EIA_API_KEY, DATA_DIR
from eia_utils import fetch_steo_series


# ── EIA STEO 库存 series ─────────────────────────────
# 注意：EIA STEO v2 API 仅美国库存有分国别数据
# OECD 总量/欧洲/日本 在 STEO API 不可用，需从 STEO 报告手动获取
STEO_INVENTORY_SERIES = {
    "us_commercial_steo":    "STEO.PASC_US.M",   # 美国商业库存(月度, 百万桶)
}


# _fetch_steo 已移至 eia_utils.fetch_steo_series


def fetch_oecd_inventory() -> dict:
    """拉取 STEO 月度库存 + EIA 周度库存作为全球库存覆盖。"""
    if not EIA_API_KEY:
        print("  ⚠ EIA_API_KEY 未设置")
        return {}

    result = {}

    # 1) STEO 月度
    for key, sid in STEO_INVENTORY_SERIES.items():
        print(f"    STEO库存: {key} ...")
        try:
            data = fetch_steo_series(sid)
            result[key] = data
            if data:
                latest = data[-1]
                print(f"      → {len(data)} 月, 最新: {latest['date']} = {latest['value']:.1f} mb")
        except Exception as e:
            print(f"      ✗ 失败: {e}")
            result[key] = []

    # 2) 从 inventory.json 读取 EIA 周度库存（已由 fetch_eia.py 写入）
    inv_file = DATA_DIR / "inventory.json"
    try:
        with open(inv_file) as f:
            weekly_inv = json.load(f)
        for key in ["crude", "cushing", "gasoline", "distillate", "spr"]:
            data = weekly_inv.get(key, [])
            if data:
                result[f"us_{key}_weekly"] = data
                print(f"    EIA周度: {key} → {len(data)} 周, 最新: {data[-1]['date']}")
    except (FileNotFoundError, json.JSONDecodeError):
        print("    ⚠ inventory.json 不存在，跳过周度数据")

    return result


def _compute_implied_stockchange() -> list:
    """
    从全球供需平衡推算隐含库存变化。
    读取 global_balance.json 中的 balance 数据。
    """
    balance_file = DATA_DIR / "global_balance.json"
    try:
        with open(balance_file) as f:
            gb = json.load(f)
        balance = gb.get("balance", [])
        if not balance:
            return []

        # balance 正值=供给>需求=隐含累库，负值=去库
        return [
            {
                "date": b["date"],
                "stockchange_mbd": b["value"],
                "supply_mbd": b.get("supply", 0),
                "demand_mbd": b.get("demand", 0),
                "type": b.get("type", "actual"),
            }
            for b in balance[-24:]  # 最近2年
        ]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _analyze_floating_storage() -> dict:
    """
    浮仓经济性分析。
    条件：大 Contango + 低运费 → 浮仓经济性好 → 浮仓增加
    从 futures.json 读取曲线结构。
    """
    futures_file = DATA_DIR / "futures.json"
    try:
        with open(futures_file) as f:
            futures = json.load(f)

        m1_m6 = futures.get("spread_m1_m6")
        structure = futures.get("structure", "unknown")

        # 浮仓经济性判断
        # VLCC 日费率大约 $30,000-80,000
        # 储油成本 ≈ $0.50-1.00/桶/月 (含运费+保险)
        # 需要 Contango > ~$1/月 才有浮仓利润
        if m1_m6 is not None:
            contango_per_month = -m1_m6 / 5  # 5个月间距
            economics = "profitable" if contango_per_month > 1.0 else (
                "marginal" if contango_per_month > 0.3 else "unprofitable"
            )
        else:
            contango_per_month = None
            economics = "unknown"

        return {
            "structure": structure,
            "m1_m6_spread": m1_m6,
            "contango_per_month": round(contango_per_month, 2) if contango_per_month is not None else None,
            "floating_storage_economics": economics,
            "note": (
                "深度 Backwardation → 浮仓不经济 → 预计浮仓减少"
                if economics == "unprofitable" and structure == "backwardation"
                else "Contango 结构 → 浮仓可能增加"
                if economics == "profitable"
                else ""
            ),
        }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"status": "no_futures_data"}


def _analyze_inventory_deviation(oecd_data: dict) -> dict:
    """
    计算 OECD 库存相对 5 年均值的偏差。
    """
    oecd = oecd_data.get("us_commercial_steo", [])
    if len(oecd) < 60:
        return {}

    # 最近 60 个月 (5年)
    five_year = oecd[-60:]
    avg_5y = sum(d["value"] for d in five_year) / len(five_year)
    latest = oecd[-1]
    deviation = latest["value"] - avg_5y

    # 按月份计算季节性均值
    monthly_avg = {}
    for d in five_year:
        month = d["date"][-2:] if len(d["date"]) >= 7 else ""
        if month:
            monthly_avg.setdefault(month, []).append(d["value"])

    for m in monthly_avg:
        monthly_avg[m] = round(sum(monthly_avg[m]) / len(monthly_avg[m]), 1)

    latest_month = latest["date"][-2:] if len(latest["date"]) >= 7 else ""
    seasonal_avg = monthly_avg.get(latest_month, avg_5y)
    seasonal_deviation = latest["value"] - seasonal_avg

    return {
        "latest_date": latest["date"],
        "latest_value_mb": round(latest["value"], 1),
        "avg_5y_mb": round(avg_5y, 1),
        "deviation_mb": round(deviation, 1),
        "deviation_pct": round(deviation / avg_5y * 100, 1) if avg_5y > 0 else 0,
        "seasonal_avg_mb": round(seasonal_avg, 1),
        "seasonal_deviation_mb": round(seasonal_deviation, 1),
        "assessment": (
            "significantly_below" if deviation < -100 else
            "below" if deviation < -30 else
            "normal" if abs(deviation) <= 30 else
            "above" if deviation <= 100 else
            "significantly_above"
        ),
    }


def _fetch_spr_global() -> dict:
    """
    主要国家 SPR 水平估算。
    美国 SPR 从 EIA 周度数据获取（已在 inventory.json）。
    IEA 成员国 SPR 约束: 需持有 ≥ 90天进口量。
    """
    inv_file = DATA_DIR / "inventory.json"
    try:
        with open(inv_file) as f:
            inv = json.load(f)
        us_spr = inv.get("spr", [])
        us_spr_latest = us_spr[-1] if us_spr else {}
    except (FileNotFoundError, json.JSONDecodeError):
        us_spr_latest = {}

    # IEA 成员国 SPR 估算（基于公开数据，非实时）
    spr_estimates = {
        "us": {
            "name": "美国",
            "level_mb": round(us_spr_latest.get("value", 0) / 1000, 1) if us_spr_latest else 0,
            "date": us_spr_latest.get("date", ""),
            "max_release_kbd": 4400,
            "source": "EIA weekly",
        },
        "japan": {
            "name": "日本",
            "level_mb": 320,
            "date": "est.",
            "estimate_year": 2024,
            "note": "含国家储备+民间义务储备",
            "source": "IEA estimate",
        },
        "china": {
            "name": "中国",
            "level_mb": 950,
            "date": "est.",
            "estimate_year": 2024,
            "note": "中国不公布SPR具体数据，此为外部估算",
            "source": "industry estimate",
        },
        "europe_iea": {
            "name": "欧洲 IEA 成员",
            "level_mb": 500,
            "date": "est.",
            "estimate_year": 2024,
            "note": "IEA欧洲成员国合计",
            "source": "IEA estimate",
        },
    }

    total = sum(c["level_mb"] for c in spr_estimates.values())
    return {
        "by_country": spr_estimates,
        "total_estimated_mb": round(total, 0),
        "note": "除美国外均为行业估算值，非官方实时数据",
    }


def fetch_global_inventory() -> dict:
    """主入口：汇集全球库存数据。"""
    print("  [1] 全球库存数据 (STEO月度 + EIA周度)...")
    oecd = fetch_oecd_inventory()

    print("  [2] 隐含库存变化 (供需平衡)...")
    implied = _compute_implied_stockchange()
    if implied:
        latest = implied[-1]
        print(f"    → 最新: {latest['date']} "
              f"{'累库' if latest['stockchange_mbd'] > 0 else '去库'} "
              f"{abs(latest['stockchange_mbd']):.2f} mb/d")

    print("  [3] 浮仓经济性分析...")
    floating = _analyze_floating_storage()
    if floating.get("floating_storage_economics"):
        print(f"    → 浮仓: {floating['floating_storage_economics']}")

    print("  [4] 库存偏差分析...")
    deviation = _analyze_inventory_deviation(oecd)
    if deviation:
        print(f"    → US 商业库存: {deviation.get('assessment', '?')} "
              f"(偏差: {deviation.get('deviation_mb', '?')} mb)")

    print("  [5] 全球 SPR 估算...")
    spr = _fetch_spr_global()
    print(f"    → 全球 SPR 合计: ~{spr.get('total_estimated_mb', '?')} mb")

    return {
        "oecd_inventory": oecd,
        "implied_stockchange": implied,
        "floating_storage": floating,
        "oecd_deviation": deviation,
        "global_spr": spr,
        "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def save_global_inventory(data: dict):
    """保存全球库存数据。"""
    out_file = DATA_DIR / "global_inventory.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    n_oecd = sum(1 for v in data.get("oecd_inventory", {}).values() if v)
    print(f"  ✓ global_inventory.json (OECD: {n_oecd} 地区)")


if __name__ == "__main__":
    print("[全球石油库存]")
    if not EIA_API_KEY:
        print("⚠ EIA_API_KEY 未设置")
    else:
        data = fetch_global_inventory()
        save_global_inventory(data)
