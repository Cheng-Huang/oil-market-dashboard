"""
获取 WTI 原油期货曲线数据（Yahoo Finance）

提供：
  - 期货曲线快照（12 个月合约价格）
  - M1-M2 近远月价差（Backwardation / Contango 判断依据）
  - 历史价差时间序列（累积模式 + 引导式回填）
"""
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf
import pandas as pd

from config import DATA_DIR

# WTI (CL) 期货月份代码
MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


# ── 合约 Ticker 生成 ──────────────────────────────────

def _contract_tickers(n_months: int = 12) -> list[dict]:
    """
    生成未来 n 个月的 WTI CL 期货合约 Yahoo Finance ticker。
    WTI 合约一般在交割月前一个月的 20 号左右到期，
    为安全起见从 当前月+1 开始（当前月合约可能已到期或流动性极低）。
    """
    now = datetime.now()
    # 如果已过 20 号，当前月合约大概率已到期，从 +2 开始
    start_offset = 2 if now.day >= 20 else 1
    month = now.month + start_offset
    year = now.year
    if month > 12:
        month -= 12
        year += 1

    result = []
    for i in range(n_months):
        m = ((month - 1 + i) % 12) + 1
        y = year + (month - 1 + i) // 12
        code = MONTH_CODES[m]
        yr2 = str(y)[-2:]
        ticker = f"CL{code}{yr2}.NYM"
        label = f"{MONTH_NAMES[m]} {y}"
        result.append({
            "ticker": ticker,
            "month": f"{y}-{m:02d}",
            "label": label,
            "order": i,
        })
    return result


# ── 曲线快照 ──────────────────────────────────────────

def fetch_curve_snapshot(n_months: int = 12) -> list[dict]:
    """获取当前 WTI 期货曲线 —— 每个合约月份的最新收盘价"""
    contracts = _contract_tickers(n_months)
    tickers = [c["ticker"] for c in contracts]
    print(f"  获取 {len(tickers)} 个 WTI 期货合约价格...")

    # yfinance 批量下载（一次 HTTP 请求）
    try:
        df = yf.download(tickers, period="5d", progress=False, group_by="ticker")
    except Exception as e:
        print(f"  ✗ yfinance 下载失败: {e}")
        return []

    if df.empty:
        print("  ✗ yfinance 返回空数据")
        return []

    curve = []
    single_ticker = len(tickers) == 1

    for c in contracts:
        try:
            if single_ticker:
                close = df["Close"].dropna()
            else:
                close = df[(c["ticker"], "Close")].dropna()
            if not close.empty:
                price = float(close.iloc[-1])
                date_val = close.index[-1]
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
                if price > 0:
                    curve.append({
                        "month": c["month"],
                        "label": c["label"],
                        "ticker": c["ticker"],
                        "price": round(price, 2),
                        "date": date_str,
                    })
        except (KeyError, IndexError):
            pass  # 该合约可能没有活跃交易

    print(f"  → 获取到 {len(curve)} 个合约价格")
    return curve


# ── 历史近远月价差 ─────────────────────────────────────

def _bootstrap_spread_history(days: int = 500) -> list[dict]:
    """
    尝试从最近两个特定合约的历史重叠区间构建 M1-M2 价差时间序列。
    由于单一合约存续期有限，通常只能获得数月数据。
    """
    contracts = _contract_tickers(3)
    m1_ticker = contracts[0]["ticker"]
    m2_ticker = contracts[1]["ticker"]

    print(f"  引导历史价差: {m1_ticker} vs {m2_ticker}")

    try:
        tickers_str = f"{m1_ticker} {m2_ticker}"
        df = yf.download(tickers_str, period=f"{days}d", progress=False, group_by="ticker")

        if df.empty:
            return []

        m1_close = df[(m1_ticker, "Close")].dropna()
        m2_close = df[(m2_ticker, "Close")].dropna()

        common_dates = m1_close.index.intersection(m2_close.index)
        spread_data = []
        for date in sorted(common_dates):
            m1_val = float(m1_close.loc[date])
            m2_val = float(m2_close.loc[date])
            if m1_val > 0 and m2_val > 0:
                date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]
                spread_data.append({
                    "date": date_str,
                    "value": round(m1_val - m2_val, 4),
                    "m1": round(m1_val, 2),
                    "m2": round(m2_val, 2),
                })

        print(f"  → 引导得到 {len(spread_data)} 天的历史价差")
        return spread_data

    except Exception as e:
        print(f"  ⚠ 引导历史价差失败: {e}")
        return []


