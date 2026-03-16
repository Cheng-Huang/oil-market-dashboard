"""
从 IMF PortWatch 获取主要石油航运咽喉要道的每日通行数据，
以及通过 Yahoo Finance 获取油轮运价指标（股票代理）。

数据源：
  1. IMF PortWatch (ArcGIS) — 免费、无需 API Key
     - 霍尔木兹海峡 (全球 ~25% 海运石油)
     - 曼德海峡 / 苏伊士运河 (红海-地中海航线)
     - 马六甲海峡 (亚太原油进口主航道)
  2. Yahoo Finance — 油轮上市公司股价作为运价代理
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yfinance as yf

import config

# ── IMF PortWatch ArcGIS API ─────────────────────────
_ARCGIS_BASE = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG"
    "/arcgis/rest/services"
)
_DAILY_CP_URL = f"{_ARCGIS_BASE}/Daily_Chokepoints_Data/FeatureServer/0/query"

# 石油相关的关键咽喉要道
OIL_CHOKEPOINTS = {
    "chokepoint6": {
        "name": "霍尔木兹海峡",
        "name_en": "Strait of Hormuz",
        "oil_share": "~25% 全球海运石油",
    },
    "chokepoint4": {
        "name": "曼德海峡",
        "name_en": "Bab el-Mandeb",
        "oil_share": "~9% 全球海运石油",
    },
    "chokepoint1": {
        "name": "苏伊士运河",
        "name_en": "Suez Canal",
        "oil_share": "~12% 全球海运石油",
    },
    "chokepoint5": {
        "name": "马六甲海峡",
        "name_en": "Malacca Strait",
        "oil_share": "~28% 全球海运石油",
    },
}

# 油轮公司 — 股价作为运价代理
TANKER_TICKERS = {
    "FRO":  "Frontline (VLCC 原油)",
    "STNG": "Scorpio Tankers (成品油)",
    "INSW": "Intl Seaways (原油+成品油)",
    "DHT":  "DHT Holdings (VLCC 原油)",
}

DAYS_HISTORY = 180  # 获取半年历史


def _fetch_chokepoint_daily(chokepoint_id, days=DAYS_HISTORY):
    """获取单个咽喉要道的每日通行数据。"""
    try:
        r = requests.get(_DAILY_CP_URL, params={
            "where": f"portid='{chokepoint_id}'",
            "outFields": (
                "date,n_tanker,n_total,n_container,n_dry_bulk,"
                "capacity_tanker,capacity"
            ),
            "orderByFields": "date DESC",
            "resultRecordCount": days,
            "f": "json",
        }, timeout=30)
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])
        records = []
        for f in features:
            a = f["attributes"]
            ts = a.get("date")
            if ts is None:
                continue
            records.append({
                "date": datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d"),
                "n_tanker": a.get("n_tanker", 0) or 0,
                "n_total": a.get("n_total", 0) or 0,
                "n_container": a.get("n_container", 0) or 0,
                "n_dry_bulk": a.get("n_dry_bulk", 0) or 0,
                "capacity_tanker": a.get("capacity_tanker", 0) or 0,
                "capacity": a.get("capacity", 0) or 0,
            })
        # 按日期升序
        records.sort(key=lambda x: x["date"])
        return records
    except Exception as e:
        print(f"    ⚠ 获取 {chokepoint_id} 数据失败: {e}")
        return []


def _calc_rolling_avg(records, field, window=7):
    """计算滚动平均。"""
    values = [r[field] for r in records]
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start:i + 1]
        result.append(round(sum(chunk) / len(chunk), 1))
    return result


def _calc_stats(records, field):
    """计算统计信息。"""
    values = [r[field] for r in records if r[field] is not None]
    if not values:
        return {"avg": 0, "max": 0, "min": 0, "latest": 0}
    recent_7 = values[-7:] if len(values) >= 7 else values
    prev_7 = values[-14:-7] if len(values) >= 14 else values[:len(values)//2]
    avg_90 = sum(values[-90:]) / len(values[-90:]) if values else 0
    avg_recent = sum(recent_7) / len(recent_7) if recent_7 else 0
    avg_prev = sum(prev_7) / len(prev_7) if prev_7 else 0
    wow_change = ((avg_recent - avg_prev) / avg_prev * 100) if avg_prev else 0
    return {
        "avg_90d": round(avg_90, 1),
        "avg_7d": round(avg_recent, 1),
        "avg_prev_7d": round(avg_prev, 1),
        "wow_change": round(wow_change, 1),
        "max": max(values),
        "min": min(values),
        "latest": values[-1] if values else 0,
    }


def _fetch_tanker_stocks():
    """获取油轮公司股价作为运价代理。"""
    results = []
    for ticker, label in TANKER_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="6mo")
            if len(hist) == 0:
                continue
            last = float(hist["Close"].iloc[-1])
            prev_5d = float(hist["Close"].iloc[-5]) if len(hist) >= 5 else last
            prev_1m = float(hist["Close"].iloc[-22]) if len(hist) >= 22 else last
            first = float(hist["Close"].iloc[0])
            results.append({
                "ticker": ticker,
                "label": label,
                "price": round(last, 2),
                "change_5d": round((last - prev_5d) / prev_5d * 100, 1),
                "change_1m": round((last - prev_1m) / prev_1m * 100, 1),
                "change_6m": round((last - first) / first * 100, 1),
                "history": [
                    {
                        "date": d.strftime("%Y-%m-%d"),
                        "close": round(float(c), 2),
                    }
                    for d, c in zip(hist.index, hist["Close"])
                ][::5],  # 每5天采样
            })
        except Exception as e:
            print(f"    ⚠ 获取 {ticker} 失败: {e}")
    return results


def fetch_maritime_data():
    """获取所有航运数据。"""
    chokepoints = {}
    for cp_id, cp_info in OIL_CHOKEPOINTS.items():
        print(f"  ↳ {cp_info['name']} ({cp_info['name_en']})...")
        records = _fetch_chokepoint_daily(cp_id)
        if not records:
            continue

        tanker_7d_avg = _calc_rolling_avg(records, "n_tanker", 7)
        total_7d_avg = _calc_rolling_avg(records, "n_total", 7)

        # 用于图表的时间序列（7日滚动平均）
        chart_data = []
        for i, rec in enumerate(records):
            chart_data.append({
                "date": rec["date"],
                "tanker": rec["n_tanker"],
                "tanker_7d": tanker_7d_avg[i],
                "total": rec["n_total"],
                "total_7d": total_7d_avg[i],
                "capacity_tanker": rec["capacity_tanker"],
            })

        chokepoints[cp_id] = {
            **cp_info,
            "tanker_stats": _calc_stats(records, "n_tanker"),
            "total_stats": _calc_stats(records, "n_total"),
            "chart_data": chart_data,
            "data_range": {
                "start": records[0]["date"],
                "end": records[-1]["date"],
                "days": len(records),
            },
        }

    print("  ↳ 油轮运价指标 (股票代理)...")
    tanker_stocks = _fetch_tanker_stocks()

    # 生成封锁风险评估
    hormuz = chokepoints.get("chokepoint6", {})
    mandeb = chokepoints.get("chokepoint4", {})
    risk_signals = _assess_risk(hormuz, mandeb)

    return {
        "chokepoints": chokepoints,
        "tanker_stocks": tanker_stocks,
        "risk_signals": risk_signals,
        "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _assess_risk(hormuz, mandeb):
    """基于通行量变化评估封锁风险信号。"""
    signals = []

    for cp_data, name in [(hormuz, "霍尔木兹"), (mandeb, "曼德海峡")]:
        if not cp_data:
            continue
        ts = cp_data.get("tanker_stats", {})
        wow = ts.get("wow_change", 0)
        avg_7d = ts.get("avg_7d", 0)
        avg_90d = ts.get("avg_90d", 0)

        # 油轮通行量周环比大幅下降
        if wow < -30:
            signals.append({
                "level": "danger",
                "message": f"⚠️ {name}油轮通行量骤降 {wow:.0f}% (7日均值 {avg_7d:.0f} vs 前周 {ts.get('avg_prev_7d', 0):.0f})",
            })
        elif wow < -15:
            signals.append({
                "level": "warning",
                "message": f"⚡ {name}油轮通行量下降 {wow:.0f}% (7日均值 {avg_7d:.0f} vs 前周 {ts.get('avg_prev_7d', 0):.0f})",
            })

        # 7日均值低于90日均值的70%
        if avg_90d > 0 and avg_7d < avg_90d * 0.7:
            pct = (avg_7d / avg_90d - 1) * 100
            signals.append({
                "level": "danger",
                "message": f"🚨 {name}油轮通行量显著低于常态 (7日均: {avg_7d:.0f}, 90日均: {avg_90d:.0f}, {pct:.0f}%)",
            })

    if not signals:
        signals.append({
            "level": "normal",
            "message": "✅ 主要石油航运要道通行正常",
        })

    return signals


def save_maritime_data(data):
    out_file = config.DATA_DIR / "maritime.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    n_cp = len(data["chokepoints"])
    n_stocks = len(data["tanker_stocks"])
    print(f"  ✓ maritime.json ({n_cp} 航运要道, {n_stocks} 油轮指标)")


if __name__ == "__main__":
    print("[航运数据]")
    data = fetch_maritime_data()
    save_maritime_data(data)

    # 打印风险信号
    print("\n[风险评估]")
    for sig in data["risk_signals"]:
        print(f"  {sig['message']}")

    # 打印统计摘要
    print("\n[通行统计]")
    for cp_id, cp in data["chokepoints"].items():
        ts = cp["tanker_stats"]
        print(f"  {cp['name']}: 油轮 7日均 {ts['avg_7d']}/天, "
              f"90日均 {ts['avg_90d']}/天, 周环比 {ts['wow_change']:+.1f}%")

    if data["tanker_stocks"]:
        print("\n[油轮运价指标]")
        for s in data["tanker_stocks"]:
            print(f"  {s['ticker']} ({s['label']}): ${s['price']:.2f} "
                  f"({s['change_5d']:+.1f}% 5日, {s['change_1m']:+.1f}% 月)")
