"""
从 FRED API 拉取金融条件数据：DXY、实际利率、OVX、WTI/Brent 价格
"""
import json
import requests
from datetime import datetime, timedelta
from config import FRED_BASE, FRED_API_KEY, FRED_SERIES, DATA_DIR


def fetch_fred_series(series_id: str, days_back: int = 730) -> list[dict]:
    """拉取单个 FRED series 的观测值"""
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "asc",
    }
    resp = requests.get(FRED_BASE, params=params, timeout=30)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    # 清洗：过滤 "." 缺失值，转 float
    return [
        {"date": o["date"], "value": float(o["value"])}
        for o in observations
        if o["value"] != "."
    ]


def fetch_all_fred() -> dict:
    """拉取所有 FRED 指标，返回 {key: [{date, value}, ...]}"""
    result = {}
    for key, sid in FRED_SERIES.items():
        print(f"  FRED: {key} ({sid}) ...")
        try:
            result[key] = fetch_fred_series(sid)
            print(f"    → {len(result[key])} observations")
        except Exception as e:
            print(f"    ✗ 失败: {e}")
            result[key] = []
    return result


def _compute_crack_spread(wti, gasoline, heating_oil):
    """
    计算裂解价差:
    - 3-2-1 Crack = (2 × 汽油价 + 1 × 取暖油价) / 3 × 42 − WTI
      (汽油/取暖油单位 $/gal → ×42 转 $/bbl)
    - Gasoline Crack = 汽油价 × 42 − WTI
    - Diesel Crack = 取暖油价 × 42 − WTI
    """
    wti_map = {d["date"]: d["value"] for d in wti}
    gas_map = {d["date"]: d["value"] for d in gasoline}
    ho_map = {d["date"]: d["value"] for d in heating_oil}
    common_dates = sorted(set(wti_map) & set(gas_map) & set(ho_map))

    crack_321, crack_gas, crack_diesel = [], [], []
    for dt in common_dates:
        w = wti_map[dt]
        g = gas_map[dt] * 42  # $/gal → $/bbl
        h = ho_map[dt] * 42
        crack_321.append({"date": dt, "value": round((2 * g + h) / 3 - w, 4)})
        crack_gas.append({"date": dt, "value": round(g - w, 4)})
        crack_diesel.append({"date": dt, "value": round(h - w, 4)})

    return crack_321, crack_gas, crack_diesel


def save_fred_data(data: dict):
    """拆分存储：价格 → price.json，金融条件 → financial.json，裂解价差 → crack_spread.json"""
    # ── 价格 ──
    price = {
        "wti": data.get("wti_price", []),
        "brent": data.get("brent_price", []),
    }
    # 计算价差
    if price["wti"] and price["brent"]:
        brent_map = {d["date"]: d["value"] for d in price["brent"]}
        price["spread"] = [
            {"date": d["date"], "value": round(d["value"] - brent_map[d["date"]], 4)}
            for d in price["wti"]
            if d["date"] in brent_map
        ]
    else:
        price["spread"] = []

    with open(DATA_DIR / "price.json", "w") as f:
        json.dump(price, f, indent=2)

    # ── 金融条件 ──
    financial = {
        "dxy": data.get("dxy", []),
        "real_rate": data.get("real_rate", []),
        "ovx": data.get("ovx", []),
    }
    with open(DATA_DIR / "financial.json", "w") as f:
        json.dump(financial, f, indent=2)

    # ── 裂解价差 ──
    wti = data.get("wti_price", [])
    gasoline = data.get("gasoline_price", [])
    heating_oil = data.get("heating_oil_price", [])
    if wti and gasoline and heating_oil:
        crack_321, crack_gas, crack_diesel = _compute_crack_spread(wti, gasoline, heating_oil)
        crack_spread = {
            "crack_321": crack_321,
            "gasoline_crack": crack_gas,
            "diesel_crack": crack_diesel,
        }
    else:
        crack_spread = {"crack_321": [], "gasoline_crack": [], "diesel_crack": []}

    with open(DATA_DIR / "crack_spread.json", "w") as f:
        json.dump(crack_spread, f, indent=2)


if __name__ == "__main__":
    if not FRED_API_KEY:
        print("⚠ FRED_API_KEY 未设置，跳过 FRED 拉取")
    else:
        data = fetch_all_fred()
        save_fred_data(data)
        print("✓ FRED 数据已保存")