# ── 主入口 ─────────────────────────────────────────────

def fetch_futures_data() -> dict:
    """
    获取所有期货相关数据并保存到 futures.json。

    返回:
      {
        "curve": [...],           # 曲线快照（12 个合约）
        "m1_m2_spread": float,    # 当前 M1-M2 价差
        "m1_m6_spread": float,    # 当前 M1-M6 价差
        "structure": str,         # "backwardation" / "contango" / "flat"
        "spread_history": [...],  # 历史 M1-M2 价差时间序列
        "updated": str,
      }
    """

    # 1. 曲线快照
    curve = fetch_curve_snapshot(12)

    # 2. 计算当前价差
    m1_m2_spread = None
    m1_m6_spread = None
    structure = "unknown"

    if len(curve) >= 2:
        m1_m2_spread = round(curve[0]["price"] - curve[1]["price"], 4)
    if len(curve) >= 6:
        m1_m6_spread = round(curve[0]["price"] - curve[5]["price"], 4)

    # 判断期限结构
    if m1_m2_spread is not None:
        if m1_m2_spread > 0.10:
            structure = "backwardation"
        elif m1_m2_spread < -0.10:
            structure = "contango"
        else:
            structure = "flat"

    # 3. 加载已有历史数据（累积模式）
    futures_path = DATA_DIR / "futures.json"
    existing = {}
    if futures_path.exists():
        try:
            with open(futures_path) as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    spread_history = existing.get("spread_history", [])

    # 4. 如果历史不够，尝试引导回填
    if len(spread_history) < 20:
        try:
            bootstrapped = _bootstrap_spread_history(500)
            if bootstrapped:
                existing_dates = {d["date"] for d in spread_history}
                for point in bootstrapped:
                    if point["date"] not in existing_dates:
                        spread_history.append(point)
                spread_history.sort(key=lambda x: x["date"])
        except Exception as e:
            print(f"  ⚠ 引导回填失败: {e}")

    # 5. 追加今天的价差数据点
    if curve and len(curve) >= 2:
        today = curve[0]["date"]
        existing_dates = {d["date"] for d in spread_history}
        if today not in existing_dates:
            spread_history.append({
                "date": today,
                "value": m1_m2_spread,
                "m1": curve[0]["price"],
                "m2": curve[1]["price"],
            })
            spread_history.sort(key=lambda x: x["date"])

    # 6. 构建输出
    result = {
        "curve": curve,
        "m1_m2_spread": m1_m2_spread,
        "m1_m6_spread": m1_m6_spread,
        "structure": structure,
        "spread_history": spread_history,
        "updated": datetime.now().isoformat(),
    }

    # 7. 保存
    save_futures_data(result)
    return result


def save_futures_data(data: dict):
    """保存期货数据到 futures.json"""
    with open(DATA_DIR / "futures.json", "w") as f:
        json.dump(data, f, indent=2)
    n_curve = len(data.get("curve", []))
    n_hist = len(data.get("spread_history", []))
    struct = data.get("structure", "unknown")
    print(f"  ✓ futures.json (曲线: {n_curve} 合约, 历史: {n_hist} 天, 结构: {struct})")


if __name__ == "__main__":
    print("获取 WTI 期货曲线数据...")
    data = fetch_futures_data()
    if data["curve"]:
        print("\n期货曲线:")
        for c in data["curve"]:
            print(f"  {c['label']:>10}  ${c['price']:.2f}")
        print(f"\nM1-M2 价差: ${data['m1_m2_spread']}")
        if data["m1_m6_spread"] is not None:
            print(f"M1-M6 价差: ${data['m1_m6_spread']}")
        print(f"期限结构: {data['structure']}")
