"""
CME 原油期权数据 — Put/Call Ratio 极端情绪监控

数据源：
  1. Yahoo Finance — USO/XLE ETF 期权链 (CL=F 期货期权不可用，ETF 作代理)
     - Put/Call ratio, 隐含波动率(IV), 最大持仓量 strike
  2. OVX（已在 FRED 中获取，此处做增强分析）
  3. 期权到期日 Gamma 暴露估算

输出：data/options.json
"""
import json
from datetime import datetime, timedelta

import yfinance as yf

from config import DATA_DIR


def fetch_options_data() -> dict:
    """
    从 Yahoo Finance 获取原油相关 ETF 期权链数据。
    CL=F 期货期权在 Yahoo Finance 不可用，改用 USO/XLE 作代理。
    计算 Put/Call Ratio 和关键 strike 分布。
    """
    print("  获取原油期权链 (USO ETF + XLE 作代理)...")
    result = {
        "by_ticker": {},
        "by_expiry": [],
        "aggregate": {},
        "sentiment": {},
    }

    oil_option_tickers = [
        ("USO", "United States Oil Fund ETF"),
        ("XLE", "Energy Select Sector SPDR"),
    ]

    # 跨所有 ticker 的汇总
    grand_puts_volume = 0
    grand_calls_volume = 0
    grand_puts_oi = 0
    grand_calls_oi = 0
    all_expiry_analysis = []

    for ticker_sym, label in oil_option_tickers:
        print(f"  ↳ {ticker_sym} ({label})...")
        try:
            ticker = yf.Ticker(ticker_sym)
            expirations = ticker.options
            if not expirations:
                print(f"    ⚠ {ticker_sym}: 无可用期权到期日")
                continue

            print(f"    → {len(expirations)} 个到期日可用")

            ticker_puts_vol = 0
            ticker_calls_vol = 0
            ticker_puts_oi = 0
            ticker_calls_oi = 0
            ticker_expiries = []

            for exp in expirations[:4]:
                try:
                    chain = ticker.option_chain(exp)
                    calls = chain.calls
                    puts = chain.puts

                    if calls.empty and puts.empty:
                        continue

                    call_vol = int(calls["volume"].sum()) if "volume" in calls.columns else 0
                    put_vol = int(puts["volume"].sum()) if "volume" in puts.columns else 0
                    pc_vol = round(put_vol / call_vol, 3) if call_vol > 0 else 0

                    call_oi = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
                    put_oi = int(puts["openInterest"].sum()) if "openInterest" in puts.columns else 0
                    pc_oi = round(put_oi / call_oi, 3) if call_oi > 0 else 0

                    ticker_puts_vol += put_vol
                    ticker_calls_vol += call_vol
                    ticker_puts_oi += put_oi
                    ticker_calls_oi += call_oi

                    max_call_strike = None
                    max_put_strike = None
                    if not calls.empty and "openInterest" in calls.columns:
                        valid_calls = calls.dropna(subset=["openInterest"])
                        if not valid_calls.empty:
                            max_call_strike = float(valid_calls.loc[valid_calls["openInterest"].idxmax(), "strike"])
                    if not puts.empty and "openInterest" in puts.columns:
                        valid_puts = puts.dropna(subset=["openInterest"])
                        if not valid_puts.empty:
                            max_put_strike = float(valid_puts.loc[valid_puts["openInterest"].idxmax(), "strike"])

                    iv_calls = float(calls["impliedVolatility"].mean()) if "impliedVolatility" in calls.columns else 0
                    iv_puts = float(puts["impliedVolatility"].mean()) if "impliedVolatility" in puts.columns else 0
                    iv_skew = round(iv_puts - iv_calls, 4) if iv_puts and iv_calls else 0

                    expiry_info = {
                        "ticker": ticker_sym,
                        "expiry": exp,
                        "pc_ratio_volume": pc_vol,
                        "pc_ratio_oi": pc_oi,
                        "total_call_volume": call_vol,
                        "total_put_volume": put_vol,
                        "total_call_oi": call_oi,
                        "total_put_oi": put_oi,
                        "max_call_oi_strike": max_call_strike,
                        "max_put_oi_strike": max_put_strike,
                        "avg_iv_calls": round(iv_calls, 4),
                        "avg_iv_puts": round(iv_puts, 4),
                        "iv_skew": iv_skew,
                    }
                    ticker_expiries.append(expiry_info)
                    all_expiry_analysis.append(expiry_info)

                    print(f"    {exp}: P/C(vol)={pc_vol:.2f} P/C(OI)={pc_oi:.2f} "
                          f"maxPut=${max_put_strike} maxCall=${max_call_strike}")

                except Exception as e:
                    print(f"    ⚠ {exp}: {e}")

            # 单 ticker 汇总
            t_pc_vol = round(ticker_puts_vol / ticker_calls_vol, 3) if ticker_calls_vol > 0 else 0
            t_pc_oi = round(ticker_puts_oi / ticker_calls_oi, 3) if ticker_calls_oi > 0 else 0
            result["by_ticker"][ticker_sym] = {
                "label": label,
                "pc_ratio_volume": t_pc_vol,
                "pc_ratio_oi": t_pc_oi,
                "total_call_volume": ticker_calls_vol,
                "total_put_volume": ticker_puts_vol,
                "total_call_oi": ticker_calls_oi,
                "total_put_oi": ticker_puts_oi,
                "expiries_analyzed": len(ticker_expiries),
            }

            grand_puts_volume += ticker_puts_vol
            grand_calls_volume += ticker_calls_vol
            grand_puts_oi += ticker_puts_oi
            grand_calls_oi += ticker_calls_oi

        except Exception as e:
            print(f"  ✗ {ticker_sym} 期权获取失败: {e}")

    # 跨 ticker 汇总
    result["by_expiry"] = all_expiry_analysis
    total_pc_vol = round(grand_puts_volume / grand_calls_volume, 3) if grand_calls_volume > 0 else 0
    total_pc_oi = round(grand_puts_oi / grand_calls_oi, 3) if grand_calls_oi > 0 else 0

    result["aggregate"] = {
        "total_pc_ratio_volume": total_pc_vol,
        "total_pc_ratio_oi": total_pc_oi,
        "total_call_volume": grand_calls_volume,
        "total_put_volume": grand_puts_volume,
        "total_call_oi": grand_calls_oi,
        "total_put_oi": grand_puts_oi,
    }

    result["sentiment"] = _assess_option_sentiment(total_pc_vol, total_pc_oi, all_expiry_analysis)

    return result


