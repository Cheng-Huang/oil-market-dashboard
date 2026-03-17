"""
航运数据交叉验证 — 备选数据源 + IMF PortWatch 多维验证

目的：
  IMF PortWatch (AIS) 在极端事件时可能因 AIS 关闭/覆盖不全产生失真。
  本模块提供多维度交叉验证框架。

数据源：
  1. UNCTAD Liner Shipping Connectivity Index (LSCI) — 免费 API
     - 反映港口连通性，月度指标
  2. Yahoo Finance 运价代理 ETF/股票
     - BDRY (Breakwave Dry Bulk Shipping ETF)
     - VLCCF 等油轮运价关联标的
  3. IMF PortWatch 容量维度 — 利用已有数据的 capacity_tanker 字段做二次验证
  4. 船东盈利数据 — Frontline, Scorpio, DHT, INSW（已有，增强分析）

输出：data/maritime_validation.json
"""
import json
from datetime import datetime, timedelta

import yfinance as yf

from config import DATA_DIR


# ── 运价代理标的 ──────────────────────────────────────
FREIGHT_PROXIES = {
    # 原油运输
    "FRO":  {"name": "Frontline (VLCC)",   "segment": "crude",    "weight": 0.3},
    "DHT":  {"name": "DHT Holdings (VLCC)","segment": "crude",    "weight": 0.2},
    "INSW": {"name": "Intl Seaways",       "segment": "mixed",    "weight": 0.2},
    "STNG": {"name": "Scorpio Tankers",    "segment": "product",  "weight": 0.2},
    # 干散货运价 ETF（间接参考——航运市场整体温度计）
    "BDRY": {"name": "Breakwave Dry Bulk", "segment": "dry_bulk", "weight": 0.1},
}


def fetch_freight_proxy_data(days: int = 90) -> dict:
    """
    获取运价代理标的价格和异常信号。
    油轮股价 + 交易量 可以间接验证航运活跃度。
    """
    tickers = list(FREIGHT_PROXIES.keys())
    print(f"  获取 {len(tickers)} 个运价代理标的...")

    try:
        df = yf.download(tickers, period=f"{days}d", progress=False, group_by="ticker")
    except Exception as e:
        print(f"  ✗ 运价代理下载失败: {e}")
        return {}

    if df.empty:
        return {}

    results = {}
    single_ticker = len(tickers) == 1

    for ticker, info in FREIGHT_PROXIES.items():
        try:
            if single_ticker:
                close = df["Close"].dropna()
                vol = df["Volume"].dropna()
            else:
                close = df[(ticker, "Close")].dropna()
                vol = df[(ticker, "Volume")].dropna()

            if close.empty:
                continue

            prices = [
                {"date": d.strftime("%Y-%m-%d"), "close": round(float(c), 2)}
                for d, c in zip(close.index, close)
            ]
            volumes = [
                {"date": d.strftime("%Y-%m-%d"), "volume": int(v) if v == v else 0}
                for d, v in zip(vol.index, vol)
            ]

            latest = float(close.iloc[-1])
            prev_5d = float(close.iloc[-5]) if len(close) >= 5 else latest
            prev_20d = float(close.iloc[-20]) if len(close) >= 20 else latest

            # 交易量异常检测（近5日 vs 前20日平均）
            vol_values = [int(v) for v in vol if v == v]
            vol_recent = vol_values[-5:] if len(vol_values) >= 5 else vol_values
            vol_avg_20d = sum(vol_values[-20:]) / max(len(vol_values[-20:]), 1)
            vol_recent_avg = sum(vol_recent) / max(len(vol_recent), 1)
            vol_spike = (vol_recent_avg / vol_avg_20d - 1) * 100 if vol_avg_20d > 0 else 0

            results[ticker] = {
                **info,
                "price": round(latest, 2),
                "change_5d_pct": round((latest - prev_5d) / prev_5d * 100, 1),
                "change_20d_pct": round((latest - prev_20d) / prev_20d * 100, 1),
                "volume_spike_pct": round(vol_spike, 1),
                "history": prices[-30:],  # 保留最近30天
            }
            print(f"    ✓ {ticker}: ${latest:.2f} (5d: {results[ticker]['change_5d_pct']:+.1f}%, "
                  f"vol: {vol_spike:+.0f}%)")

        except Exception as e:
            print(f"    ⚠ {ticker}: {e}")

    return results


