"""
EIA API 公共工具函数 — 供 fetch_global_demand / fetch_opec_production / fetch_global_inventory 共用
"""
import requests
from datetime import datetime, timedelta

from config import EIA_API_KEY


def fetch_steo_series(series_id: str, days_back: int = 1825) -> list[dict]:
    """拉取单个 EIA STEO series，返回 [{date, value}, ...]"""
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


def fetch_eia_intl_production(countries: dict, *, convert_to_mbd: bool = False) -> dict:
    """
    拉取 EIA International 分国别原油产量（月度）。

    参数:
        countries: {key: {"code": "SAU", "name": "沙特"}, ...}
        convert_to_mbd: True 时将千桶/天转换为百万桶/天

    返回: {key: [{date, value}, ...], ...}
    """
    if not EIA_API_KEY:
        return {}

    result = {}
    for key, info in countries.items():
        code = info["code"]
        name = info["name"]
        print(f"    EIA国际: {name} ({code})...")
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
                        v = float(value)
                        if convert_to_mbd:
                            v = round(v / 1000, 3)
                        records.append({"date": period, "value": v})
                    except (ValueError, TypeError):
                        pass
            records.sort(key=lambda x: x["date"])
            result[key] = records
            if records:
                latest = records[-1]
                unit = "mb/d" if convert_to_mbd else "kb/d"
                fmt = f"{latest['value']:.3f}" if convert_to_mbd else f"{latest['value']:.0f}"
                print(f"      → {len(records)} 月, 最新: {latest['date']} = {fmt} {unit}")
            else:
                print(f"      → 0 条记录")
        except Exception as e:
            print(f"      ✗ 失败: {e}")
            result[key] = []

    return result