def _assess_option_sentiment(pc_vol, pc_oi, by_expiry) -> dict:
    """
    评估基于期权的市场情绪。

    P/C Ratio 参考:
      < 0.7  → 极度看多（可能过热）
      0.7-1.0 → 正常偏多
      1.0-1.2 → 中性
      1.2-1.5 → 偏空/谨慎
      > 1.5  → 极度看空/恐慌对冲
    """
    assessment = {}

    # Volume P/C
    if pc_vol > 0:
        if pc_vol < 0.7:
            assessment["volume_signal"] = "extreme_bullish"
            assessment["volume_note"] = f"P/C(vol)={pc_vol:.2f} 极度看多，可能反转风险"
        elif pc_vol < 1.0:
            assessment["volume_signal"] = "bullish"
            assessment["volume_note"] = f"P/C(vol)={pc_vol:.2f} 偏多"
        elif pc_vol < 1.2:
            assessment["volume_signal"] = "neutral"
            assessment["volume_note"] = f"P/C(vol)={pc_vol:.2f} 中性"
        elif pc_vol < 1.5:
            assessment["volume_signal"] = "bearish"
            assessment["volume_note"] = f"P/C(vol)={pc_vol:.2f} 偏空/谨慎"
        else:
            assessment["volume_signal"] = "extreme_bearish"
            assessment["volume_note"] = f"P/C(vol)={pc_vol:.2f} 极度看空/恐慌对冲"

    # OI P/C
    if pc_oi > 0:
        if pc_oi < 0.7:
            assessment["oi_signal"] = "extreme_bullish"
        elif pc_oi < 1.0:
            assessment["oi_signal"] = "bullish"
        elif pc_oi < 1.2:
            assessment["oi_signal"] = "neutral"
        elif pc_oi < 1.5:
            assessment["oi_signal"] = "bearish"
        else:
            assessment["oi_signal"] = "extreme_bearish"

    # IV skew 分析
    if by_expiry:
        near_month = by_expiry[0]
        skew = near_month.get("iv_skew", 0)
        if skew > 0.1:
            assessment["skew_signal"] = "put_premium"
            assessment["skew_note"] = (
                f"Put IV 显著高于 Call IV (skew={skew:.3f}) "
                "→ 市场在积极买入下行保护"
            )
        elif skew < -0.1:
            assessment["skew_signal"] = "call_premium"
            assessment["skew_note"] = "Call IV 偏高 → 投机性做多活跃"
        else:
            assessment["skew_signal"] = "balanced"

    # 关键 strike 水平（从最大 OI 推断支撑/阻力）
    if by_expiry:
        max_put_strikes = [e["max_put_oi_strike"] for e in by_expiry if e.get("max_put_oi_strike")]
        max_call_strikes = [e["max_call_oi_strike"] for e in by_expiry if e.get("max_call_oi_strike")]
        if max_put_strikes:
            assessment["key_put_support"] = max(max_put_strikes)  # 最高的 put strike = 下方支撑
        if max_call_strikes:
            assessment["key_call_resistance"] = min(max_call_strikes)  # 最低的 call strike = 上方阻力

    return assessment


