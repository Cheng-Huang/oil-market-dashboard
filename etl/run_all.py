"""
ETL 入口：运行所有数据拉取 + 信号计算
用法:
  python run_all.py          # 真实 API 拉取
  python run_all.py --mock   # 生成模拟数据
"""
import sys
import os
from datetime import datetime
from pathlib import Path

# 确保从 etl/ 目录运行时也能找到模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# 重新导入 config（让 .env 生效）
import config
config.EIA_API_KEY = os.getenv("EIA_API_KEY", "")
config.FRED_API_KEY = os.getenv("FRED_API_KEY", "")


def run_mock():
    print("=" * 50)
    print("🔧 生成模拟数据 ...")
    print("=" * 50)
    from generate_mock import generate_mock_data
    generate_mock_data()

    print("\n📊 计算信号 ...")
    from compute_signals import compute_all_signals
    signals = compute_all_signals()
    for k, v in signals.items():
        if isinstance(v, dict) and "signal" in v:
            emoji = {"bullish": "🟢", "bearish": "🔴", "warning": "⚠️", "neutral": "⚪"}.get(v["signal"], "?")
            print(f"  {emoji} {v['name']}: {v['signal']}")
    print("\n✅ 完成！可以打开 web/index.html 查看 Dashboard")


def _fix_price_freshness():
    """
    FRED 价格可能滞后 EIA 数天。
    如果 price_eia.json 有比 price.json 更新的数据点，追加到 price.json。
    同时记录各数据源最新日期，供报告标注时间差。
    """
    import json
    price_file = config.DATA_DIR / "price.json"
    eia_file = config.DATA_DIR / "price_eia.json"

    if not price_file.exists() or not eia_file.exists():
        return

    try:
        with open(price_file) as f:
            price = json.load(f)
        with open(eia_file) as f:
            eia_price = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return

    updated = False
    for key in ["wti", "brent"]:
        fred_data = price.get(key, [])
        eia_data = eia_price.get(key, [])
        if not fred_data or not eia_data:
            continue

        fred_latest_date = fred_data[-1]["date"]
        # Find EIA points newer than FRED latest
        new_points = [p for p in eia_data if p["date"] > fred_latest_date]
        if new_points:
            fred_data.extend(new_points)
            fred_data.sort(key=lambda x: x["date"])
            price[key] = fred_data
            updated = True
            print(f"  ✓ {key}: 用 EIA 补齐 {len(new_points)} 个更新数据点 "
                  f"({fred_latest_date} → {new_points[-1]['date']})")

    if updated:
        # Recompute spread
        if price.get("wti") and price.get("brent"):
            brent_map = {d["date"]: d["value"] for d in price["brent"]}
            price["spread"] = [
                {"date": d["date"], "value": round(d["value"] - brent_map[d["date"]], 4)}
                for d in price["wti"]
                if d["date"] in brent_map
            ]
        with open(price_file, "w") as f:
            json.dump(price, f, indent=2)


def _fix_crack_spread(fred_data, eia_data):
    """FRED 汽油价格失效时，用 EIA 汽油现货价格重算裂解价差"""
    import json
    crack_file = config.DATA_DIR / "crack_spread.json"
    try:
        with open(crack_file) as f:
            crack = json.load(f)
        if crack.get("crack_321"):
            return  # 已有数据，无需修补
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    wti = fred_data.get("wti_price", [])
    gasoline = eia_data.get("gasoline_spot_price", [])
    heating_oil = fred_data.get("heating_oil_price", [])

    if not (wti and gasoline and heating_oil):
        return

    from fetch_fred import _compute_crack_spread
    crack_321, crack_gas, crack_diesel = _compute_crack_spread(wti, gasoline, heating_oil)
    crack_spread = {
        "crack_321": crack_321,
        "gasoline_crack": crack_gas,
        "diesel_crack": crack_diesel,
    }
    with open(crack_file, "w") as f:
        json.dump(crack_spread, f, indent=2)
    print(f"  ✓ 裂解价差已用 EIA 汽油现货重算 ({len(crack_321)} 天)")


