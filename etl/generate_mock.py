"""
生成模拟数据（用于前端开发 & 演示）
数据格式与真实 ETL 输出完全一致
"""
import json
import math
import random
from datetime import datetime, timedelta
from config import DATA_DIR


def _dates(n: int, freq: str = "daily") -> list[str]:
    """生成日期序列"""
    end = datetime(2026, 3, 3)
    step = timedelta(days=1) if freq == "daily" else timedelta(weeks=1)
    dates = []
    d = end - step * (n - 1)
    for _ in range(n):
        dates.append(d.strftime("%Y-%m-%d"))
        d += step
    return dates


def _walk(start: float, n: int, vol: float = 0.01, trend: float = 0.0) -> list[float]:
    """随机游走生成价格/指标序列"""
    values = [start]
    for _ in range(n - 1):
        change = random.gauss(trend, vol) * values[-1]
        values.append(round(values[-1] + change, 2))
    return values


def _seasonal(base: float, n: int, amplitude: float, period: int = 52) -> list[float]:
    """带季节性的序列"""
    return [
        round(base + amplitude * math.sin(2 * math.pi * i / period) + random.gauss(0, amplitude * 0.3), 2)
        for i in range(n)
    ]


def generate_mock_data():
    random.seed(42)
    now_str = datetime(2026, 3, 3).strftime("%Y-%m-%dT%H:%M:%S")

    # ── 价格 (日度, 2年) ──────────────────────────────
    n_daily = 500
    daily_dates = _dates(n_daily, "daily")
    wti_vals = _walk(68.0, n_daily, vol=0.015, trend=0.0001)
    brent_vals = [round(w + random.gauss(3.5, 0.5), 2) for w in wti_vals]
    spread_vals = [round(w - b, 4) for w, b in zip(wti_vals, brent_vals)]

    price = {
        "wti":    [{"date": d, "value": v} for d, v in zip(daily_dates, wti_vals)],
        "brent":  [{"date": d, "value": v} for d, v in zip(daily_dates, brent_vals)],
        "spread": [{"date": d, "value": v} for d, v in zip(daily_dates, spread_vals)],
    }

    # ── 库存 (周度, 5年=260周) ────────────────────────
    n_weekly = 260
    weekly_dates = _dates(n_weekly, "weekly")

    inventory = {
        "crude":      [{"date": d, "value": v} for d, v in
                       zip(weekly_dates, _seasonal(430000, n_weekly, 30000))],
        "cushing":    [{"date": d, "value": v} for d, v in
                       zip(weekly_dates, _seasonal(32000, n_weekly, 8000))],
        "gasoline":   [{"date": d, "value": v} for d, v in
                       zip(weekly_dates, _seasonal(235000, n_weekly, 20000))],
        "distillate": [{"date": d, "value": v} for d, v in
                       zip(weekly_dates, _seasonal(125000, n_weekly, 15000))],
    }
    # 让最近几周原油库存持续下降（模拟去库）
    for i in range(-4, 0):
        inventory["crude"][i]["value"] = inventory["crude"][i - 1]["value"] - random.uniform(1000, 3000)

    # ── 产量 (周度) ───────────────────────────────────
    production = {
        "crude_production":     [{"date": d, "value": v} for d, v in
                                 zip(weekly_dates[-104:], _walk(13100, 104, vol=0.003))],
        "refinery_utilization": [{"date": d, "value": v} for d, v in
                                 zip(weekly_dates[-104:], _seasonal(90.5, 104, 5.0, 52))],
        "net_import":           [{"date": d, "value": v} for d, v in
                                 zip(weekly_dates[-104:], _walk(2500, 104, vol=0.02))],
    }

    # ── 需求 (周度) ───────────────────────────────────
    demand = {
        "gasoline":   [{"date": d, "value": v} for d, v in
                       zip(weekly_dates[-104:], _seasonal(9200, 104, 800, 52))],
        "distillate": [{"date": d, "value": v} for d, v in
                       zip(weekly_dates[-104:], _seasonal(4100, 104, 500, 52))],
    }

    # ── 金融条件 (日度) ───────────────────────────────
    financial = {
        "dxy":       [{"date": d, "value": v} for d, v in
                      zip(daily_dates, _walk(104.5, n_daily, vol=0.003))],
        "real_rate": [{"date": d, "value": v} for d, v in
                      zip(daily_dates, _walk(1.85, n_daily, vol=0.02, trend=-0.0001))],
        "ovx":       [{"date": d, "value": v} for d, v in
                      zip(daily_dates, _walk(28.0, n_daily, vol=0.03))],
    }

    # ── CFTC 持仓 (周度, 3年) ─────────────────────────
    n_cftc = 156
    cftc_dates = _dates(n_cftc, "weekly")
    cftc = []
    net = 180000
    for d in cftc_dates:
        net += random.gauss(0, 8000)
        net = max(50000, min(350000, net))
        long_pos = net + random.uniform(20000, 60000)
        short_pos = long_pos - net
        cftc.append({
            "date": d,
            "net_long": round(net),
            "long": round(long_pos),
            "short": round(short_pos),
            "open_interest": round(long_pos + short_pos + random.uniform(100000, 200000)),
        })

    # ── 期货曲线 (模拟 12 个月合约) ──────────────────
    # 模拟 Backwardation 结构（近月高于远月）
    base_price = wti_vals[-1]  # 以最新 WTI 价格为基准
    month_codes = {1:'F', 2:'G', 3:'H', 4:'J', 5:'K', 6:'M',
                   7:'N', 8:'Q', 9:'U', 10:'V', 11:'X', 12:'Z'}
    month_names = {1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'Jun',
                   7:'Jul', 8:'Aug', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dec'}

    # 期货曲线快照
    curve = []
    from datetime import datetime as _dt
    mock_now = _dt(2026, 3, 3)
    start_month = mock_now.month + 1
    start_year = mock_now.year
    if start_month > 12:
        start_month -= 12
        start_year += 1

    for i in range(12):
        m = ((start_month - 1 + i) % 12) + 1
        y = start_year + (start_month - 1 + i) // 12
        code = month_codes[m]
        yr2 = str(y)[-2:]
        # 模拟 Backwardation: 近月略高，逐月递减 + 随机扰动
        decay = -0.15 * i + random.gauss(0, 0.08)
        contract_price = round(base_price + decay, 2)
        curve.append({
            "month": f"{y}-{m:02d}",
            "label": f"{month_names[m]} {y}",
            "ticker": f"CL{code}{yr2}.NYM",
            "price": contract_price,
            "date": "2026-03-03",
        })

    # M1-M2 和 M1-M6 价差
    m1_m2_spread = round(curve[0]["price"] - curve[1]["price"], 4) if len(curve) >= 2 else 0
    m1_m6_spread = round(curve[0]["price"] - curve[5]["price"], 4) if len(curve) >= 6 else None

    if m1_m2_spread > 0.10:
        structure = "backwardation"
    elif m1_m2_spread < -0.10:
        structure = "contango"
    else:
        structure = "flat"

    # 模拟历史 M1-M2 价差序列 (日度，约 6 个月)
    n_spread_hist = 120
    spread_hist_dates = _dates(n_spread_hist, "daily")
    spread_history = []
    spread_val = 0.3  # 初始略微 Backwardation
    for d in spread_hist_dates:
        spread_val += random.gauss(0, 0.05)
        spread_val = max(-1.5, min(1.5, spread_val))
        m1_price = base_price + random.gauss(0, 0.5)
        spread_history.append({
            "date": d,
            "value": round(spread_val, 4),
            "m1": round(m1_price, 2),
            "m2": round(m1_price - spread_val, 2),
        })

    futures = {
        "curve": curve,
        "m1_m2_spread": m1_m2_spread,
        "m1_m6_spread": m1_m6_spread,
        "structure": structure,
        "spread_history": spread_history,
        "updated": now_str,
    }

    # ── Meta ──────────────────────────────────────────
    meta = {
        "last_updated": now_str,
        "sources": {
            "price": {"source": "MOCK", "updated": now_str},
            "inventory": {"source": "MOCK", "updated": now_str},
            "production": {"source": "MOCK", "updated": now_str},
            "demand": {"source": "MOCK", "updated": now_str},
            "financial": {"source": "MOCK", "updated": now_str},
            "cftc": {"source": "MOCK", "updated": now_str},
            "futures": {"source": "MOCK", "updated": now_str},
        },
    }

    # ── 写文件 ────────────────────────────────────────
    files = {
        "price.json": price,
        "inventory.json": inventory,
        "production.json": production,
        "demand.json": demand,
        "financial.json": financial,
        "cftc.json": cftc,
        "futures.json": futures,
        "meta.json": meta,
    }
    for fname, data in files.items():
        with open(DATA_DIR / fname, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  ✓ {fname}")

    print(f"\n✓ 模拟数据已生成到 {DATA_DIR}")


if __name__ == "__main__":
    generate_mock_data()
