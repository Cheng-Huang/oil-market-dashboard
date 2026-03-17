"""
OPEC 实时产量监控 — 接入 EIA STEO 分国别产量 + OPEC MOMR 代理

数据源（全部免费）：
  1. EIA STEO — OPEC 各成员国月度产量预测
     - 沙特、伊朗、伊拉克、阿联酋、科威特、委内瑞拉 等
     - OPEC+ 减产执行情况可从实际 vs 配额推算
  2. JODI — 生产国自报产量（月度，滞后约2月）
  3. 油轮跟踪代理 — 出口国附近油轮活动作为产量近似

输出：data/opec_production.json
"""
import json
import requests
from datetime import datetime, timedelta

from config import EIA_API_KEY, DATA_DIR


# ── EIA STEO 全球/地区级产量 ─────────────────────────
STEO_PRODUCTION_SERIES = {
    "opec_total":       "STEO.PAPR_OPEC.M",          # OPEC 总产量
    "non_opec_total":   "STEO.PAPR_NONOPEC.M",       # 非OPEC总量
    "us_production":    "STEO.PAPR_US.M",             # 美国产量（月度）
    "world_total":      "STEO.PAPR_WORLD.M",          # 全球总产量
}

# ── EIA International — 分国别产量（月度, 千桶/天）──
# 使用 INTL.57-1-{ISO3}-TBPD.M (productId=57=crude, activityId=1=production)
EIA_INTL_PRODUCTION = {
    # OPEC 核心
    "saudi":      {"code": "SAU", "name": "沙特"},
    "iran":       {"code": "IRN", "name": "伊朗"},
    "iraq":       {"code": "IRQ", "name": "伊拉克"},
    "uae":        {"code": "ARE", "name": "阿联酋"},
    "kuwait":     {"code": "KWT", "name": "科威特"},
    "venezuela":  {"code": "VEN", "name": "委内瑞拉"},
    "nigeria":    {"code": "NGA", "name": "尼日利亚"},
    "libya":      {"code": "LBY", "name": "利比亚"},
    "algeria":    {"code": "DZA", "name": "阿尔及利亚"},
    "angola":     {"code": "AGO", "name": "安哥拉"},
    # 非 OPEC 关键
    "russia":     {"code": "RUS", "name": "俄罗斯"},
    "canada":     {"code": "CAN", "name": "加拿大"},
    "brazil":     {"code": "BRA", "name": "巴西"},
    "norway":     {"code": "NOR", "name": "挪威"},
    "mexico":     {"code": "MEX", "name": "墨西哥"},
    "china":      {"code": "CHN", "name": "中国"},
}

# OPEC+ 减产基准（2024 年参考产量配额，百万桶/日）
# 来源: OPEC+ 第37次部长级会议 (2024年6月)
OPEC_PLUS_QUOTAS = {
    "saudi":      9.0,    # 自愿额外减产后的目标
    "iraq":       4.0,
    "uae":        2.9,
    "kuwait":     2.4,
    "algeria":    0.9,
    "nigeria":    1.4,
    "russia":     9.0,    # 自愿削减后目标
}


def _fetch_steo(series_id: str, days_back: int = 1825) -> list[dict]:
    """拉取单个 EIA STEO series"""
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    url = f"https://api.eia.gov/v2/seriesid/{series_id}"
    params = {"api_key": EIA_API_KEY, "start": start}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("response", {}).get("data", [])
    result = []
    for item in data:
        period = item.get("period", "")
        value = item.get("value")
        if value is not None:
            try:
                result.append({"date": period, "value": float(value)})
            except (ValueError, TypeError):
                pass
    result.sort(key=lambda x: x["date"])
    return result


def fetch_opec_production() -> dict:
    """拉取 OPEC 及关键产油国月度产量。"""
    if not EIA_API_KEY:
        print("  ⚠ EIA_API_KEY 未设置")
        return {}

    result = {}

    # 1) STEO 地区级总量
    for key, sid in STEO_PRODUCTION_SERIES.items():
        print(f"    STEO产量: {key} ...")
        try:
            data = _fetch_steo(sid)
            result[key] = data
            if data:
                latest = data[-1]
                print(f"      → {len(data)} 月, 最新: {latest['date']} = {latest['value']:.2f} mb/d")
        except Exception as e:
            print(f"      ✗ 失败: {e}")
            result[key] = []

    # 2) EIA International 分国别产量
    for key, info in EIA_INTL_PRODUCTION.items():
        code = info["code"]
        name = info["name"]
        sid = f"INTL.57-1-{code}-TBPD.M"
        print(f"    EIA国际: {name} ({code}) ...")
        try:
            sid = f"INTL.57-1-{code}-TBPD.M"
            url = f"https://api.eia.gov/v2/seriesid/{sid}"
            params = {
                "api_key": EIA_API_KEY,
                "start": (datetime.now() - timedelta(days=1825)).strftime("%Y-%m-%d"),
            }
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            api_data = resp.json().get("response", {}).get("data", [])

            records = []
            for item in api_data:
                period = item.get("period", "")
                value = item.get("value")
                if value is not None:
                    try:
                        # EIA International 单位是 千桶/天 (TBPD)，转换为 百万桶/天
                        records.append({"date": period, "value": round(float(value) / 1000, 3)})
                    except (ValueError, TypeError):
                        pass
            records.sort(key=lambda x: x["date"])
            result[key] = records
            if records:
                latest = records[-1]
                print(f"      → {len(records)} 月, 最新: {latest['date']} = {latest['value']:.3f} mb/d")
        except Exception as e:
            print(f"      ✗ 失败: {e}")
            result[key] = []

    return result