def _analyze_portwatch_consistency(maritime_file: str = None) -> dict:
    """
    对 IMF PortWatch 已有数据做多维一致性检查：
    1. 油轮数量 vs 总船舶数量 — 是否同步下降
    2. 油轮容量 vs 油轮数量 — 是否一致
    3. 不同咽喉要道之间 — 替代路线效应检测
    """
    if maritime_file is None:
        maritime_file = DATA_DIR / "maritime.json"

    try:
        with open(maritime_file) as f:
            maritime = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"status": "no_data", "message": "maritime.json 不存在或格式错误"}

    checks = []
    chokepoints = maritime.get("chokepoints", {})

    # ── Check 1: 霍尔木兹油轮 vs 总船舶 ──
    hormuz = chokepoints.get("chokepoint6", {})
    if hormuz:
        ts = hormuz.get("tanker_stats", {})
        total_s = hormuz.get("total_stats", {})
        tanker_wow = ts.get("wow_change", 0)
        total_wow = total_s.get("wow_change", 0)

        consistency = "consistent"
        note = ""
        if abs(tanker_wow) > 50 and abs(total_wow) < 20:
            consistency = "inconsistent"
            note = (f"油轮变化 {tanker_wow:.0f}% 但总船舶仅 {total_wow:.0f}% "
                    "→ 可能是船型分类问题或 AIS 标签错误")
        elif abs(tanker_wow - total_wow) < 15:
            consistency = "consistent"
            note = "油轮与总船舶变化幅度一致"

        checks.append({
            "check": "hormuz_tanker_vs_total",
            "tanker_wow": tanker_wow,
            "total_wow": total_wow,
            "consistency": consistency,
            "note": note,
        })

    # ── Check 2: 容量 vs 数量一致性 ──
    if hormuz:
        chart = hormuz.get("chart_data", [])
        if len(chart) >= 14:
            recent = chart[-7:]
            prev = chart[-14:-7]

            avg_tanker_recent = sum(d["tanker"] for d in recent) / 7
            avg_tanker_prev = sum(d["tanker"] for d in prev) / 7
            avg_cap_recent = sum(d.get("capacity_tanker", 0) for d in recent) / 7
            avg_cap_prev = sum(d.get("capacity_tanker", 0) for d in prev) / 7

            tanker_change = ((avg_tanker_recent / avg_tanker_prev - 1) * 100
                             if avg_tanker_prev > 0 else 0)
            cap_change = ((avg_cap_recent / avg_cap_prev - 1) * 100
                          if avg_cap_prev > 0 else 0)

            consistency = "consistent"
            note = ""
            if avg_tanker_recent > 0 and avg_cap_recent == 0:
                consistency = "suspicious"
                note = "有油轮通行但载重量为零 → 可能是空载转运"
            elif abs(tanker_change - cap_change) > 30:
                consistency = "divergent"
                note = (f"油轮数 {tanker_change:.0f}% vs 容量 {cap_change:.0f}% "
                        "→ 船型结构变化")

            checks.append({
                "check": "hormuz_count_vs_capacity",
                "tanker_count_change": round(tanker_change, 1),
                "capacity_change": round(cap_change, 1),
                "consistency": consistency,
                "note": note,
            })

    # ── Check 3: 替代路线效应 ──
    suez = chokepoints.get("chokepoint1", {})
    mandeb = chokepoints.get("chokepoint4", {})
    if hormuz and suez:
        hormuz_wow = hormuz.get("tanker_stats", {}).get("wow_change", 0)
        suez_wow = suez.get("tanker_stats", {}).get("wow_change", 0)

        note = ""
        if hormuz_wow < -50 and suez_wow > 10:
            note = (f"霍尔木兹下降 {hormuz_wow:.0f}% 而苏伊士上升 {suez_wow:.0f}% "
                    "→ 可能反映替代路线效应")
        elif hormuz_wow < -50 and suez_wow < -20:
            note = "霍尔木兹和苏伊士同时下降 → 全球航运整体萎缩或 AIS 系统性问题"

        checks.append({
            "check": "substitute_route_effect",
            "hormuz_wow": hormuz_wow,
            "suez_wow": suez_wow,
            "note": note,
        })

    return {"checks": checks}


def _cross_validate_freight_vs_portwatch(freight_data: dict, maritime_file=None) -> dict:
    """
    将运价代理（油轮股价）与 PortWatch 航运数据交叉验证。
    预期：
      - 封锁 → 运费先涨（供给紧张）→ 后跌（无货可运）
      - 正常波动 → 油轮股价与通行量正相关
    """
    if maritime_file is None:
        maritime_file = DATA_DIR / "maritime.json"

    try:
        with open(maritime_file) as f:
            maritime = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    hormuz = maritime.get("chokepoints", {}).get("chokepoint6", {})
    hormuz_wow = hormuz.get("tanker_stats", {}).get("wow_change", 0) if hormuz else 0

    # 计算加权运价代理变化
    crude_tanker_tickers = ["FRO", "DHT", "INSW"]
    weighted_change = 0
    total_weight = 0
    for tk in crude_tanker_tickers:
        if tk in freight_data:
            w = freight_data[tk]["weight"]
            weighted_change += freight_data[tk]["change_5d_pct"] * w
            total_weight += w
    if total_weight > 0:
        weighted_change /= total_weight

    # 判断一致性
    validation = {
        "hormuz_tanker_wow": hormuz_wow,
        "crude_tanker_stock_5d": round(weighted_change, 1),
    }

    if hormuz_wow < -70:
        if weighted_change > 10:
            validation["interpretation"] = (
                "油轮股价上涨 + 霍尔木兹通行骤降 → "
                "运费飙升阶段（供给中断初期，运价上涨）"
            )
            validation["portwatch_confirmed"] = True
        elif weighted_change < -5:
            validation["interpretation"] = (
                "油轮股价下跌 + 霍尔木兹通行骤降 → "
                "可能已进入'无货可运'阶段，或 PortWatch 数据夸大了封锁程度"
            )
            validation["portwatch_confirmed"] = "partial"
        else:
            validation["interpretation"] = (
                "油轮股价平稳 + 霍尔木兹通行骤降 → "
                "市场已消化封锁预期，或 PortWatch 数据噪声较大"
            )
            validation["portwatch_confirmed"] = "uncertain"
    elif abs(hormuz_wow) < 20:
        validation["interpretation"] = "航运正常波动范围"
        validation["portwatch_confirmed"] = True

    return validation


