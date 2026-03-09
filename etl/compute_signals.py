"""
信号计算引擎：根据拉取的数据计算各维度信号
输出 signals.json
"""
import json
from config import DATA_DIR, SIGNAL_INVENTORY_WEEKS as N_WEEKS
from config import (
    SIGNAL_CUSHING_WARN_MBBL,
    SIGNAL_CONTANGO_THRESHOLD,
    SIGNAL_BACK_THRESHOLD,
    SIGNAL_FUTURES_BACK_THRESHOLD,
    SIGNAL_FUTURES_CONTANGO_THRESHOLD,
    SIGNAL_OVX_PANIC,
    SIGNAL_REAL_RATE_HIGH,
    SIGNAL_POSITIONING_HIGH_PCT,
    SIGNAL_POSITIONING_LOW_PCT,
)


def _load(name: str):
    path = DATA_DIR / name
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def _pct_rank(value: float, series: list[float]) -> float:
    """百分位排名 0-100"""
    if not series:
        return 50.0
    below = sum(1 for v in series if v < value)
    return round(below / len(series) * 100, 1)


def _weekly_changes(series: list[dict]) -> list[float]:
    """计算周度变化量（相邻差分）"""
    if len(series) < 2:
        return []
    values = [d["value"] for d in series]
    return [values[i] - values[i - 1] for i in range(1, len(values))]


def inventory_signal(inv: dict) -> dict:
    crude = inv.get("crude", [])
    changes = _weekly_changes(crude)
    recent = changes[-N_WEEKS:] if len(changes) >= N_WEEKS else changes

    if recent and all(c < 0 for c in recent):
        signal = "bullish"
    elif recent and all(c > 0 for c in recent):
        signal = "bearish"
    else:
        signal = "neutral"

    # Cushing 警戒
    cushing = inv.get("cushing", [])
    cushing_val = cushing[-1]["value"] if cushing else None
    cushing_warn = False
    if cushing_val is not None and cushing_val < SIGNAL_CUSHING_WARN_MBBL * 1000:
        cushing_warn = True

    last_change = round(recent[-1], 2) if recent else 0
    return {
        "name": "库存趋势",
        "signal": signal,
        "detail": f"最近{N_WEEKS}周变化: {[round(c, 1) for c in recent]}",
        "last_change_mbbl": last_change,
        "cushing_warning": cushing_warn,
    }


def curve_signal(price: dict, futures: dict) -> dict:
    """
    曲线结构信号：优先使用真实期货 M1-M2 价差判断 Backwardation/Contango，
    如无期货数据则回退到 WTI-Brent 价差近似（并标注）。
    """
    has_futures = bool(futures and futures.get("m1_m2_spread") is not None)

    if has_futures:
        # ── 真实期货数据 ──
        m1_m2 = futures["m1_m2_spread"]
        m1_m6 = futures.get("m1_m6_spread")
        structure = futures.get("structure", "unknown")

        if m1_m2 > SIGNAL_FUTURES_BACK_THRESHOLD:
            signal = "bullish"
            label = "Backwardation"
        elif m1_m2 < SIGNAL_FUTURES_CONTANGO_THRESHOLD:
            signal = "bearish"
            label = "Contango"
        else:
            signal = "neutral"
            label = "Flat"

        result = {
            "name": "曲线结构",
            "signal": signal,
            "label": label,
            "source": "futures",
            "m1_m2_spread": round(m1_m2, 4),
        }
        if m1_m6 is not None:
            result["m1_m6_spread"] = round(m1_m6, 4)

        # 附加曲线快照摘要
        curve = futures.get("curve", [])
        if curve:
            result["curve_front"] = curve[0].get("price")
            result["curve_back"] = curve[-1].get("price") if len(curve) > 1 else None
            result["n_contracts"] = len(curve)

        return result

    # ── 回退：WTI-Brent 价差近似 ──
    spread_series = price.get("spread", [])
    if spread_series:
        latest_spread = spread_series[-1]["value"]
        if latest_spread > SIGNAL_BACK_THRESHOLD:
            signal = "bullish"
            label = "Backwardation*"
        elif latest_spread < SIGNAL_CONTANGO_THRESHOLD:
            signal = "bearish"
            label = "Contango*"
        else:
            signal = "neutral"
            label = "Flat*"
    else:
        signal = "neutral"
        label = "N/A"
        latest_spread = 0

    return {
        "name": "曲线结构",
        "signal": signal,
        "label": label,
        "source": "wti_brent_proxy",
        "wti_brent_spread": round(latest_spread, 2) if spread_series else 0,
        "note": "使用 WTI-Brent 跨品种价差近似（无期货数据时回退）",
    }


