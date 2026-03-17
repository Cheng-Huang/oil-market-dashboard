"""
信号计算引擎：根据拉取的数据计算各维度信号
输出 signals.json

证据等级体系：
  A层（直接观测）：现货/期货价格、月差、航运流量、库存、OI/成交量、炼厂开工
  B层（二手确认）：Reuters/IEA/EIA/OPEC报告、企业公告、政府公告
  C层（市场代理）：油轮股、ETF Put/Call、风险资产联动
  D层（推演情景）：概率估计、溢价测算、均衡价

引用规则：
  A/B层 → 可写"事实"
  C层 → 只写"辅助信号"，不当核心证据
  D层 → 只写"情景假设"，附触发/失效条件
"""
import json
from datetime import datetime
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
    SIGNAL_GASOLINE_CRACK_CRITICAL,
    SIGNAL_GASOLINE_CRACK_SHUTDOWN,
    SIGNAL_CRACK_DAILY_DROP_PCT,
    SIGNAL_STEO_MAX_MONTHLY_SUPPLY_CHANGE,
    SIGNAL_SPR_RELEASE_PRICE_TRIGGER,
    SIGNAL_SPR_LOW_LEVEL_KBBL,
    SIGNAL_SPR_MAX_RELEASE_RATE_KBD,
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
        "evidence_tier": "A",
        "evidence_note": "EIA周度库存为直接观测数据",
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
            "evidence_tier": "A",
            "evidence_note": "期货价格为直接市场观测",
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
        "evidence_tier": "A",
        "evidence_note": "EIA表观需求为直接观测（仅覆盖美国）",
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
        "evidence_tier": "A" if source == "rig_count" else "C",
        "evidence_note": "钻机数为直接观测" if source == "rig_count" else "使用产量作为代理指标",
        "source": source,
        "recent_avg": round(avg_recent, 1),
        "prev_avg": round(avg_prev, 1),
    }