def fetch_unctad_port_calls() -> dict:
    """
    获取 UNCTAD 港口停靠数据（如果 API 可用）。
    UNCTAD stat API: https://unctadstat-api.unctad.org/
    注意：UNCTAD 数据为月度/季度，用于长期趋势验证而非日频。
    """
    import requests
    # UNCTAD 航运连通性指数 — 反映全球航运网络健康度
    url = "https://unctadstat-api.unctad.org/bulkdownload/US.LSCI/US_LSCI"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            # UNCTAD 返回 CSV，简单解析头几行
            lines = resp.text.strip().split("\n")
            if len(lines) > 1:
                return {
                    "source": "UNCTAD LSCI",
                    "status": "available",
                    "records": len(lines) - 1,
                    "note": "月度数据，仅供长期参考",
                }
        return {"source": "UNCTAD LSCI", "status": "unavailable", "note": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"source": "UNCTAD LSCI", "status": "error", "note": str(e)}


def fetch_and_validate_maritime() -> dict:
    """
    主入口：拉取运价代理 + 对已有数据做多维交叉验证。
    """
    print("  [1] 运价代理标的...")
    freight_data = fetch_freight_proxy_data()

    print("  [2] PortWatch 内部一致性检查...")
    portwatch_checks = _analyze_portwatch_consistency()

    print("  [3] 运价 ↔ PortWatch 交叉验证...")
    cross_validation = _cross_validate_freight_vs_portwatch(freight_data)

    print("  [4] UNCTAD 备选数据源...")
    unctad = fetch_unctad_port_calls()
    print(f"    → UNCTAD: {unctad.get('status', 'unknown')}")

    # 综合可信度评估
    confidence = _assess_overall_confidence(portwatch_checks, cross_validation)

    return {
        "freight_proxies": freight_data,
        "portwatch_consistency": portwatch_checks,
        "cross_validation": cross_validation,
        "unctad": unctad,
        "overall_confidence": confidence,
        "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _assess_overall_confidence(portwatch_checks: dict, cross_validation: dict) -> dict:
    """综合评估航运数据可信度。"""
    issues = []
    score = 100  # 从 100 分开始扣分

    # PortWatch 一致性检查
    for check in portwatch_checks.get("checks", []):
        if check.get("consistency") == "inconsistent":
            issues.append(check.get("note", ""))
            score -= 25
        elif check.get("consistency") == "suspicious":
            issues.append(check.get("note", ""))
            score -= 15
        elif check.get("consistency") == "divergent":
            issues.append(check.get("note", ""))
            score -= 10

    # 交叉验证
    if cross_validation.get("portwatch_confirmed") == "partial":
        issues.append(cross_validation.get("interpretation", ""))
        score -= 15
    elif cross_validation.get("portwatch_confirmed") == "uncertain":
        issues.append(cross_validation.get("interpretation", ""))
        score -= 20

    score = max(0, min(100, score))
    if score >= 80:
        level = "high"
    elif score >= 50:
        level = "medium"
    else:
        level = "low"

    return {
        "score": score,
        "level": level,
        "issues": issues,
    }


def save_maritime_validation(data: dict):
    """保存交叉验证结果。"""
    out_file = DATA_DIR / "maritime_validation.json"
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    confidence = data.get("overall_confidence", {})
    print(f"  ✓ maritime_validation.json "
          f"(可信度: {confidence.get('level', '?')} {confidence.get('score', '?')}/100)")


if __name__ == "__main__":
    print("[航运数据交叉验证]")
    data = fetch_and_validate_maritime()
    save_maritime_validation(data)

    # 打印验证报告
    print("\n[验证报告]")
    confidence = data.get("overall_confidence", {})
    print(f"  综合可信度: {confidence.get('level', 'unknown')} ({confidence.get('score', '?')}/100)")
    for issue in confidence.get("issues", []):
        if issue:
            print(f"  ⚠ {issue}")

    cv = data.get("cross_validation", {})
    if cv.get("interpretation"):
        print(f"\n  [运价 ↔ PortWatch] {cv['interpretation']}")