def demand_signal(demand: dict) -> dict:
    gas = demand.get("gasoline", [])
    dist = demand.get("distillate", [])

    # 比较最近一周 vs 4 周平均
    def _trend(series):
        if len(series) < 5:
            return "neutral"
        latest = series[-1]["value"]
        avg4w = sum(d["value"] for d in series[-5:-1]) / 4
        if latest > avg4w * 1.02:
            return "bullish"
        elif latest < avg4w * 0.98:
            return "bearish"
        return "neutral"

    gas_t = _trend(gas)
    dist_t = _trend(dist)

    if gas_t == "bullish" and dist_t != "bearish":
        signal = "bullish"
    elif gas_t == "bearish" and dist_t == "bearish":
        signal = "bearish"
    else:
        signal = "neutral"

    return {
        "name": "需求强度",
        "signal": signal,
        "gasoline_trend": gas_t,
        "distillate_trend": dist_t,
    }


def drilling_signal(production: dict, drilling: dict) -> dict:
    """钻井活动信号：优先用钻机数（领先指标），回退到产量"""
    rig = drilling.get("rig_count", []) if drilling else []

    if len(rig) >= 4:
        # 用钻机数（更好的领先指标）
        recent = [d["value"] for d in rig[-3:]]
        prev = [d["value"] for d in rig[-6:-3]] if len(rig) >= 6 else recent
        avg_recent = sum(recent) / len(recent)
        avg_prev = sum(prev) / len(prev)
        source = "rig_count"
    else:
        # 回退到产量
        prod = production.get("crude_production", [])
        if len(prod) < 5:
            return {"name": "钻井活动", "signal": "neutral", "source": "none"}
        recent = [d["value"] for d in prod[-4:]]
        prev = [d["value"] for d in prod[-8:-4]] if len(prod) >= 8 else recent
        avg_recent = sum(recent) / len(recent)
        avg_prev = sum(prev) / len(prev)
        source = "production_proxy"

    if avg_prev == 0:
        signal = "neutral"
    elif avg_recent > avg_prev * 1.01:
        signal = "bearish"  # 钻机增加/产量增加 → 利空
    elif avg_recent < avg_prev * 0.99:
        signal = "bullish"  # 钻机减少/产量减少 → 利多
    else:
        signal = "neutral"

    return {
        "name": "钻井活动",
        "signal": signal,
        "source": source,
        "recent_avg": round(avg_recent, 1),
        "prev_avg": round(avg_prev, 1),
    }