def opec_signal(global_bal: dict) -> dict:
    """OPEC/全球供需平衡信号：基于隐含库存变化趋势，区分实际vs预测"""
    balance = global_bal.get("balance", []) if global_bal else []
    if len(balance) < 3:
        return {"name": "全球供需", "signal": "neutral", "source": "none"}

    # 优先使用有 actual/forecast 标注的数据
    has_type = any("type" in d for d in balance)

    if has_type:
        # 分离 actual 和 forecast
        actuals = [d for d in balance if d.get("type") == "actual"]
        forecasts = [d for d in balance if d.get("type") == "forecast"]
        # 使用最近3个月的 actual 数据
        use_data = actuals[-3:] if len(actuals) >= 3 else balance[-3:]
        data_source = "actual" if len(actuals) >= 3 else "mixed"
    else:
        use_data = balance[-3:]
        data_source = "unknown"

    recent = [d["value"] for d in use_data]
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

    # Build supply/demand for report
    supply_demand = []
    for d in use_data:
        entry = {"date": d["date"], "balance": d["value"]}
        if "supply" in d:
            entry["supply"] = d["supply"]
        if "demand" in d:
            entry["demand"] = d["demand"]
        if "type" in d:
            entry["type"] = d["type"]
        supply_demand.append(entry)

    result = {
        "name": "全球供需",
        "signal": signal,
        "evidence_tier": "B" if data_source == "actual" else "D",
        "evidence_note": "STEO实际值为B层二手确认" if data_source == "actual" else "含STEO预测，属D层推演数据",
        "balance_avg_3m": round(avg, 3),
        "opec_trend": opec_trend,
        "data_source": data_source,
        "supply_demand_detail": supply_demand,
        "detail": f"近3月平均平衡: {avg:+.3f} 百万桶/日 (来源: {data_source})",
    }

    # 标注 STEO 预测误差警示
    if data_source in ("forecast", "mixed"):
        result["forecast_caveat"] = "⚠ 含STEO预测数据，历史误差约±100万桶/日"

    return result


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

    return {
        "name": "金融条件",
        "signal": signal,
        "evidence_tier": "A",
        "evidence_note": "DXY/OVX/实际利率为直接市场观测",
        **details,
    }


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

    # 周度变化分析（多头 vs 空头驱动）
    result = {
        "name": "持仓拥挤度",
        "signal": signal,
        "evidence_tier": "A",
        "evidence_note": "CFTC持仓为直接观测（周频，截至周二）",
        "net_long": latest,
        "percentile": pct,
    }

    if len(cftc) >= 2:
        prev = cftc[-2]
        curr = cftc[-1]
        net_change = curr["net_long"] - prev["net_long"]
        long_change = curr.get("long", 0) - prev.get("long", 0)
        short_change = curr.get("short", 0) - prev.get("short", 0)
        result["net_change"] = round(net_change, 0)
        result["long_change"] = round(long_change, 0)
        result["short_change"] = round(short_change, 0)

        # 判断驱动来源
        if abs(short_change) > abs(long_change) * 2 and short_change < 0:
            result["driver"] = "short_squeeze"
            result["driver_note"] = "空头回补驱动，非新多头入场，上涨持续性存疑"
        elif long_change > abs(short_change) * 2 and long_change > 0:
            result["driver"] = "new_longs"
            result["driver_note"] = "新多头入场驱动，看多信心较强"
        else:
            result["driver"] = "mixed"
            result["driver_note"] = "多空双边变动，方向信号不明确"

    # 历史分布上下文
    if len(net_longs) >= 10:
        sorted_vals = sorted(net_longs)
        p25 = sorted_vals[len(sorted_vals) // 4]
        p75 = sorted_vals[3 * len(sorted_vals) // 4]
        result["hist_p25"] = round(p25, 0)
        result["hist_p75"] = round(p75, 0)
        result["context_note"] = (
            f"当前净多仓位于历史{pct:.0f}%分位"
            f"（P25={p25:.0f}, P75={p75:.0f}），"
            f"{'仍有较大上行空间' if pct < 30 else '接近中位水平' if pct < 70 else '拥挤度较高'}"
        )

    return result


def crack_spread_signal(crack: dict, demand_sig: dict) -> dict:
    """
    裂解价差信号：3-2-1 裂解价差反映炼厂利润，是需求端最核心的验证指标。
    
    新增：汽油裂解崩塌检测（交易员反馈 #2）
    - 汽油裂解 < $10 = 炼厂亏损预警
    - 汽油裂解 < $5 = 炼厂减产信号，需求端承接断裂
    - 单日跌幅 > 40% = 裂解崩塌，地缘溢价不可持续的最强基本面信号
    
    与需求信号交叉验证：
    - 需求弱 + 裂解弱 = 确认需求疲软（bearish）
    - 需求弱 + 裂解强 = 可能是炼厂主动减产导致的"假性弱需求"（neutral）
    - 需求强 + 裂解强 = 确认需求旺盛（bullish）
    """
    crack_321 = crack.get("crack_321", [])
    gas_crack = crack.get("gasoline_crack", [])
    diesel_crack = crack.get("diesel_crack", [])

    if not crack_321 or len(crack_321) < 20:
        return {"name": "裂解价差", "signal": "neutral", "detail": "数据不足"}

    latest = crack_321[-1]["value"]
    avg_20d = sum(d["value"] for d in crack_321[-20:]) / 20
    window_60 = crack_321[-60:]
    avg_60d = sum(d["value"] for d in window_60) / len(window_60)

    # 趋势：20日均 vs 60日均
    if avg_20d > avg_60d * 1.05:
        crack_trend = "rising"
    elif avg_20d < avg_60d * 0.95:
        crack_trend = "falling"
    else:
        crack_trend = "flat"

    # 裂解价差绝对水平判断
    if latest > 30:
        level = "high"  # 炼厂高利润
    elif latest < 15:
        level = "low"   # 炼厂利润承压
    else:
        level = "normal"

    # ── 汽油裂解崩塌检测 ──
    gas_latest = gas_crack[-1]["value"] if gas_crack else None
    diesel_latest = diesel_crack[-1]["value"] if diesel_crack else None
    
    collapse_alert = None
    gas_daily_drop_pct = None
    
    if gas_crack and len(gas_crack) >= 2:
        gas_prev = gas_crack[-2]["value"]
        if gas_prev > 0:
            gas_daily_drop_pct = round((gas_prev - gas_latest) / gas_prev * 100, 1)
        
        if gas_latest is not None:
            if gas_latest < SIGNAL_GASOLINE_CRACK_SHUTDOWN:
                collapse_alert = "shutdown"  # 炼厂减产信号
            elif gas_latest < SIGNAL_GASOLINE_CRACK_CRITICAL:
                collapse_alert = "critical"  # 炼厂亏损预警
            
            if gas_daily_drop_pct and gas_daily_drop_pct > SIGNAL_CRACK_DAILY_DROP_PCT:
                if collapse_alert is None:
                    collapse_alert = "collapse"  # 单日崩塌
    
    # 汽油-柴油裂解分化度
    gas_diesel_divergence = None
    if gas_latest is not None and diesel_latest is not None:
        gas_diesel_divergence = round(diesel_latest - gas_latest, 2)

    # 与需求信号交叉验证
    demand_is_weak = demand_sig.get("signal") == "bearish"
    demand_is_strong = demand_sig.get("signal") == "bullish"

    # 崩塌信号优先级最高，但需要标注数据可信度和其他可能原因
    if collapse_alert in ("shutdown", "collapse"):
        signal = "bearish"
        cross_note = (
            f"⚠️ 汽油裂解快速下跌至${gas_latest:.1f}，可能原因包括："
            f"(1)成品油库存结构变化；(2)炼厂检修结束/开工率变化；"
            f"(3)季节性切换（冬→春）；(4)RBOB合约换月；"
            f"(5)终端消费者难以吸收油价上涨。"
            f"当前仅有3天数据支撑，需观察2-4周趋势、成品油库存和炼厂开工率后才能确认。"
        )
    elif collapse_alert == "critical":
        signal = "bearish"
        cross_note = (
            f"⚠️ 汽油裂解接近亏损区（${gas_latest:.1f}），"
            f"可能反映多种因素：库存变化/合约换月/季节性调整。"
            f"若持续2-4周低于${SIGNAL_GASOLINE_CRACK_SHUTDOWN}则预示炼厂利润真实受压。"
        )
    elif demand_is_weak and crack_trend == "falling":
        signal = "bearish"
        cross_note = "需求弱+裂解走低→确认需求疲软"
    elif demand_is_weak and crack_trend in ("rising", "flat") and level != "low":
        signal = "neutral"
        cross_note = "需求弱但裂解未走低→可能是炼厂主动减产导致的假性弱需求"
    elif demand_is_strong and crack_trend == "rising":
        signal = "bullish"
        cross_note = "需求强+裂解走高→确认需求旺盛"
    elif level == "low":
        signal = "bearish"
        cross_note = "裂解价差处于低位，炼厂利润承压"
    elif level == "high":
        signal = "bullish"
        cross_note = "裂解价差处于高位，炼厂利润丰厚"
    else:
        signal = "neutral"
        cross_note = "裂解价差处于正常范围"

    result = {
        "name": "裂解价差",
        "signal": signal,
        "evidence_tier": "A",
        "evidence_note": "裂解价差基于现货/期货价格计算，属直接观测",
        "crack_321": round(latest, 2),
        "crack_321_20d_avg": round(avg_20d, 2),
        "crack_321_60d_avg": round(avg_60d, 2),
        "gasoline_crack": round(gas_latest, 2) if gas_latest else None,
        "diesel_crack": round(diesel_latest, 2) if diesel_latest else None,
        "trend": crack_trend,
        "level": level,
        "cross_validation": cross_note,
        "detail": f"3-2-1: ${latest:.1f} (20d均: ${avg_20d:.1f}, 60d均: ${avg_60d:.1f}), 趋势: {crack_trend}",
    }
    
    # 崩塌相关额外字段
    if collapse_alert:
        result["collapse_alert"] = collapse_alert
    if gas_daily_drop_pct is not None:
        result["gasoline_crack_daily_drop_pct"] = gas_daily_drop_pct
    if gas_diesel_divergence is not None:
        result["gas_diesel_divergence"] = gas_diesel_divergence

    return result


def cross_analysis(curve_sig: dict, opec_sig: dict, maritime: dict, price: dict, futures: dict) -> dict:
    """
    交叉分析：识别信号间的关键矛盾和需要深入讨论的问题。
    - 期限结构 vs 供需平衡 矛盾
    - 海运咽喉要道异常关联
    - 价格-期货时间差分析
    """
    findings = []
    contradictions = []

    # ── 1. 曲线 vs 供需矛盾 ──
    is_backwardation = curve_sig.get("signal") == "bullish"
    is_oversupply = opec_sig.get("signal") == "bearish"
    balance_avg = opec_sig.get("balance_avg_3m", 0)

    if is_backwardation and is_oversupply:
        contradictions.append({
            "type": "curve_vs_balance",
            "severity": "medium",
            "detail": (
                f"深度Backwardation与全球供需过剩({balance_avg:+.1f}百万桶/日)并存。"
                f"两者并非理论上不可共存——Backwardation反映短期供应风险/现货紧张预期"
                f"（地缘溢价、库存结构、运输瓶颈等），而供需过剩反映中长期基本面压力。"
                f"当前Backwardation主要由以下因素驱动：(1)地缘风险溢价；(2)库欣交割库结构；"
                f"(3)近月资金做多。远月曲线更接近基本面均衡价格。"
            ),
        })

    # ── 2. 价格-期货时间差 ──
    wti_series = price.get("wti", [])
    curve = futures.get("curve", []) if futures else []
    if wti_series and curve:
        spot_date = wti_series[-1]["date"]
        spot_price = wti_series[-1]["value"]
        futures_date = curve[0].get("date", "")
        futures_price = curve[0].get("price", 0)
        if spot_date and futures_date and spot_date != futures_date:
            gap = abs(futures_price - spot_price)
            findings.append({
                "type": "price_futures_gap",
                "spot_date": spot_date,
                "spot_price": spot_price,
                "futures_date": futures_date,
                "futures_price": futures_price,
                "gap": round(gap, 2),
                "detail": (
                    f"现货({spot_date})${spot_price} vs 近月期货({futures_date})"
                    f"${futures_price}，差距${gap:.2f}。"
                    f"{'含数据时间差+地缘溢价，需区分两者贡献。' if gap > 5 else ''}"
                ),
            })

    # ── 3. 海运咽喉异常关联 ──
    chokepoints = maritime.get("chokepoints", {}) if maritime else {}
    if chokepoints:
        hormuz = chokepoints.get("chokepoint6", {}).get("tanker_stats", {})
        mandeb = chokepoints.get("chokepoint4", {}).get("tanker_stats", {})
        hormuz_wow = hormuz.get("wow_change", 0)
        mandeb_wow = mandeb.get("wow_change", 0)

        # 霍尔木兹 + 曼德海峡同时骤降：中东出口全面受阻
        if hormuz_wow < -50 and mandeb_wow < -50:
            findings.append({
                "type": "hormuz_mandeb_correlation",
                "severity": "critical",
                "hormuz_wow": hormuz_wow,
                "mandeb_wow": mandeb_wow,
                "detail": (
                    f"霍尔木兹({hormuz_wow:+.1f}%)与曼德海峡({mandeb_wow:+.1f}%)同时骤降，"
                    f"中东原油出口双通道同时受阻，"
                    f"供应中断严重程度远超单一咽喉封锁。"
                ),
            })
        elif hormuz_wow < -50:
            # 数据可信度交叉检查：如果霍尔木兹真的下降>90%，油价应远超当前水平
            hormuz_avg_7d = hormuz.get("avg_7d", 0)
            hormuz_avg_90d = hormuz.get("avg_90d", 0)
            data_plausibility = "plausible"
            if hormuz_wow < -90 and hormuz_avg_7d < 5:
                # 检查油价水平是否与"接近完全封锁"一致
                current_price = None
                if curve:
                    current_price = curve[0].get("price", 0)
                elif wti_series:
                    current_price = wti_series[-1]["value"]
                if current_price and current_price < 120:
                    data_plausibility = "questionable"
                    findings.append({
                        "type": "hormuz_data_plausibility",
                        "severity": "warning",
                        "detail": (
                            f"霍尔木兹油轮通行量数据显示下降{hormuz_wow:+.1f}%"
                            f"（7日均{hormuz_avg_7d:.1f}艘 vs 90日均{hormuz_avg_90d:.1f}艘），"
                            f"但WTI仅${current_price:.0f}。如果全球~25%海运石油真的接近中断，"
                            f"油价应远超$120-150+。数据与价格不一致，可能原因："
                            f"(1) AIS数据统计口径问题（仅计入某类船型）；"
                            f"(2) 数据源覆盖延迟；(3) 部分油轮关闭AIS转发器。"
                            f"建议交叉验证Kpler、Vortexa等商业航运数据。"
                        ),
                    })

            findings.append({
                "type": "hormuz_critical",
                "severity": "critical",
                "data_plausibility": data_plausibility,
                "detail": f"霍尔木兹油轮通行量周环比{hormuz_wow:+.1f}%，属极端事件。",
            })

        # 油轮股 vs 海运数据矛盾
        tanker_stocks = maritime.get("tanker_stocks", [])
        if tanker_stocks and hormuz_wow < -30:
            avg_5d_chg = sum(s.get("change_5d", 0) for s in tanker_stocks) / len(tanker_stocks)
            if avg_5d_chg < -3:  # 油轮股下跌但应该利好
                contradictions.append({
                    "type": "tanker_stock_vs_maritime",
                    "severity": "medium",
                    "evidence_tier": "C",
                    "evidence_note": "油轮股为C层市场代理，仅作辅助信号，不能单独确认供给中断规模",
                    "avg_5d_change": round(avg_5d_chg, 1),
                    "detail": (
                        f"霍尔木兹通行量下降但油轮股5日均跌"
                        f"{avg_5d_chg:.1f}%。与\"封锁导致货源减少\"一致，"
                        f"但也可能反映市场恐慌情绪、流动性收缩或板块轮动等因素。"
                    ),
                })

    return {
        "findings": findings,
        "contradictions": contradictions,
        "n_contradictions": len(contradictions),
    }


def steo_data_validation(global_bal: dict) -> dict:
    """
    STEO 数据异常检测（交易员反馈 #5）：
    当月度供给变化超过合理范围时，标记数据存疑并建议交叉验证。
    例如：月度供给骤降 6 百万桶/日极端罕见，即使霍尔木兹完全封锁也不应如此。
    可能原因：STEO 修正造成的统计口径问题，而非完全的实际供给减少。
    """
    balance = global_bal.get("balance", []) if global_bal else []
    world_prod = global_bal.get("world_production", []) if global_bal else []

    if len(world_prod) < 2:
        return {"has_anomaly": False}

    anomalies = []
    for i in range(1, len(world_prod)):
        prev = world_prod[i - 1]
        curr = world_prod[i]
        change = curr["value"] - prev["value"]
        if abs(change) > SIGNAL_STEO_MAX_MONTHLY_SUPPLY_CHANGE:
            anomalies.append({
                "date": curr["date"],
                "prev_date": prev["date"],
                "supply_change": round(change, 3),
                "prev_supply": round(prev["value"], 3),
                "curr_supply": round(curr["value"], 3),
                "severity": "critical" if abs(change) > 5.0 else "warning",
                "detail": (
                    f"{prev['date']}→{curr['date']} 供给变动 {change:+.2f} 百万桶/日，"
                    f"超过合理阈值 ±{SIGNAL_STEO_MAX_MONTHLY_SUPPLY_CHANGE}。"
                    f"STEO供给=全球产量，产量不会因运输中断瞬间骤降——"
                    f"运输封锁影响的是贸易流向而非产量本身。"
                    f"可能原因：(1) STEO 月度数据修正/统计口径调整；"
                    f"(2) 实际减产（OPEC+主动减产或制裁导致关井）；"
                    f"(3) 数据发布时滞导致的暂时性异常。"
                    f"建议交叉验证 OPEC 月报和 IEA 月报数据。"
                ),
            })

    return {
        "has_anomaly": len(anomalies) > 0,
        "anomalies": anomalies,
    }


def spr_policy_signal(inv: dict, price: dict, futures: dict, maritime: dict) -> dict:
    """
    SPR 释放 & IEA 协调响应评估（交易员反馈 #4）：
    油价超过阈值 + 供给中断 → SPR 释放几乎是必然的政策响应，
    这是打断地缘溢价的最直接催化剂。
    
    评估维度：
    1. SPR 当前库存水平 → 释放空间
    2. 油价水平 → 政策干预动机
    3. 航运中断程度 → 供给紧急度
    4. 历史释放节奏参考
    """
    spr_data = inv.get("spr", [])
    wti = price.get("wti", [])
    curve = futures.get("curve", []) if futures else []
    chokepoints = maritime.get("chokepoints", {}) if maritime else {}

    result = {
        "name": "SPR政策响应",
    }

    # SPR 当前水平
    if spr_data:
        spr_latest = spr_data[-1]["value"]
        spr_date = spr_data[-1]["date"]
        result["spr_level_kbbl"] = spr_latest
        result["spr_date"] = spr_date
        result["spr_low"] = spr_latest < SIGNAL_SPR_LOW_LEVEL_KBBL

        # 近期 SPR 变化趋势（4周）
        if len(spr_data) >= 5:
            recent_changes = [
                spr_data[i]["value"] - spr_data[i - 1]["value"]
                for i in range(len(spr_data) - 4, len(spr_data))
            ]
            result["spr_4w_change"] = round(sum(recent_changes), 0)
            if all(c < 0 for c in recent_changes):
                result["spr_trend"] = "releasing"
            elif all(c > 0 for c in recent_changes):
                result["spr_trend"] = "refilling"
            else:
                result["spr_trend"] = "stable"
    else:
        result["spr_level_kbbl"] = None

    # 油价水平
    current_price = None
    if curve:
        current_price = curve[0].get("price", 0)
    elif wti:
        current_price = wti[-1]["value"]
    result["current_wti"] = current_price

    price_above_trigger = (
        current_price is not None
        and current_price > SIGNAL_SPR_RELEASE_PRICE_TRIGGER
    )

    # 航运中断评估
    hormuz = chokepoints.get("chokepoint6", {}).get("tanker_stats", {})
    hormuz_disrupted = hormuz.get("wow_change", 0) < -50

    # 综合评估 SPR 释放概率
    if price_above_trigger and hormuz_disrupted:
        release_likelihood = "high"
        result["detail"] = (
            f"WTI ${current_price:.0f} 超过政策干预阈值 "
            f"${SIGNAL_SPR_RELEASE_PRICE_TRIGGER}，叠加航运数据显示霍尔木兹通行量异常。"
            f"SPR 释放概率较高，但取决于："
            f"(1)是否存在实体供应缺口（当前STEO显示供需仍为过剩）；"
            f"(2)油价上涨持续时间；(3)政治窗口期。"
            f"历史上SPR释放通常需要明确的实体供给中断，而非仅价格高位。"
        )
    elif price_above_trigger:
        release_likelihood = "moderate"
        result["detail"] = (
            f"WTI ${current_price:.0f} 超过政策干预阈值，"
            f"但当前供需仍为过剩，SPR 释放概率中等，需关注白宫/DOE 政策信号。"
        )
    elif hormuz_disrupted:
        release_likelihood = "moderate"
        result["detail"] = (
            "霍尔木兹严重中断但油价尚在可控范围，"
            "IEA 协调响应可能以预警为主，实际释放视后续价格走势。"
        )
    else:
        release_likelihood = "low"
        result["detail"] = "当前无明显触发 SPR 释放的条件。"

    result["release_likelihood"] = release_likelihood

    # SPR 释放容量估算
    if result.get("spr_level_kbbl") is not None:
        spr_level = result["spr_level_kbbl"]
        max_days_at_full_rate = spr_level / SIGNAL_SPR_MAX_RELEASE_RATE_KBD if spr_level > 0 else 0
        result["max_release_days"] = round(max_days_at_full_rate, 0)
        result["capacity_note"] = (
            f"SPR 当前 {spr_level/1000:.0f} 百万桶，"
            f"按最大速率 {SIGNAL_SPR_MAX_RELEASE_RATE_KBD/1000:.1f} 百万桶/日可持续 {max_days_at_full_rate:.0f} 天。"
        )
        if result["spr_low"]:
            result["capacity_note"] += (
                f" ⚠️ SPR 低于 {SIGNAL_SPR_LOW_LEVEL_KBBL/1000:.0f} 百万桶警戒线，"
                f"释放空间有限，政策可能更审慎。"
            )

    return result


def price_freshness(price: dict, futures: dict) -> dict:
    """计算各数据源的时间新鲜度，标注时间差，并评估时间错位风险。"""
    result = {}
    wti = price.get("wti", [])
    brent = price.get("brent", [])
    curve = futures.get("curve", []) if futures else []
    if wti:
        result["spot_date"] = wti[-1]["date"]
    if curve:
        result["futures_date"] = curve[0].get("date", "")
    if result.get("spot_date") and result.get("futures_date"):
        try:
            d1 = datetime.strptime(result["spot_date"], "%Y-%m-%d")
            d2 = datetime.strptime(result["futures_date"], "%Y-%m-%d")
            result["lag_days"] = abs((d2 - d1).days)
        except ValueError:
            result["lag_days"] = None

    # 评估时间错位风险：在高波动市场中，数据时间差可能导致分析失真
    max_lag = result.get("lag_days", 0) or 0
    if max_lag >= 7:
        result["temporal_risk"] = "high"
        result["temporal_warning"] = (
            f"现货与期货数据相差{max_lag}天。在地缘事件驱动的高波动市场中，"
            f"7天内价格可能大幅变动，混合不同时间的数据得出的结论需保留不确定性。"
        )
    elif max_lag >= 3:
        result["temporal_risk"] = "medium"
        result["temporal_warning"] = (
            f"数据存在{max_lag}天时差，分析结论需考虑时间错位因素。"
        )
    else:
        result["temporal_risk"] = "low"
    return result


def compute_all_signals():
    inv = _load("inventory.json")
    price = _load("price.json")
    demand = _load("demand.json")
    prod = _load("production.json")
    fin = _load("financial.json")
    futures = _load("futures.json")
    global_bal = _load("global_balance.json")
    drill = _load("drilling.json")
    crack = _load("crack_spread.json")
    maritime = _load("maritime.json")

    cftc_path = DATA_DIR / "cftc.json"
    if cftc_path.exists():
        with open(cftc_path) as f:
            cftc = json.load(f)
    else:
        cftc = []

    demand_sig = demand_signal(demand)
    curve_sig = curve_signal(price, futures)
    opec_sig = opec_signal(global_bal)
    crack_sig = crack_spread_signal(crack, demand_sig)

    inv_sig = inventory_signal(inv)
    drill_sig = drilling_signal(prod, drill)
    fin_sig = financial_signal(fin)
    pos_sig = positioning_signal(cftc)

    # 信号评分一致性检查
    scored_signals = [inv_sig, curve_sig, demand_sig, crack_sig, drill_sig, opec_sig, fin_sig, pos_sig]
    score_summary = _score_consistency(scored_signals)

    signals = {
        "inventory": inv_sig,
        "curve": curve_sig,
        "demand": demand_sig,
        "crack_spread": crack_sig,
        "drilling": drill_sig,
        "opec": opec_sig,
        "financial": fin_sig,
        "positioning": pos_sig,
        "cross_analysis": cross_analysis(curve_sig, opec_sig, maritime, price, futures),
        "spr_policy": spr_policy_signal(inv, price, futures, maritime),
        "steo_validation": steo_data_validation(global_bal),
        "price_freshness": price_freshness(price, futures),
        "score_summary": score_summary,
    }

    with open(DATA_DIR / "signals.json", "w") as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    print("✓ 信号计算完成")
    return signals


def _score_consistency(scored_signals: list[dict]) -> dict:
    """
    评分一致性检查：汇总各维度信号，确保总结与评分系统一致。
    不再简单计数，而是区分 '基本面信号' 和 '事件驱动信号'，
    并标注当前市场是由哪种力量主导。
    """
    bullish = 0
    bearish = 0
    neutral = 0
    data_issues = 0

    for sig in scored_signals:
        s = sig.get("signal", "neutral")
        if s == "bullish":
            bullish += 1
        elif s in ("bearish", "warning"):
            bearish += 1
        else:
            neutral += 1

    total = bullish + bearish + neutral
    if total == 0:
        return {"regime": "unknown", "detail": "无信号数据"}

    # 判断市场机制
    if bearish > bullish + 1:
        base_regime = "bearish_leaning"
    elif bullish > bearish + 1:
        base_regime = "bullish_leaning"
    else:
        base_regime = "mixed"

    result = {
        "bullish": bullish,
        "neutral": neutral,
        "bearish": bearish,
        "base_regime": base_regime,
        "regime": base_regime,
    }

    # 如果存在数据可信度问题，降低结论置信度
    for sig in scored_signals:
        if sig.get("collapse_alert") or sig.get("data_confidence") == "low":
            data_issues += 1

    if data_issues > 0:
        result["data_confidence"] = "reduced"
        result["confidence_note"] = (
            f"存在{data_issues}个数据可信度问题，结论置信度降低。"
        )

    # 生成一致性摘要
    if bearish > bullish:
        result["summary"] = (
            f"看多{bullish}/中性{neutral}/看空{bearish} — "
            f"基本面信号偏空，但需区分：如果市场处于事件驱动模式，"
            f"基本面信号权重应降低，方向性结论的置信度有限。"
        )
    elif bullish > bearish:
        result["summary"] = (
            f"看多{bullish}/中性{neutral}/看空{bearish} — "
            f"信号偏多，但需检验是否由单一因素（如地缘风险）主导。"
        )
    else:
        result["summary"] = (
            f"看多{bullish}/中性{neutral}/看空{bearish} — "
            f"多空信号接近均衡，方向不明确，宜维持中性或轻仓。"
        )

    return result


if __name__ == "__main__":
    signals = compute_all_signals()
    for k, v in signals.items():
        if isinstance(v, dict) and "signal" in v:
            emoji = {"bullish": "🟢", "bearish": "🔴", "warning": "⚠️", "neutral": "⚪"}.get(v["signal"], "?")
            print(f"  {emoji} {v['name']}: {v['signal']}")
        elif k == "spr_policy":
            likelihood = v.get("release_likelihood", "unknown")
            emoji = {"very_high": "🚨", "high": "⚠️", "moderate": "⚪", "low": "✅"}.get(likelihood, "?")
            print(f"  {emoji} SPR政策响应: {likelihood}")
        elif k == "steo_validation":
            if v.get("has_anomaly"):
                print(f"  🔶 STEO数据异常: {len(v.get('anomalies', []))} 个异常点")
            else:
                print(f"  ✓ STEO数据: 无异常")