def fetch_ovx_enhanced() -> dict:
    """
    增强 OVX 分析：读取已有 financial.json 中的 OVX 数据，
    计算 OVX 百分位、趋势、波动率的波动率。
    """
    fin_file = DATA_DIR / "financial.json"
    try:
        with open(fin_file) as f:
            financial = json.load(f)
        ovx = financial.get("ovx", [])
        if len(ovx) < 20:
            return {}

        values = [d["value"] for d in ovx]
        latest = values[-1]
        avg_20d = sum(values[-20:]) / min(len(values), 20)
        avg_60d = sum(values[-60:]) / min(len(values), 60)

        # OVX 百分位（相对近2年）
        sorted_values = sorted(values)
        percentile = (sorted_values.index(latest) / len(sorted_values) * 100
                      if latest in sorted_values else 50)

        # OVX 变化率（vol of vol）
        if len(values) >= 5:
            changes = [abs(values[i] - values[i-1]) / values[i-1] * 100
                       for i in range(-5, 0) if values[i-1] > 0]
            vol_of_vol = sum(changes) / len(changes) if changes else 0
        else:
            vol_of_vol = 0

        return {
            "latest": round(latest, 2),
            "date": ovx[-1]["date"],
            "avg_20d": round(avg_20d, 2),
            "avg_60d": round(avg_60d, 2),
            "percentile": round(percentile, 1),
            "vol_of_vol_5d": round(vol_of_vol, 1),
            "regime": (
                "extreme_panic" if latest > 80 else
                "panic" if latest > 40 else
                "elevated" if latest > 25 else
                "normal"
            ),
        }
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def fetch_all_options_data() -> dict:
    """主入口：获取期权+波动率完整数据包。"""
    print("  [1] WTI 期货期权链...")
    options = fetch_options_data()

    print("  [2] OVX 增强分析...")
    ovx = fetch_ovx_enhanced()
    if ovx:
        print(f"    → OVX={ovx.get('latest','?')} ({ovx.get('regime','?')}) "
              f"百分位={ovx.get('percentile','?')}%")

    # 合并
    return {
        "options": options,
        "ovx_enhanced": ovx,
        "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def save_options_data(data: dict):
    """保存期权数据。"""
    out_file = DATA_DIR / "options.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    agg = data.get("options", {}).get("aggregate", {})
    sentiment = data.get("options", {}).get("sentiment", {})
    pc = agg.get("total_pc_ratio_volume", "?")
    sig = sentiment.get("volume_signal", "?")
    print(f"  ✓ options.json (P/C={pc}, 情绪={sig})")


if __name__ == "__main__":
    print("[期权数据 & Put/Call Ratio]")
    data = fetch_all_options_data()
    save_options_data(data)

    # 打印情绪报告
    sentiment = data.get("options", {}).get("sentiment", {})
    if sentiment:
        print("\n[期权情绪]")
        for k, v in sentiment.items():
            if "_note" in k:
                print(f"  {v}")
        support = sentiment.get("key_put_support")
        resist = sentiment.get("key_call_resistance")
        if support or resist:
            print(f"  期权支撑: ${support}, 期权阻力: ${resist}")
