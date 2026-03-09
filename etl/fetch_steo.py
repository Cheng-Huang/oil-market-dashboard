"""
从 EIA STEO (Short-Term Energy Outlook) 拉取全球供需平衡 + 钻井数据
输出: global_balance.json, drilling.json
"""
import json
import requests
from datetime import datetime, timedelta
from config import EIA_API_KEY, DATA_DIR


# EIA STEO 月度 series（使用 /v2/seriesid/ 端点）
STEO_SERIES = {
    # ── 全球供需平衡 ──
    "world_production":    "STEO.PAPR_WORLD.M",    # 全球液体燃料产量 (百万桶/日)
    "world_consumption":   "STEO.PATC_WORLD.M",    # 全球液体燃料消费 (百万桶/日)
    "opec_production":     "STEO.PAPR_OPEC.M",     # OPEC 液体燃料产量 (百万桶/日)
    "non_opec_production": "STEO.PAPR_NONOPEC.M",  # 非 OPEC 产量 (百万桶/日)
    # ── 美国钻井 ──
    "us_rig_count":        "STEO.CORIPUS.M",       # 美国原油钻机数 (座)
}


def fetch_steo_series(series_id: str, days_back: int = 1825) -> list[dict]:
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


def fetch_all_steo() -> dict:
    """拉取所有 STEO 指标"""
    result = {}
    for key, sid in STEO_SERIES.items():
        print(f"  STEO: {key} ({sid}) ...")
        try:
            result[key] = fetch_steo_series(sid)
            print(f"    → {len(result[key])} observations")
        except Exception as e:
            print(f"    ✗ 失败: {e}")
            result[key] = []
    return result


def _compute_balance(production: list[dict], consumption: list[dict]) -> list[dict]:
    """计算全球供需平衡: production - consumption = 隐含库存变化"""
    prod_map = {d["date"]: d["value"] for d in production}
    cons_map = {d["date"]: d["value"] for d in consumption}
    common = sorted(set(prod_map) & set(cons_map))
    return [
        {"date": dt, "value": round(prod_map[dt] - cons_map[dt], 3)}
        for dt in common
    ]


def save_steo_data(data: dict):
    """存储 STEO 数据到 global_balance.json 和 drilling.json"""
    # ── 全球供需平衡 ──
    world_prod = data.get("world_production", [])
    world_cons = data.get("world_consumption", [])
    balance = _compute_balance(world_prod, world_cons) if world_prod and world_cons else []

    global_balance = {
        "world_production": world_prod,
        "world_consumption": world_cons,
        "opec_production": data.get("opec_production", []),
        "non_opec_production": data.get("non_opec_production", []),
        "balance": balance,  # >0 累库, <0 去库
    }
    with open(DATA_DIR / "global_balance.json", "w") as f:
        json.dump(global_balance, f, indent=2)

    # ── 钻井数据 ──
    drilling = {
        "rig_count": data.get("us_rig_count", []),
    }
    with open(DATA_DIR / "drilling.json", "w") as f:
        json.dump(drilling, f, indent=2)


if __name__ == "__main__":
    if not EIA_API_KEY:
        print("⚠ EIA_API_KEY 未设置，跳过 STEO 拉取")
    else:
        data = fetch_all_steo()
        save_steo_data(data)
        print("✓ STEO 数据已保存")
