"""
数据验证与覆盖度评估引擎

核心理念：不用模板套数据，而是让数据说话。
1. 盘点每个数据源的实际覆盖范围和新鲜度
2. 评估每个市场研判能否被项目数据交叉验证
3. 识别验证盲区，给出数据获取改进建议
4. 输出 verification.json 供报告生成使用

最终目标：从项目数据中就能比较好地佐证当前市场的研判，
如果佐证不了，告知原因和进一步验证的方案。
"""
import json
from datetime import datetime, timedelta
from typing import Optional
from config import DATA_DIR


def _load(name: str):
    path = DATA_DIR / name
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def _latest_date(series: list) -> Optional[str]:
    """从 [{date, value}...] 中取最新日期"""
    if not series:
        return None
    return series[-1].get("date")


def _staleness_days(date_str: Optional[str], ref_date: Optional[datetime] = None) -> Optional[int]:
    """计算数据滞后天数"""
    if not date_str:
        return None
    ref = ref_date or datetime.now()
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (ref - d).days
    except ValueError:
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第1层：数据源盘点
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def inventory_data_sources() -> dict:
    """盘点所有数据源的覆盖范围、频率、新鲜度"""
    today = datetime.now()
    sources = {}

    # 1. 价格数据
    price = _load("price.json")
    futures = _load("futures.json")
    sources["spot_price"] = {
        "desc": "WTI/Brent 现货价格",
        "origin": "FRED + EIA",
        "frequency": "日频（工作日）",
        "latest": _latest_date(price.get("wti", [])),
        "lag_days": _staleness_days(_latest_date(price.get("wti", [])), today),
        "covers": ["当前油价水平", "WTI-Brent价差", "近期价格趋势"],
        "cannot_cover": ["盘中实时价格", "亚洲/欧洲时段价格"],
    }
    curve = futures.get("curve", [])
    sources["futures_curve"] = {
        "desc": "WTI 期货曲线 (12合约)",
        "origin": "Yahoo Finance",
        "frequency": "日频",
        "latest": curve[0].get("date") if curve else None,
        "lag_days": _staleness_days(curve[0].get("date") if curve else None, today),
        "covers": ["期限结构(Backwardation/Contango)", "远月隐含价格", "近远月价差"],
        "cannot_cover": ["期权隐含波动率曲面", "期货成交量/持仓量分布"],
    }

    # 2. 库存与供给
    inv = _load("inventory.json")
    sources["us_inventory"] = {
        "desc": "美国商业库存 (原油/库欣/汽油/馏分油)",
        "origin": "EIA Weekly",
        "frequency": "周频（每周三发布，截至上周五）",
        "latest": _latest_date(inv.get("crude", [])),
        "lag_days": _staleness_days(_latest_date(inv.get("crude", [])), today),
        "covers": ["美国库存趋势", "库欣交割库水平", "成品油库存方向"],
        "cannot_cover": ["全球库存（OECD/非OECD）", "浮仓库存", "中国SPR"],
    }

    # 3. 需求
    demand = _load("demand.json")
    sources["us_demand"] = {
        "desc": "美国表观需求 (汽油/馏分油)",
        "origin": "EIA Weekly",
        "frequency": "周频",
        "latest": _latest_date(demand.get("gasoline", [])),
        "lag_days": _staleness_days(_latest_date(demand.get("gasoline", [])), today),
        "covers": ["美国汽油需求趋势", "馏分油（柴油）需求趋势"],
        "cannot_cover": ["全球需求（IEA月报才有）", "中国/印度需求", "航空燃油需求"],
    }

    # 4. 裂解价差
    crack = _load("crack_spread.json")
    sources["crack_spread"] = {
        "desc": "裂解价差 (3-2-1, 汽油, 柴油)",
        "origin": "FRED/EIA 价格计算",
        "frequency": "日频",
        "latest": _latest_date(crack.get("crack_321", [])),
        "lag_days": _staleness_days(_latest_date(crack.get("crack_321", [])), today),
        "covers": ["炼厂利润趋势", "汽油vs柴油裂解分化", "成品油供需间接信号"],
        "cannot_cover": ["实际炼厂利润（含运营成本）", "区域性裂解差异（Gulf/East Coast）"],
    }

    # 5. 全球供需
    gb = _load("global_balance.json")
    balance = gb.get("balance", [])
    sources["global_balance"] = {
        "desc": "全球供需平衡 (STEO)",
        "origin": "EIA STEO 月度",
        "frequency": "月频",
        "latest": _latest_date(balance) if balance else None,
        "lag_days": None,  # 月度数据，lag概念不同
        "covers": ["全球供需平衡趋势", "OPEC产量方向", "预测vs实际对比"],
        "cannot_cover": ["实时产量变化", "制裁实际影响量", "战略储备变化"],
    }

    # 6. CFTC 持仓
    cftc = _load("cftc.json") if (DATA_DIR / "cftc.json").exists() else []
    sources["cftc_positioning"] = {
        "desc": "CFTC 投机持仓",
        "origin": "CFTC Disaggregated",
        "frequency": "周频（周五发布，截至周二）",
        "latest": cftc[-1]["date"] if cftc else None,
        "lag_days": _staleness_days(cftc[-1]["date"] if cftc else None, today),
        "covers": ["投机净多头水平", "多空驱动分解", "历史百分位"],
        "cannot_cover": ["日内持仓变化", "dealer/producer持仓细分", "期权持仓"],
    }

    # 7. 金融条件
    fin = _load("financial.json")
    sources["financial"] = {
        "desc": "金融条件 (DXY/OVX/实际利率)",
        "origin": "FRED",
        "frequency": "日频",
        "latest": _latest_date(fin.get("ovx", [])),
        "lag_days": _staleness_days(_latest_date(fin.get("ovx", [])), today),
        "covers": ["美元强弱", "原油波动率水平", "实际利率环境"],
        "cannot_cover": ["美联储政策预期（需CME FedWatch）", "信用利差"],
    }

    # 8. 航运
    maritime = _load("maritime.json")
    sources["maritime"] = {
        "desc": "航运要道通行量 + 油轮股",
        "origin": "IMF PortWatch (ArcGIS) + Yahoo Finance",
        "frequency": "日频",
        "latest": maritime.get("updated", "")[:10] if maritime else None,
        "lag_days": _staleness_days(maritime.get("updated", "")[:10] if maritime else None, today),
        "covers": ["霍尔木兹/曼德/苏伊士/马六甲通行趋势", "油轮股价表现"],
        "cannot_cover": ["单船运价（需Baltic Exchange）", "载重/货物细分", "油轮AIS全覆盖"],
        "data_caveat": "IMF PortWatch 基于AIS数据，可能存在覆盖不全或延迟",
    }

    # 9. 预测市场
    poly = _load("polymarket.json")
    sources["polymarket"] = {
        "desc": "地缘风险预测市场",
        "origin": "Polymarket API",
        "frequency": "实时",
        "latest": poly.get("updated", "")[:10] if isinstance(poly, dict) and poly.get("updated") else None,
        "lag_days": 0 if poly else None,
        "covers": ["市场对地缘事件的概率定价"],
        "cannot_cover": ["概率准确性（校准性差）", "事件实际影响量化"],
        "data_caveat": "Polymarket在地缘事件上的校准性历史上较差，仅作情绪参考",
    }

    # 10. 生产/炼厂
    prod = _load("production.json")
    sources["us_production"] = {
        "desc": "美国产量/炼厂/进口",
        "origin": "EIA Weekly",
        "frequency": "周频",
        "latest": _latest_date(prod.get("crude_production", [])),
        "lag_days": _staleness_days(_latest_date(prod.get("crude_production", [])), today),
        "covers": ["美国产量趋势", "炼厂开工率", "净进口变化"],
        "cannot_cover": ["OPEC各国实时产量", "俄罗斯/伊朗出口量"],
    }

    return sources


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第2层：市场研判 → 数据验证能力评估
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 定义常见市场研判及其验证需求
MARKET_CLAIMS = [
    {
        "id": "supply_disruption",
        "claim": "供给中断（如霍尔木兹封锁、OPEC减产）",
        "verify_with": [
            {"source": "maritime", "field": "霍尔木兹通行量", "weight": "primary",
             "check": "7日均值 vs 90日均值是否显著下降"},
            {"source": "global_balance", "field": "STEO月度供给", "weight": "secondary",
             "check": "供给是否出现异常下降（注意：STEO=产量，运输封锁≠产量下降）"},
            {"source": "futures_curve", "field": "期限结构", "weight": "supporting",
             "check": "是否转为深度Backwardation"},
            {"source": "spot_price", "field": "WTI-Brent价差", "weight": "supporting",
             "check": "Brent溢价是否扩大（国际供给更受影响）"},
        ],
        "cannot_verify": "实际封锁程度和持续时间；需要Kpler/Vortexa等商业航运数据",
        "improve_hint": "接入Kpler或Vortexa的油轮追踪API，可获得按船型、目的地分类的实时贸易流数据",
    },
    {
        "id": "demand_weakness",
        "claim": "需求走弱/衰退风险",
        "verify_with": [
            {"source": "us_demand", "field": "汽油+馏分油表观需求", "weight": "primary",
             "check": "是否连续2-4周低于季节性均值"},
            {"source": "crack_spread", "field": "裂解价差趋势", "weight": "primary",
             "check": "3-2-1裂解是否持续2-4周下行（单日不够）"},
            {"source": "us_inventory", "field": "成品油库存", "weight": "supporting",
             "check": "汽油/馏分油库存是否异常累积"},
            {"source": "us_production", "field": "炼厂开工率", "weight": "supporting",
             "check": "开工率是否主动下调"},
        ],
        "cannot_verify": "全球需求（尤其中国/印度）；美国以外的炼厂利润",
        "improve_hint": "可接入IEA月报API或中国海关进口数据来补充全球需求视角",
    },
    {
        "id": "geopolitical_premium",
        "claim": "地缘风险溢价推高油价",
        "verify_with": [
            {"source": "polymarket", "field": "地缘事件概率", "weight": "supporting",
             "check": "相关事件概率是否显著高于基准"},
            {"source": "financial", "field": "OVX波动率", "weight": "primary",
             "check": "OVX是否远超正常水平（>40为恐慌）"},
            {"source": "futures_curve", "field": "近远月价差", "weight": "primary",
             "check": "近月溢价是否远超远月（地缘驱动的Backwardation）"},
            {"source": "maritime", "field": "航运要道通行量", "weight": "supporting",
             "check": "关键航线是否出现异常"},
        ],
        "cannot_verify": "地缘事件本身的概率和时间线；精确的风险溢价量化",
        "improve_hint": "已有Polymarket，但其校准性差。可考虑接入多个预测市场取平均值",
    },
    {
        "id": "refinery_margin_squeeze",
        "claim": "炼厂利润挤压/减产预期",
        "verify_with": [
            {"source": "crack_spread", "field": "汽油/柴油裂解", "weight": "primary",
             "check": "裂解价差是否持续2-4周低于历史均值"},
            {"source": "us_production", "field": "炼厂开工率", "weight": "primary",
             "check": "开工率是否开始下降"},
            {"source": "us_demand", "field": "需求趋势", "weight": "supporting",
             "check": "需求端是否同步走弱（交叉验证）"},
            {"source": "us_inventory", "field": "成品油库存", "weight": "supporting",
             "check": "成品油是否累库（供大于求证据）"},
        ],
        "cannot_verify": "单个炼厂的实际生产成本和利润",
        "improve_hint": "可接入EIA炼厂月度报告(EIA-820)获取更细粒度的开工率和产率数据",
    },
    {
        "id": "speculative_positioning",
        "claim": "投机资金推动/空头挤压",
        "verify_with": [
            {"source": "cftc_positioning", "field": "净多头+分项变化", "weight": "primary",
             "check": "净多头变化由多头加仓还是空头回补驱动"},
            {"source": "financial", "field": "OVX水平", "weight": "supporting",
             "check": "波动率环境是否有利于投机"},
            {"source": "futures_curve", "field": "持仓量变化", "weight": "supporting",
             "check": "总持仓量是增是减（配合方向看资金行为）"},
        ],
        "cannot_verify": "CTA/量化基金的实时仓位；期权market making对冲需求",
        "improve_hint": "CFTC补充数据(Traders in Financial Futures)可提供更细分的持仓",
    },
    {
        "id": "curve_structure_anomaly",
        "claim": "曲线结构异常（如Backwardation与过剩并存）",
        "verify_with": [
            {"source": "futures_curve", "field": "各月合约价差", "weight": "primary",
             "check": "M1-M2, M1-M6 价差水平和趋势"},
            {"source": "global_balance", "field": "供需平衡", "weight": "primary",
             "check": "实际供需是过剩还是紧缺"},
            {"source": "us_inventory", "field": "库欣库存", "weight": "supporting",
             "check": "交割库库存水平（直接影响近月定价）"},
            {"source": "cftc_positioning", "field": "近月持仓", "weight": "supporting",
             "check": "是否有大量资金集中在近月"},
        ],
        "cannot_verify": "交割库的微观结构（管道调度、存储经济学等）",
        "improve_hint": "可接入CME清算数据获取更精确的期货持仓分布",
    },
    {
        "id": "policy_intervention",
        "claim": "SPR释放/IEA协调/OPEC+政策变化",
        "verify_with": [
            {"source": "us_inventory", "field": "SPR库存水平", "weight": "primary",
             "check": "SPR当前水平和近期变化趋势"},
            {"source": "spot_price", "field": "油价水平", "weight": "supporting",
             "check": "是否超过历史政策干预触发价"},
            {"source": "global_balance", "field": "供需缺口", "weight": "primary",
             "check": "是否存在实体供应缺口（过剩时释放概率低）"},
        ],
        "cannot_verify": "政策决策内部讨论；国际协调时间表；OPEC+实际减产执行率",
        "improve_hint": "可通过爬取DOE/IEA官方新闻or Twitter来获取政策信号的早期提示",
    },
]


