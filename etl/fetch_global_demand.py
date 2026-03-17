"""
全球石油需求覆盖 — 弥补"仅有美国 EIA 数据"的最大盲区

数据源（全部免费）：
  1. EIA STEO — 主要国家/地区月度消费预测（已有全球总量，新增分国别）
     - 中国、印度、日本、韩国、欧洲 等
  2. JODI (Joint Organisations Data Initiative) — 全球70+国家月度石油数据
     - https://www.jodidata.org/ 通过 UN COMTRADE/JODI API 获取
  3. EIA International — 年度/季度各国需求数据
  4. 中国炼厂开工率代理 — 新加坡裂解价差(Yahoo Finance)作为亚太需求温度计

输出：data/global_demand.json
"""
import json
import requests
from datetime import datetime, timedelta

import yfinance as yf

from config import EIA_API_KEY, DATA_DIR


# ── EIA STEO 分地区消费 series ──────────────────────
# STEO 有分地区/国别消费预测（月度，单位：百万桶/日）
STEO_DEMAND_SERIES = {
    # 主要消费国/地区
    "us_consumption":      "STEO.PATC_US.M",       # 美国液体燃料消费
    "oecd_europe_consumption": "STEO.PATC_OECD_EUROPE.M",  # OECD欧洲消费
    "non_oecd_consumption": "STEO.PATC_NON_OECD.M",  # 非OECD消费
    "oecd_consumption":     "STEO.PATC_OECD.M",      # OECD消费
    "world_consumption":    "STEO.PATC_WORLD.M",     # 全球消费（已有，重复拉取作对照）
}

# ── EIA International — 主要国家原油产量（月度，千桶/天）──
# 注意：EIA International 仅有 production(activityId=1) 数据，
# 不提供中国/印度等非OECD国家的月度消费或进口数据。
# 用产量变化作为供需间接指标：产量骤降→可能因外部冲击减产。
EIA_INTL_PRODUCTION_COUNTRIES = {
    "china_production":  {"country": "CHN", "name": "中国"},
    "india_production":  {"country": "IND", "name": "印度"},
    "japan_production":  {"country": "JPN", "name": "日本"},
    "korea_production":  {"country": "KOR", "name": "韩国"},
    "brazil_production": {"country": "BRA", "name": "巴西"},
}

# ── JODI Oil World Database API ─────────────────────
# JODI 数据通过 UN Data API 或直接 CSV 下载
JODI_API_BASE = "https://data.un.org/ws/rest/data/JODI,DF_WORLD_OILDATA,1.0"

# 关键国家 ISO3 代码 → 中国/印度/韩国/日本/巴西
JODI_KEY_COUNTRIES = {
    "CHN": "中国",
    "IND": "印度",
    "JPN": "日本",
    "KOR": "韩国",
    "BRA": "巴西",
    "SAU": "沙特",
    "ARE": "阿联酋",
    "DEU": "德国",
}

# ── 亚太裂解价差（新加坡）— 作为亚太需求代理 ──────
ASIA_DEMAND_PROXIES = {
    # 新加坡裂解价差代理：使用 PBF Energy (East Coast refiner) + Marathon 对比
    # 另一个代理: 亚太航运相关 ETF
    "APTS":  "Asia Pacific tanker (ProShares Ultra Bloomberg Crude Oil ETF 替代)",
}


