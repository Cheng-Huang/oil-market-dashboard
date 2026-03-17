"""
从 Yahoo Finance 获取 WTI/Brent 实时价格，消除 FRED/EIA 现货价格 8 天滞后。

数据源：Yahoo Finance（免费，无需 API Key）
  - CL=F  → WTI 原油连续合约
  - BZ=F  → Brent 原油连续合约
  - HO=F  → 取暖油期货
  - RB=F  → RBOB 汽油期货

输出：data/price_realtime.json
  - 最近 60 天日频 OHLCV
  - 最新快照（含盘中价格）
  - 与本地 price.json / price_eia.json 的滞后天数对比
"""
import json
from datetime import datetime, timedelta

import yfinance as yf

from config import DATA_DIR

# Yahoo Finance 期货连续合约 ticker
ENERGY_TICKERS = {
    "wti":         {"ticker": "CL=F",  "name": "WTI Crude Oil",   "unit": "$/bbl"},
    "brent":       {"ticker": "BZ=F",  "name": "Brent Crude Oil",  "unit": "$/bbl"},
    "heating_oil": {"ticker": "HO=F",  "name": "Heating Oil",      "unit": "$/gal"},
    "gasoline":    {"ticker": "RB=F",  "name": "RBOB Gasoline",    "unit": "$/gal"},
    "natural_gas": {"ticker": "NG=F",  "name": "Natural Gas",      "unit": "$/MMBtu"},
}