def opec_signal(global_bal: dict) -> dict:
    """OPEC/全球供需平衡信号：基于隐含库存变化趋势"""
    balance = global_bal.get("balance", []) if global_bal else []
    if len(balance) < 3:
        return {"name": "全球供需", "signal": "neutral", "source": "none"}

    # 最近 3 个月的供需平衡
    recent = [d["value"] for d in balance[-3:]]
    avg = sum(recent) / len(recent)

    if avg < -0.3:
        signal = "bullish"   # 持续去库 → 供不应求 → 利多
    elif avg > 0.3:
        signal = "bearish"   # 持续累库 → 供过于求 → 利空
    else:
        signal = "neutral"

    # OPEC 产量趋势
    opec = global_bal.get("opec_production", [])
    opec_trend = "stable"
    if len(opec) >= 3:
        r = [d["value"] for d in opec[-3:]]
        p = [d["value"] for d in opec[-6:-3]] if len(opec) >= 6 else r
        if sum(r) / len(r) > sum(p) / len(p) * 1.01:
            opec_trend = "increasing"
        elif sum(r) / len(r) < sum(p) / len(p) * 0.99:
            opec_trend = "decreasing"

    return {
        "name": "全球供需",
        "signal": signal,
        "balance_avg_3m": round(avg, 3),
        "opec_trend": opec_trend,
        "detail": f"近3月平均平衡: {avg:+.3f} 百万桶/日",
    }


def financial_signal(fin: dict) -> dict:
    dxy = fin.get("dxy", [])
    rr = fin.get("real_rate", [])
    ovx = fin.get("ovx", [])

    score = 0
    details = {}

    # DXY vs 200 日均线
    if len(dxy) >= 200:
        ma200 = sum(d["value"] for d in dxy[-200:]) / 200
        latest_dxy = dxy[-1]["value"]
        details["dxy_vs_ma200"] = round(latest_dxy - ma200, 2)
        if latest_dxy > ma200:
            score -= 1
    elif dxy:
        details["dxy_vs_ma200"] = 0

    # 实际利率
    if rr:
        latest_rr = rr[-1]["value"]
        details["real_rate"] = latest_rr
        if latest_rr > SIGNAL_REAL_RATE_HIGH:
            score -= 1

    # OVX
    if ovx:
        latest_ovx = ovx[-1]["value"]
        details["ovx"] = latest_ovx
        if latest_ovx > SIGNAL_OVX_PANIC:
            score -= 1

    if score <= -2:
        signal = "bearish"
    elif score >= 0:
        signal = "bullish"
    else:
        signal = "neutral"

    return {"name": "金融条件", "signal": signal, **details}


def positioning_signal(cftc: list[dict]) -> dict:
    if not cftc:
        return {"name": "持仓拥挤度", "signal": "neutral"}

    net_longs = [d["net_long"] for d in cftc]
    latest = net_longs[-1]
    pct = _pct_rank(latest, net_longs)

    if pct > SIGNAL_POSITIONING_HIGH_PCT:
        signal = "warning"
    elif pct < SIGNAL_POSITIONING_LOW_PCT:
        signal = "bullish"
    else:
        signal = "neutral"

    return {
        "name": "持仓拥挤度",
        "signal": signal,
        "net_long": latest,
        "percentile": pct,
    }


def compute_all_signals():
    inv = _load("inventory.json")
    price = _load("price.json")
    demand = _load("demand.json")
    prod = _load("production.json")
    fin = _load("financial.json")
    futures = _load("futures.json")
    global_bal = _load("global_balance.json")
    drill = _load("drilling.json")

    cftc_path = DATA_DIR / "cftc.json"
    if cftc_path.exists():
        with open(cftc_path) as f:
            cftc = json.load(f)
    else:
        cftc = []

    signals = {
        "inventory": inventory_signal(inv),
        "curve": curve_signal(price, futures),
        "demand": demand_signal(demand),
        "drilling": drilling_signal(prod, drill),
        "opec": opec_signal(global_bal),
        "financial": financial_signal(fin),
        "positioning": positioning_signal(cftc),
    }

    with open(DATA_DIR / "signals.json", "w") as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    print("✓ 信号计算完成")
    return signals


if __name__ == "__main__":
    signals = compute_all_signals()
    for k, v in signals.items():
        emoji = {"bullish": "🟢", "bearish": "🔴", "warning": "⚠️", "neutral": "⚪"}.get(v["signal"], "?")
        print(f"  {emoji} {v['name']}: {v['signal']}")