def _fetch_steo_series(series_id: str, days_back: int = 1825) -> list[dict]:
    """拉取单个 EIA STEO series"""
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    url = f"https://api.eia.gov/v2/seriesid/{series_id}"
    params = {
        "api_key": EIA_API_KEY,
        "start": start,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    response_data = data.get("response", {}).get("data", [])

    result = []
    for item in response_data:
        period = item.get("period", "")
        value = item.get("value")
        if value is not None:
            try:
                result.append({"date": period, "value": float(value)})
            except (ValueError, TypeError):
                pass
    result.sort(key=lambda x: x["date"])
    return result


def fetch_steo_demand_by_country() -> dict:
    """拉取 EIA STEO 分国别/地区消费数据。"""
    if not EIA_API_KEY:
        print("  ⚠ EIA_API_KEY 未设置")
        return {}

    result = {}
    for key, sid in STEO_DEMAND_SERIES.items():
        print(f"    STEO需求: {key} ...")
        try:
            data = _fetch_steo_series(sid)
            result[key] = data
            if data:
                latest = data[-1]
                print(f"      → {len(data)} 月, 最新: {latest['date']} = {latest['value']:.2f} mb/d")
            else:
                print(f"      → 0 条记录")
        except Exception as e:
            print(f"      ✗ 失败: {e}")
            result[key] = []

    return result


def fetch_eia_intl_production() -> dict:
    """
    拉取 EIA International 主要国家原油产量（月度, 千桶/天）。
    EIA International 仅提供 production 数据，不提供非OECD国家消费/进口。
    产量变化可作为供需间接指标。
    """
    if not EIA_API_KEY:
        return {}

    result = {}
    for key, info in EIA_INTL_PRODUCTION_COUNTRIES.items():
        country = info["country"]
        name = info["name"]
        print(f"    EIA国际: {name} ({country}) 原油产量...")
        try:
            # EIA International: INTL.{product}-{activity}-{country}-TBPD.M
            # productId=57(crude), activityId=1(production)
            sid = f"INTL.57-1-{country}-TBPD.M"
            url = f"https://api.eia.gov/v2/seriesid/{sid}"
            params = {
                "api_key": EIA_API_KEY,
                "start": (datetime.now() - timedelta(days=1825)).strftime("%Y-%m-%d"),
            }
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json().get("response", {}).get("data", [])

            records = []
            for item in data:
                period = item.get("period", "")
                value = item.get("value")
                if value is not None:
                    try:
                        records.append({"date": period, "value": float(value)})
                    except (ValueError, TypeError):
                        pass
            records.sort(key=lambda x: x["date"])
            result[key] = records
            if records:
                latest = records[-1]
                print(f"      → {len(records)} 月, 最新: {latest['date']} = {latest['value']:.0f} kb/d")
            else:
                print(f"      → 0 条记录")
        except Exception as e:
            print(f"      ✗ 失败: {e}")
            result[key] = []

    return result


def fetch_jodi_demand_data() -> dict:
    """
    尝试从 JODI 获取分国别石油需求数据。
    JODI 通过 SDMX REST API 提供数据。
    Flow=TOTDEM (Total Demand), Product=CRUDEOIL
    """
    result = {"status": "unavailable", "countries": {}}

    # JODI SDMX query for total oil demand, recent data
    # Format: .{COUNTRY}.TOTDEM.CRUDEOIL.KTOE.M
    try:
        # Try a smaller query first — latest 12 months for key countries
        countries = "+".join(JODI_KEY_COUNTRIES.keys())
        url = (
            f"{JODI_API_BASE}/"
            f"{countries}.TOTDEM.CR+CRUDE.KBBL.M"
        )
        headers = {"Accept": "application/json"}
        params = {"lastNObservations": 12, "detail": "dataonly"}
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            # Parse SDMX-JSON response
            datasets = data.get("dataSets", [{}])
            if datasets:
                result["status"] = "available"
                # Extract series from SDMX structure
                series = datasets[0].get("series", {})
                dimensions = data.get("structure", {}).get("dimensions", {}).get("series", [])
                time_dims = data.get("structure", {}).get("dimensions", {}).get("observation", [])

                # Map dimension values
                country_dim = None
                for dim in dimensions:
                    if dim.get("id") == "REF_AREA":
                        country_dim = {str(i): v["id"] for i, v in enumerate(dim.get("values", []))}

                time_values = []
                for dim in time_dims:
                    if dim.get("id") == "TIME_PERIOD":
                        time_values = [v["id"] for v in dim.get("values", [])]

                for series_key, series_data in series.items():
                    key_parts = series_key.split(":")
                    country_idx = key_parts[0] if key_parts else "0"
                    country_code = country_dim.get(country_idx, "UNK") if country_dim else "UNK"
                    country_name = JODI_KEY_COUNTRIES.get(country_code, country_code)

                    obs = series_data.get("observations", {})
                    records = []
                    for time_idx, values in obs.items():
                        time_period = time_values[int(time_idx)] if int(time_idx) < len(time_values) else "?"
                        if values and values[0] is not None:
                            records.append({
                                "date": time_period,
                                "value": round(float(values[0]), 1),
                            })
                    records.sort(key=lambda x: x["date"])
                    if records:
                        result["countries"][country_code] = {
                            "name": country_name,
                            "unit": "千桶",
                            "data": records,
                            "latest": records[-1],
                        }

                print(f"    → JODI: {len(result['countries'])} 个国家有数据")
            else:
                result["status"] = "empty"
                print(f"    → JODI: 返回空数据集")
        else:
            result["status"] = f"http_{resp.status_code}"
            print(f"    → JODI: HTTP {resp.status_code}")

    except Exception as e:
        result["status"] = f"error"
        result["error"] = str(e)
        print(f"    → JODI: {e}")

    return result


def fetch_asia_demand_proxy() -> dict:
    """
    用新加坡裂解价差和亚太航运指标作为亚太实际需求的高频代理。
    逻辑：炼厂开工率与裂解价差正相关 → 裂解高=需求好。
    """
    result = {}

    # 抓取新加坡柴油裂解价差代理（使用 Marathon Petroleum 作美国代理参考）
    proxies = {
        "MPC": "Marathon Petroleum (US refiner)",
        "VLO": "Valero Energy (US refiner)",
        "PSX": "Phillips 66 (US refiner)",
    }

    tickers = list(proxies.keys())
    try:
        df = yf.download(tickers, period="90d", progress=False, group_by="ticker")
        if df.empty:
            return result

        for tk, label in proxies.items():
            try:
                close = df[(tk, "Close")].dropna()
                if close.empty:
                    continue
                latest = float(close.iloc[-1])
                prev_20d = float(close.iloc[-20]) if len(close) >= 20 else latest
                result[tk] = {
                    "name": label,
                    "price": round(latest, 2),
                    "change_20d_pct": round((latest - prev_20d) / prev_20d * 100, 1),
                }
            except Exception:
                pass
    except Exception as e:
        print(f"    ⚠ 炼厂代理获取失败: {e}")

    return result


def _compute_demand_share(steo_data: dict) -> dict:
    """计算各国/地区占全球需求的份额（最新月份）。"""
    world = steo_data.get("world_consumption", [])
    if not world:
        return {}

    latest_date = world[-1]["date"]
    world_val = world[-1]["value"]

    shares = {}
    for key, data in steo_data.items():
        if key == "world_consumption" or not data:
            continue
        # 找到同月数据
        matching = [d for d in data if d["date"] == latest_date]
        if matching:
            val = matching[0]["value"]
            shares[key.replace("_consumption", "")] = {
                "value_mbd": round(val, 2),
                "share_pct": round(val / world_val * 100, 1) if world_val > 0 else 0,
            }

    return {
        "date": latest_date,
        "world_total_mbd": round(world_val, 2),
        "shares": shares,
    }


def _detect_demand_anomalies(steo_data: dict) -> list:
    """检测需求异常变化（月环比大幅偏离）。"""
    anomalies = []
    for key, data in steo_data.items():
        if len(data) < 3:
            continue
        # 最近3个月
        recent = data[-3:]
        prev = data[-4] if len(data) >= 4 else None
        if prev is None:
            continue

        latest = recent[-1]
        mom_change = latest["value"] - prev["value"]
        mom_pct = (mom_change / prev["value"] * 100) if prev["value"] > 0 else 0

        # 月环比变化超过5%或绝对值超2百万桶/日 → 标记
        if abs(mom_pct) > 5 or abs(mom_change) > 2:
            anomalies.append({
                "region": key,
                "date": latest["date"],
                "value": latest["value"],
                "prev_value": prev["value"],
                "change_mbd": round(mom_change, 2),
                "change_pct": round(mom_pct, 1),
            })

    return anomalies


def fetch_global_demand() -> dict:
    """主入口：汇集所有全球需求数据源。"""
    print("  [1] EIA STEO 分地区需求...")
    steo_demand = fetch_steo_demand_by_country()

    print("  [2] EIA 国际产量 (中国/印度/日本/韩国/巴西)...")
    intl_production = fetch_eia_intl_production()

    print("  [3] JODI 国际石油需求...")
    jodi_data = fetch_jodi_demand_data()

    print("  [4] 炼厂/需求代理指标...")
    asia_proxy = fetch_asia_demand_proxy()

    # 计算需求份额
    demand_share = _compute_demand_share(steo_demand)

    # 检测异常
    anomalies = _detect_demand_anomalies(steo_demand)
    if anomalies:
        print(f"  ⚠ 检测到 {len(anomalies)} 个需求异常:")
        for a in anomalies:
            print(f"    {a['region']}: {a['change_mbd']:+.2f} mb/d ({a['change_pct']:+.1f}%) @ {a['date']}")

    return {
        "steo_by_region": steo_demand,
        "intl_production": intl_production,
        "jodi": jodi_data,
        "refinery_proxies": asia_proxy,
        "demand_share": demand_share,
        "anomalies": anomalies,
        "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def save_global_demand(data: dict):
    """保存全球需求数据。"""
    out_file = DATA_DIR / "global_demand.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    n_steo = sum(1 for v in data.get("steo_by_region", {}).values() if v)
    n_intl = sum(1 for v in data.get("intl_production", {}).values() if v)
    n_jodi = len(data.get("jodi", {}).get("countries", {}))
    share = data.get("demand_share", {})
    print(f"  ✓ global_demand.json (STEO: {n_steo} 地区, EIA国际: {n_intl} 国家, JODI: {n_jodi} 国家)")
    if share:
        print(f"    全球需求: {share.get('world_total_mbd', '?')} mb/d @ {share.get('date', '?')}")


if __name__ == "__main__":
    print("[全球石油需求]")
    data = fetch_global_demand()
    save_global_demand(data)

    # 打印需求份额
    share = data.get("demand_share", {})
    if share.get("shares"):
        print("\n[需求份额]")
        for region, info in sorted(share["shares"].items(),
                                     key=lambda x: x[1]["share_pct"], reverse=True):
            print(f"  {region}: {info['value_mbd']:.1f} mb/d ({info['share_pct']:.1f}%)")