def fetch_realtime_prices(days: int = 60) -> dict:
    """
    拉取能源期货近 N 天日频数据和最新盘中快照。
    返回:
      {
        "wti": {"latest": {...}, "history": [{date, open, high, low, close, volume}, ...]},
        "brent": {...},
        ...
        "snapshot_time": "2026-03-17T14:30:00",
        "freshness": {"wti": {"realtime": "2026-03-17", "fred": "2026-03-09", "lag_days": 8}}
      }
    """
    tickers = [v["ticker"] for v in ENERGY_TICKERS.values()]
    print(f"  获取 {len(tickers)} 个能源期货实时价格...")

    # 批量下载日频数据
    period = f"{days}d"
    try:
        df = yf.download(tickers, period=period, progress=False, group_by="ticker")
    except Exception as e:
        print(f"  ✗ yfinance 下载失败: {e}")
        return {}

    if df.empty:
        print("  ✗ yfinance 返回空数据")
        return {}

    result = {}
    single_ticker = len(tickers) == 1

    for key, info in ENERGY_TICKERS.items():
        tk = info["ticker"]
        try:
            if single_ticker:
                sub = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            else:
                sub = df[tk][["Open", "High", "Low", "Close", "Volume"]].dropna()

            if sub.empty:
                print(f"    ⚠ {key} ({tk}) 无数据")
                continue

            history = []
            for idx, row in sub.iterrows():
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                history.append({
                    "date": date_str,
                    "open":   round(float(row["Open"]), 2),
                    "high":   round(float(row["High"]), 2),
                    "low":    round(float(row["Low"]), 2),
                    "close":  round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
                })

            latest = history[-1] if history else {}
            result[key] = {
                "name":    info["name"],
                "unit":    info["unit"],
                "ticker":  tk,
                "latest":  latest,
                "history": history,
            }
            if latest:
                print(f"    ✓ {key}: ${latest['close']} ({latest['date']})")

        except Exception as e:
            print(f"    ⚠ {key} ({tk}) 解析失败: {e}")

    # 计算 WTI-Brent 价差
    if "wti" in result and "brent" in result:
        wti_map = {h["date"]: h["close"] for h in result["wti"]["history"]}
        brent_map = {h["date"]: h["close"] for h in result["brent"]["history"]}
        common = sorted(set(wti_map) & set(brent_map))
        result["wti_brent_spread"] = [
            {"date": d, "value": round(wti_map[d] - brent_map[d], 2)}
            for d in common
        ]

    # 计算裂解价差（从期货价格）
    if "wti" in result and "gasoline" in result and "heating_oil" in result:
        wti_map = {h["date"]: h["close"] for h in result["wti"]["history"]}
        gas_map = {h["date"]: h["close"] for h in result["gasoline"]["history"]}
        ho_map = {h["date"]: h["close"] for h in result["heating_oil"]["history"]}
        common = sorted(set(wti_map) & set(gas_map) & set(ho_map))
        result["crack_321_realtime"] = [
            {
                "date": d,
                "value": round((2 * gas_map[d] * 42 + ho_map[d] * 42) / 3 - wti_map[d], 2),
            }
            for d in common
        ]

    result["snapshot_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return result


def _compute_freshness(realtime_data: dict) -> dict:
    """比较实时数据与本地 FRED/EIA 价格的新鲜度差异。"""
    freshness = {}
    price_file = DATA_DIR / "price.json"
    eia_file = DATA_DIR / "price_eia.json"

    fred_dates = {}
    eia_dates = {}
    try:
        with open(price_file) as f:
            price = json.load(f)
        for key in ["wti", "brent"]:
            if price.get(key):
                fred_dates[key] = price[key][-1]["date"]
    except (FileNotFoundError, json.JSONDecodeError, IndexError):
        pass

    try:
        with open(eia_file) as f:
            eia = json.load(f)
        for key in ["wti", "brent"]:
            if eia.get(key):
                eia_dates[key] = eia[key][-1]["date"]
    except (FileNotFoundError, json.JSONDecodeError, IndexError):
        pass

    for key in ["wti", "brent"]:
        rt = realtime_data.get(key, {})
        rt_latest = rt.get("latest", {}).get("date", "")
        if not rt_latest:
            continue

        entry = {"realtime": rt_latest}
        rt_dt = datetime.strptime(rt_latest, "%Y-%m-%d")

        if key in fred_dates:
            entry["fred"] = fred_dates[key]
            fred_dt = datetime.strptime(fred_dates[key], "%Y-%m-%d")
            entry["fred_lag_days"] = (rt_dt - fred_dt).days

        if key in eia_dates:
            entry["eia"] = eia_dates[key]
            eia_dt = datetime.strptime(eia_dates[key], "%Y-%m-%d")
            entry["eia_lag_days"] = (rt_dt - eia_dt).days

        freshness[key] = entry

    return freshness


def save_realtime_prices(data: dict):
    """保存实时价格到 data/price_realtime.json。"""
    data["freshness"] = _compute_freshness(data)
    out_file = DATA_DIR / "price_realtime.json"
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  ✓ price_realtime.json 已保存")

    # 同时更新 price.json，将实时数据追加到 FRED 价格之后
    _merge_into_price(data)


def _merge_into_price(realtime_data: dict):
    """
    将 Yahoo Finance 实时价格合并到 price.json。
    仅追加比现有数据更新的日期，不覆盖已有数据。
    """
    price_file = DATA_DIR / "price.json"
    try:
        with open(price_file) as f:
            price = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        price = {"wti": [], "brent": [], "spread": []}

    updated = False
    for key in ["wti", "brent"]:
        existing = price.get(key, [])
        rt = realtime_data.get(key, {})
        rt_history = rt.get("history", [])
        if not rt_history:
            continue

        existing_dates = {d["date"] for d in existing}
        # Yahoo Finance close price → 追加为 spot price
        new_points = [
            {"date": h["date"], "value": h["close"]}
            for h in rt_history
            if h["date"] not in existing_dates
        ]
        if new_points:
            existing.extend(new_points)
            existing.sort(key=lambda x: x["date"])
            price[key] = existing
            updated = True
            print(f"    ✓ {key}: 追加 {len(new_points)} 天实时价格 → price.json")

    if updated:
        # 重算 spread
        if price.get("wti") and price.get("brent"):
            brent_map = {d["date"]: d["value"] for d in price["brent"]}
            price["spread"] = [
                {"date": d["date"], "value": round(d["value"] - brent_map[d["date"]], 4)}
                for d in price["wti"]
                if d["date"] in brent_map
            ]
        # 标记数据来源
        price["_source_note"] = (
            "FRED + EIA + Yahoo Finance realtime. "
            f"Last realtime merge: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
        )
        with open(price_file, "w") as f:
            json.dump(price, f, indent=2)


if __name__ == "__main__":
    print("[Yahoo Finance 实时价格]")
    data = fetch_realtime_prices()
    if data:
        save_realtime_prices(data)
        # 打印新鲜度对比
        freshness = data.get("freshness", {})
        if freshness:
            print("\n[价格新鲜度对比]")
            for key, info in freshness.items():
                lag_fred = info.get("fred_lag_days", "?")
                lag_eia = info.get("eia_lag_days", "?")
                print(f"  {key}: 实时={info['realtime']}, "
                      f"FRED滞后={lag_fred}天, EIA滞后={lag_eia}天")
    else:
        print("  ✗ 无法获取实时价格")
