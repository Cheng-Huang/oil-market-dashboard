"""
从 EIA Open Data API v2 拉取石油数据：库存、产量、炼厂开工率、需求、进出口
"""
import json
import requests
from datetime import datetime, timedelta
from config import EIA_API_KEY, EIA_WEEKLY_SERIES, EIA_DAILY_SERIES, DATA_DIR


def fetch_eia_series(series_id: str, frequency: str = "weekly",
                     days_back: int = 1825) -> list[dict]:
    """
    EIA API v2 请求
    series_id 格式: PET.WCESTUS1.W → route=petroleum, series=WCESTUS1, freq=weekly
    """
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    # EIA v2: series_id 拆分
    parts = series_id.split(".")
    # 直接用 /v2/seriesid/{series_id} 的简化接口
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
    # 按日期升序
    result.sort(key=lambda x: x["date"])
    return result


def fetch_all_eia() -> dict:
    """拉取所有 EIA 指标"""
    result = {}
    # 周度数据
    for key, sid in EIA_WEEKLY_SERIES.items():
        print(f"  EIA: {key} ({sid}) ...")
        try:
            result[key] = fetch_eia_series(sid, frequency="weekly")
            print(f"    → {len(result[key])} observations")
        except Exception as e:
            print(f"    ✗ 失败: {e}")
            result[key] = []
    # 日度价格
    for key, sid in EIA_DAILY_SERIES.items():
        print(f"  EIA: {key} ({sid}) ...")
        try:
            result[key] = fetch_eia_series(sid, frequency="daily", days_back=730)
            print(f"    → {len(result[key])} observations")
        except Exception as e:
            print(f"    ✗ 失败: {e}")
            result[key] = []
    return result


def save_eia_data(data: dict):
    """分文件存储 EIA 数据"""
    inventory = {
        "crude": data.get("crude_inventory", []),
        "cushing": data.get("cushing_inventory", []),
        "gasoline": data.get("gasoline_inventory", []),
        "distillate": data.get("distillate_inventory", []),
        "spr": data.get("spr_inventory", []),
    }
    with open(DATA_DIR / "inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)

    production = {
        "crude_production": data.get("crude_production", []),
        "refinery_utilization": data.get("refinery_utilization", []),
        "net_import": data.get("crude_net_import", []),
    }
    with open(DATA_DIR / "production.json", "w") as f:
        json.dump(production, f, indent=2)

    demand = {
        "gasoline": data.get("gasoline_demand", []),
        "distillate": data.get("distillate_demand", []),
    }
    with open(DATA_DIR / "demand.json", "w") as f:
        json.dump(demand, f, indent=2)

    # 如果 EIA 也提供了价格（优先级低于 FRED，可覆盖）
    if data.get("wti_price") or data.get("brent_price"):
        price = {
            "wti": data.get("wti_price", []),
            "brent": data.get("brent_price", []),
        }
        with open(DATA_DIR / "price_eia.json", "w") as f:
            json.dump(price, f, indent=2)


if __name__ == "__main__":
    if not EIA_API_KEY:
        print("⚠ EIA_API_KEY 未设置，跳过 EIA 拉取")
    else:
        data = fetch_all_eia()
        save_eia_data(data)
        print("✓ EIA 数据已保存")
