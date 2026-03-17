"""
EIA 日频现货价格 — 独立拉取脚本

区别于 fetch_eia.py（需要同时拉取周度库存/产量等大量数据），
本脚本仅拉取 EIA 日频现货价格，可以每天高频运行。

数据源：EIA Open Data API v2
  - WTI 现货: PET.RWTC.D
  - Brent 现货: PET.RBRTE.D
  - 汽油现货: PET.EER_EPMRU_PF4_RGC_DPG.D

输出：更新 data/price_eia.json，并合并到 data/price.json
"""
import json
import requests
from datetime import datetime, timedelta

from config import EIA_API_KEY, EIA_DAILY_SERIES, DATA_DIR


def fetch_eia_daily_prices(days_back: int = 90) -> dict:
    """
    仅拉取 EIA 日频现货价格。
    比 fetch_all_eia() 更轻量，适合每日/多次运行。
    """
    if not EIA_API_KEY:
        print("  ⚠ EIA_API_KEY 未设置")
        return {}

    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    result = {}

    for key, series_id in EIA_DAILY_SERIES.items():
        print(f"  EIA Daily: {key} ({series_id}) ...")
        try:
            url = f"https://api.eia.gov/v2/seriesid/{series_id}"
            params = {
                "api_key": EIA_API_KEY,
                "start": start,
            }
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            response_data = data.get("response", {}).get("data", [])

            records = []
            for item in response_data:
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
                print(f"    → {len(records)} 天, 最新: {records[-1]['date']} = ${records[-1]['value']}")
            else:
                print(f"    → 0 条记录")
        except Exception as e:
            print(f"    ✗ 失败: {e}")
            result[key] = []

    return result


def save_eia_daily_prices(data: dict):
    """
    保存 EIA 日频价格到 price_eia.json，
    并将新数据合并到 price.json 以消除滞后。
    """
    eia_file = DATA_DIR / "price_eia.json"
    price_file = DATA_DIR / "price.json"

    # ── 1) 更新 price_eia.json ──
    eia_price = {
        "wti": data.get("wti_price", []),
        "brent": data.get("brent_price", []),
        "gasoline_spot": data.get("gasoline_spot_price", []),
        "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(eia_file, "w") as f:
        json.dump(eia_price, f, indent=2)
    print(f"  ✓ price_eia.json 已更新")

    # ── 2) 合并到 price.json ──
    try:
        with open(price_file) as f:
            price = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        price = {"wti": [], "brent": [], "spread": []}

    updated = False
    for key in ["wti", "brent"]:
        eia_key = f"{key}_price"
        eia_data = data.get(eia_key, [])
        existing = price.get(key, [])
        if not eia_data:
            continue

        existing_dates = {d["date"] for d in existing}
        new_points = [p for p in eia_data if p["date"] not in existing_dates]
        if new_points:
            existing.extend(new_points)
            existing.sort(key=lambda x: x["date"])
            price[key] = existing
            updated = True
            print(f"    ✓ {key}: EIA 日频补齐 {len(new_points)} 天 → price.json "
                  f"(最新: {existing[-1]['date']})")

    if updated:
        # 重算 spread
        if price.get("wti") and price.get("brent"):
            brent_map = {d["date"]: d["value"] for d in price["brent"]}
            price["spread"] = [
                {"date": d["date"], "value": round(d["value"] - brent_map[d["date"]], 4)}
                for d in price["wti"]
                if d["date"] in brent_map
            ]
        price["_source_note"] = (
            "FRED + EIA daily. "
            f"Last EIA daily merge: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
        )
        with open(price_file, "w") as f:
            json.dump(price, f, indent=2)


def print_freshness_report(data: dict):
    """打印 EIA 日频价格与 FRED 的新鲜度对比。"""
    price_file = DATA_DIR / "price.json"
    try:
        with open(price_file) as f:
            price = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    print("\n[EIA 日频价格新鲜度]")
    today = datetime.now().date()
    for key in ["wti", "brent"]:
        existing = price.get(key, [])
        if existing:
            latest_date = existing[-1]["date"]
            days_old = (today - datetime.strptime(latest_date, "%Y-%m-%d").date()).days
            print(f"  {key}: 最新 {latest_date} (滞后 {days_old} 天)")


if __name__ == "__main__":
    print("[EIA 日频现货价格拉取]")
    if not EIA_API_KEY:
        print("⚠ EIA_API_KEY 未设置")
    else:
        data = fetch_eia_daily_prices()
        save_eia_daily_prices(data)
        print_freshness_report(data)