def run_real():
    print("=" * 50)
    print(f"🛢️  石油数据 ETL — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # FRED
    fred_data = {}
    if config.FRED_API_KEY:
        print("\n[1/9] FRED ...")
        from fetch_fred import fetch_all_fred, save_fred_data
        fred_data = fetch_all_fred()
        save_fred_data(fred_data)
    else:
        print("\n[1/9] FRED — ⚠ 跳过（无 API Key）")

    # EIA
    eia_data = {}
    if config.EIA_API_KEY:
        print("\n[2/9] EIA ...")
        from fetch_eia import fetch_all_eia, save_eia_data
        eia_data = fetch_all_eia()
        save_eia_data(eia_data)
    else:
        print("\n[2/9] EIA — ⚠ 跳过（无 API Key）")

    # ── 裂解价差补救：FRED 汽油价格失效时，用 EIA 汽油现货替代 ──
    _fix_crack_spread(fred_data, eia_data)

    # ── 价格新鲜度补救：FRED 价格滞后时，用 EIA 日度价格补齐 ──
    _fix_price_freshness()

    # STEO (OPEC/全球供需 + 钻机数)
    if config.EIA_API_KEY:
        print("\n[3/9] STEO (全球供需 & 钻井) ...")
        try:
            from fetch_steo import fetch_all_steo, save_steo_data
            steo_data = fetch_all_steo()
            save_steo_data(steo_data)
        except Exception as e:
            print(f"  ✗ STEO 数据获取失败: {e}")
    else:
        print("\n[3/9] STEO — ⚠ 跳过（无 EIA API Key）")

    # CFTC
    print("\n[4/9] CFTC ...")
    try:
        from fetch_cftc import fetch_cftc_positioning, save_cftc_data
        cftc_data = fetch_cftc_positioning()
        save_cftc_data(cftc_data)
        print(f"  → {len(cftc_data)} records")
    except Exception as e:
        print(f"  ✗ {e}")

    # 期货曲线（Yahoo Finance，无需 API Key）
    print("\n[5/9] 期货曲线 ...")
    try:
        from fetch_futures import fetch_futures_data
        futures_data = fetch_futures_data()
        n_contracts = len(futures_data.get("curve", []))
        structure = futures_data.get("structure", "unknown")
        print(f"  → {n_contracts} 合约, 结构: {structure}")
    except Exception as e:
        print(f"  ✗ 期货数据获取失败: {e}")

    # Polymarket 预测市场（免费，无需 API Key）
    print("\n[6/9] Polymarket 预测市场 ...")
    try:
        from fetch_polymarket import fetch_polymarket_data, save_polymarket_data
        poly_data = fetch_polymarket_data()
        save_polymarket_data(poly_data)
    except Exception as e:
        print(f"  ✗ Polymarket 数据获取失败: {e}")

    # 航运数据（IMF PortWatch + Yahoo Finance，免费，无需 API Key）
    print("\n[7/9] 航运数据 (IMF PortWatch) ...")
    try:
        from fetch_maritime import fetch_maritime_data, save_maritime_data
        maritime_data = fetch_maritime_data()
        save_maritime_data(maritime_data)
    except Exception as e:
        print(f"  ✗ 航运数据获取失败: {e}")

    # 信号
    print("\n[8/9] 计算信号 ...")
    from compute_signals import compute_all_signals
    signals = compute_all_signals()
    for k, v in signals.items():
        if isinstance(v, dict) and "signal" in v:
            emoji = {"bullish": "🟢", "bearish": "🔴", "warning": "⚠️", "neutral": "⚪"}.get(v["signal"], "?")
            print(f"  {emoji} {v['name']}: {v['signal']}")
            # 裂解价差崩塌特殊提示
            if k == "crack_spread" and v.get("collapse_alert"):
                print(f"    🚨 汽油裂解崩塌预警: {v['collapse_alert']} (${v.get('gasoline_crack', '?')})")
        elif k == "cross_analysis":
            n = v.get("n_contradictions", 0)
            print(f"  {'🔶' if n > 0 else '✓'} 交叉分析: {n} 个矛盾信号")
        elif k == "spr_policy":
            likelihood = v.get("release_likelihood", "unknown")
            emoji = {"very_high": "🚨", "high": "⚠️", "moderate": "⚪", "low": "✅"}.get(likelihood, "?")
            print(f"  {emoji} SPR政策响应: {likelihood}")
        elif k == "steo_validation":
            if v.get("has_anomaly"):
                n = len(v.get("anomalies", []))
                print(f"  🔶 STEO数据验证: {n} 个异常数据点需要交叉验证")
            else:
                print(f"  ✓ STEO数据验证: 正常")
        elif k == "price_freshness":
            lag = v.get("lag_days")
            if lag and lag > 3:
                print(f"  ⚠️ 价格新鲜度: 现货 vs 期货滞后 {lag} 天")
            else:
                print(f"  ✓ 价格新鲜度: 正常")

    # Meta
    print("\n[9/9] 写入元信息 ...")
    import json
    meta = {
        "last_updated": datetime.now().isoformat(),
        "sources": {
            "fred": "ok" if config.FRED_API_KEY else "skipped",
            "eia": "ok" if config.EIA_API_KEY else "skipped",
            "cftc": "ok",
            "futures": "ok",
            "steo": "ok" if config.EIA_API_KEY else "skipped",
            "polymarket": "ok",
            "maritime": "ok",
        },
    }
    with open(config.DATA_DIR / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    # 数据验证评估
    print("\n[10] 数据验证与覆盖度评估 ...")
    try:
        from data_verification import run_verification
        verification = run_verification()
    except Exception as e:
        print(f"  ✗ 数据验证失败: {e}")

    print("\n✅ ETL 完成!")


if __name__ == "__main__":
    if "--mock" in sys.argv:
        run_mock()
    else:
        run_real()