def assess_claim_verifiability(sources: dict) -> list[dict]:
    """
    对每个市场研判，评估项目数据的验证能力。
    返回结构化报告：哪些能验证、哪些不能、如何改进。
    """
    results = []

    for claim_def in MARKET_CLAIMS:
        claim_id = claim_def["id"]
        checks = []
        verified_count = 0
        total_primary = 0
        total_checks = len(claim_def["verify_with"])

        for req in claim_def["verify_with"]:
            src_key = req["source"]
            src_data = sources.get(src_key, {})
            is_primary = req["weight"] == "primary"
            if is_primary:
                total_primary += 1

            # 判断数据是否可用且足够新鲜
            lag = src_data.get("lag_days")
            available = lag is not None
            fresh = available and (lag <= 7 if src_data.get("frequency", "").startswith("日") else lag <= 14)

            status = "ok" if (available and fresh) else ("stale" if available else "missing")
            if status == "ok":
                verified_count += 1

            checks.append({
                "source": src_key,
                "field": req["field"],
                "weight": req["weight"],
                "check": req["check"],
                "status": status,
                "lag_days": lag,
                "caveat": src_data.get("data_caveat"),
            })

        # 计算验证能力评级
        primary_ok = sum(1 for c in checks if c["weight"] == "primary" and c["status"] == "ok")
        if primary_ok == total_primary and verified_count >= total_checks * 0.7:
            confidence = "high"
            verdict = "项目数据可以较好地验证此研判"
        elif primary_ok >= 1 and verified_count >= total_checks * 0.5:
            confidence = "medium"
            verdict = "项目数据可以部分验证，但存在盲区"
        else:
            confidence = "low"
            verdict = "项目数据不足以验证此研判，需要补充数据源"

        results.append({
            "claim_id": claim_id,
            "claim": claim_def["claim"],
            "confidence": confidence,
            "verdict": verdict,
            "checks": checks,
            "cannot_verify": claim_def["cannot_verify"],
            "improve_hint": claim_def["improve_hint"],
            "primary_verified": f"{primary_ok}/{total_primary}",
            "total_verified": f"{verified_count}/{total_checks}",
        })

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第3层：数据时效 → 研判可靠性降级
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_temporal_reliability(sources: dict) -> dict:
    """
    评估各数据源的时间错位对整体研判的影响。
    在快速变化的市场中，滞后数据可能导致错误结论。
    """
    today = datetime.now()
    lag_map = {}
    max_lag = 0
    stale_sources = []

    for name, info in sources.items():
        lag = info.get("lag_days")
        if lag is not None:
            lag_map[name] = lag
            if lag > max_lag:
                max_lag = lag
            if lag > 7:
                stale_sources.append({"source": name, "lag": lag, "desc": info["desc"]})

    # 计算"有效分析窗口"——所有数据源共同覆盖的最近日期
    valid_lags = [v for v in lag_map.values() if v is not None]
    effective_window = max(valid_lags) if valid_lags else 0

    # OVX check — 高波动市场中，更短的数据滞后就会造成偏差
    fin = _load("financial.json")
    ovx_data = fin.get("ovx", [])
    ovx_latest = ovx_data[-1]["value"] if ovx_data else 0
    high_vol = ovx_latest > 40

    if high_vol and effective_window > 3:
        reliability = "degraded"
        warning = (
            f"当前OVX={ovx_latest:.1f}（高波动率环境），但数据最大滞后{effective_window}天。"
            f"高波动率下每天价格可能变动3-5%+，{effective_window}天的数据差距意味着"
            f"混合分析可能严重失真。建议：(1)优先依赖最新的数据源(期货/航运)；"
            f"(2)滞后数据仅作为背景参考，不用于方向性判断。"
        )
    elif effective_window > 7:
        reliability = "degraded"
        warning = (
            f"数据最大时间差达{effective_window}天，不同数据源反映的可能是不同的市场状态。"
            f"需谨慎处理跨数据源的结论推导。"
        )
    elif effective_window > 3:
        reliability = "moderate"
        warning = f"数据存在{effective_window}天时差，分析结论需考虑时间错位因素。"
    else:
        reliability = "good"
        warning = None

    return {
        "effective_window_days": effective_window,
        "max_lag_days": max_lag,
        "reliability": reliability,
        "high_volatility": high_vol,
        "ovx": ovx_latest,
        "stale_sources": stale_sources,
        "lag_map": lag_map,
        "warning": warning,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第4层：覆盖度汇总 → 改进建议
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def coverage_gaps_and_improvements(sources: dict, claim_results: list[dict]) -> dict:
    """
    汇总项目数据的覆盖盲区，给出具体的改进建议。
    """
    # 收集所有 cannot_cover
    all_gaps = {}
    for name, info in sources.items():
        for gap in info.get("cannot_cover", []):
            all_gaps[gap] = all_gaps.get(gap, [])
            all_gaps[gap].append(name)

    # 收集不够好的研判
    weak_claims = [c for c in claim_results if c["confidence"] in ("low", "medium")]

    # 生成改进建议（按优先级排序）
    improvements = []

    # A. 最急需：全球需求/非美国数据
    if any("全球需求" in g for g in all_gaps) or any("中国" in g for g in all_gaps):
        improvements.append({
            "priority": "high",
            "area": "全球需求覆盖",
            "current_gap": "仅有美国EIA周度需求数据，缺乏中国/印度/欧洲需求",
            "suggestion": "接入IEA Oil Market Report月度数据 或 中国海关总署原油进口数据",
            "effort": "中等（需要数据源API或爬虫）",
            "value": "可验证'全球需求走弱'研判，当前完全盲区",
        })

    # B. 航运数据质量
    if any(c["claim_id"] == "supply_disruption" and c["confidence"] != "high" for c in claim_results):
        improvements.append({
            "priority": "high",
            "area": "航运数据交叉验证",
            "current_gap": "仅依赖IMF PortWatch (AIS)，数据可能不完整",
            "suggestion": "接入Kpler或Vortexa API获取商业级油轮追踪数据",
            "effort": "高（商业数据源，需付费API）",
            "value": "可准确量化封锁影响的实际贸易流，而非依赖可疑的AIS数据",
        })

    # C. OPEC实时产量
    if any("OPEC各国实时产量" in g for g in all_gaps):
        improvements.append({
            "priority": "medium",
            "area": "OPEC产量跟踪",
            "current_gap": "STEO为月度数据，滞后且可能被修正",
            "suggestion": "接入OPEC月报(MOMR)数据 或 S&P Global Platts产量估算",
            "effort": "中等",
            "value": "可更及时验证减产/增产执行情况",
        })

    # D. 中国SPR/浮仓
    if any("浮仓库存" in g for g in all_gaps):
        improvements.append({
            "priority": "medium",
            "area": "全球库存覆盖",
            "current_gap": "仅有美国EIA库存，缺少全球(尤其中国、浮仓)",
            "suggestion": "接入Kpler浮仓数据 或 IEA月度库存统计",
            "effort": "中-高",
            "value": "可验证'全球库存累积/去库'研判",
        })

    # E. 期权/资金流
    if any("期权" in g for g in all_gaps):
        improvements.append({
            "priority": "low",
            "area": "期权市场数据",
            "current_gap": "缺少期权持仓、隐含波动率曲面、put/call比",
            "suggestion": "接入CME期权数据 或 计算put/call ratio",
            "effort": "中等",
            "value": "可更好理解OVX高企的原因和市场尾部风险定价",
        })

    return {
        "total_gaps": len(all_gaps),
        "weak_claims": len(weak_claims),
        "improvements": improvements,
        "all_gaps_summary": dict(sorted(all_gaps.items(), key=lambda x: -len(x[1]))),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_verification() -> dict:
    """运行完整的数据验证评估，输出 verification.json"""
    print("📋 数据验证与覆盖度评估...")

    # 1. 盘点数据源
    sources = inventory_data_sources()
    print(f"  → {len(sources)} 个数据源")

    # 2. 评估研判验证能力
    claim_results = assess_claim_verifiability(sources)
    high_conf = sum(1 for c in claim_results if c["confidence"] == "high")
    med_conf = sum(1 for c in claim_results if c["confidence"] == "medium")
    low_conf = sum(1 for c in claim_results if c["confidence"] == "low")
    print(f"  → 研判验证: 高置信{high_conf} / 中置信{med_conf} / 低置信{low_conf}")

    # 3. 评估时效可靠性
    temporal = assess_temporal_reliability(sources)
    print(f"  → 时效可靠性: {temporal['reliability']} (最大滞后{temporal['max_lag_days']}天)")

    # 4. 汇总覆盖度和改进建议
    gaps = coverage_gaps_and_improvements(sources, claim_results)
    print(f"  → 覆盖盲区: {gaps['total_gaps']}项, 改进建议: {len(gaps['improvements'])}条")

    result = {
        "sources": sources,
        "claims": claim_results,
        "temporal": temporal,
        "gaps": gaps,
        "generated_at": datetime.now().isoformat(),
    }

    out_path = DATA_DIR / "verification.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("✓ verification.json 已生成")

    return result


if __name__ == "__main__":
    result = run_verification()

    print("\n=== 研判验证能力 ===")
    for c in result["claims"]:
        icon = {"high": "✅", "medium": "⚠️", "low": "❌"}[c["confidence"]]
        print(f"  {icon} [{c['confidence']}] {c['claim']}")
        print(f"     验证覆盖: {c['total_verified']}  |  {c['verdict']}")
        if c["confidence"] != "high":
            print(f"     改进: {c['improve_hint']}")

    print(f"\n=== 时效评估: {result['temporal']['reliability']} ===")
    if result["temporal"]["warning"]:
        print(f"  ⚠️ {result['temporal']['warning']}")

    print("\n=== 优先改进建议 ===")
    for imp in result["gaps"]["improvements"]:
        print(f"  [{imp['priority']}] {imp['area']}: {imp['suggestion']}")