def _compute_quota_compliance(production_data: dict) -> dict:
    """
    计算 OPEC+ 减产执行率。
    执行率 = (配额 - 实际产量) / 配额 × 100
    正值 = 超额减产，负值 = 超产
    """
    compliance = {}

    for country, quota in OPEC_PLUS_QUOTAS.items():
        prod = production_data.get(country, [])
        if not prod:
            continue

        latest = prod[-1]
        actual = latest["value"]
        deviation = actual - quota
        compliance_pct = (quota - actual) / quota * 100 if quota > 0 else 0

        compliance[country] = {
            "quota_mbd": quota,
            "actual_mbd": round(actual, 2),
            "deviation_mbd": round(deviation, 2),
            "compliance_pct": round(compliance_pct, 1),
            "date": latest["date"],
            "status": (
                "over_cut" if deviation < -0.1 else
                "under_cut" if deviation > 0.1 else
                "compliant"
            ),
        }

    # 汇总
    total_quota = sum(OPEC_PLUS_QUOTAS.values())
    total_actual = sum(c["actual_mbd"] for c in compliance.values())
    overall = {
        "total_quota_mbd": total_quota,
        "total_actual_mbd": round(total_actual, 2),
        "total_deviation_mbd": round(total_actual - total_quota, 2),
        "overall_compliance_pct": round(
            (total_quota - total_actual) / total_quota * 100, 1
        ) if total_quota > 0 else 0,
    }

    return {"by_country": compliance, "overall": overall}


def _compute_production_trends(production_data: dict) -> list:
    """分析各国产量月环比趋势，标记异常变化。"""
    trends = []

    for key, data in production_data.items():
        if len(data) < 3 or key in ("opec_total", "non_opec_total", "world_total"):
            continue

        latest = data[-1]
        prev = data[-2]
        prev3 = data[-3]

        mom = latest["value"] - prev["value"]
        mom_pct = (mom / prev["value"] * 100) if prev["value"] > 0 else 0
        q_change = latest["value"] - prev3["value"]

        trend = {
            "country": key,
            "date": latest["date"],
            "value_mbd": round(latest["value"], 2),
            "mom_change_mbd": round(mom, 3),
            "mom_change_pct": round(mom_pct, 1),
            "3m_change_mbd": round(q_change, 3),
        }

        # 标记异常
        if abs(mom_pct) > 10 or abs(mom) > 0.5:
            trend["anomaly"] = True
            trend["note"] = (
                f"产量{'骤降' if mom < 0 else '骤增'} "
                f"{abs(mom):.2f} mb/d ({mom_pct:+.1f}%)"
            )

        trends.append(trend)

    # 按绝对变化排序
    trends.sort(key=lambda x: abs(x["mom_change_mbd"]), reverse=True)
    return trends


def _compute_spare_capacity(production_data: dict) -> dict:
    """
    估算 OPEC 闲置产能（简化版）。
    闲置产能 ≈ 峰值产能 - 当前产量
    使用近5年最大值作为产能估算。
    """
    capacity_estimates = {}
    for key, data in production_data.items():
        if key in ("opec_total", "non_opec_total", "world_total",
                    "us_production", "canada", "brazil"):
            continue
        if len(data) < 12:
            continue

        peak = max(d["value"] for d in data[-60:]) if len(data) >= 60 else max(d["value"] for d in data)
        latest = data[-1]["value"]
        spare = peak - latest

        if spare > 0.05:  # 仅记录有意义的闲置产能
            capacity_estimates[key] = {
                "current_mbd": round(latest, 2),
                "estimated_peak_mbd": round(peak, 2),
                "spare_capacity_mbd": round(spare, 2),
                "date": data[-1]["date"],
            }

    total_spare = sum(c["spare_capacity_mbd"] for c in capacity_estimates.values())
    return {
        "by_country": capacity_estimates,
        "total_spare_mbd": round(total_spare, 2),
    }


def fetch_all_opec_data() -> dict:
    """主入口：获取完整 OPEC 产量数据包。"""
    print("  [1] EIA STEO 分国别产量...")
    production = fetch_opec_production()

    print("  [2] OPEC+ 减产执行率...")
    compliance = _compute_quota_compliance(production)
    overall = compliance.get("overall", {})
    if overall:
        dev = overall.get("total_deviation_mbd", 0)
        pct = overall.get("overall_compliance_pct", 0)
        print(f"    → 偏差: {dev:+.2f} mb/d, 执行率: {pct:.1f}%")

    print("  [3] 产量趋势分析...")
    trends = _compute_production_trends(production)
    anomalies = [t for t in trends if t.get("anomaly")]
    if anomalies:
        print(f"    → {len(anomalies)} 个异常:")
        for a in anomalies[:5]:
            print(f"      {a['country']}: {a['note']}")

    print("  [4] 闲置产能估算...")
    spare = _compute_spare_capacity(production)
    print(f"    → 总闲置产能: {spare['total_spare_mbd']:.2f} mb/d")

    return {
        "production_by_country": production,
        "quota_compliance": compliance,
        "production_trends": trends,
        "spare_capacity": spare,
        "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def save_opec_production(data: dict):
    """保存 OPEC 产量数据。"""
    out_file = DATA_DIR / "opec_production.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    n_countries = sum(1 for v in data.get("production_by_country", {}).values() if v)
    spare = data.get("spare_capacity", {}).get("total_spare_mbd", "?")
    print(f"  ✓ opec_production.json ({n_countries} 国家/地区, 闲置产能: {spare} mb/d)")


if __name__ == "__main__":
    print("[OPEC 产量监控]")
    if not EIA_API_KEY:
        print("⚠ EIA_API_KEY 未设置")
    else:
        data = fetch_all_opec_data()
        save_opec_production(data)
