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
        emoji = {"bullish": "🟢", "bearish": "🔴", "warning": "⚠️", "neutral": "⚪"}.get(v["signal"], "?")
        print(f"  {emoji} {v['name']}: {v['signal']}")
    print("\n✅ 完成！可以打开 web/index.html 查看 Dashboard")


def run_real():
    print("=" * 50)
    print(f"🛢️  石油数据 ETL — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # FRED
    if config.FRED_API_KEY:
        print("\n[1/4] FRED ...")
        from fetch_fred import fetch_all_fred, save_fred_data
        fred_data = fetch_all_fred()
        save_fred_data(fred_data)
    else:
        print("\n[1/4] FRED — ⚠ 跳过（无 API Key）")

    # EIA
    if config.EIA_API_KEY:
        print("\n[2/4] EIA ...")
        from fetch_eia import fetch_all_eia, save_eia_data
        eia_data = fetch_all_eia()
        save_eia_data(eia_data)
    else:
        print("\n[2/4] EIA — ⚠ 跳过（无 API Key）")

    # CFTC
    print("\n[3/5] CFTC ...")
    try:
        from fetch_cftc import fetch_cftc_positioning, save_cftc_data
        cftc_data = fetch_cftc_positioning()
        save_cftc_data(cftc_data)
        print(f"  → {len(cftc_data)} records")
    except Exception as e:
        print(f"  ✗ {e}")

    # 期货曲线（Yahoo Finance，无需 API Key）
    print("\n[4/5] 期货曲线 ...")
    try:
        from fetch_futures import fetch_futures_data
        futures_data = fetch_futures_data()
        n_contracts = len(futures_data.get("curve", []))
        structure = futures_data.get("structure", "unknown")
        print(f"  → {n_contracts} 合约, 结构: {structure}")
    except Exception as e:
        print(f"  ✗ 期货数据获取失败: {e}")

    # 信号
    print("\n[5/5] 计算信号 ...")
    from compute_signals import compute_all_signals
    signals = compute_all_signals()
    for k, v in signals.items():
        emoji = {"bullish": "🟢", "bearish": "🔴", "warning": "⚠️", "neutral": "⚪"}.get(v["signal"], "?")
        print(f"  {emoji} {v['name']}: {v['signal']}")

    # Meta
    import json
    meta = {
        "last_updated": datetime.now().isoformat(),
        "sources": {
            "fred": "ok" if config.FRED_API_KEY else "skipped",
            "eia": "ok" if config.EIA_API_KEY else "skipped",
            "cftc": "ok",
            "futures": "ok",
        },
    }
    with open(config.DATA_DIR / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print("\n✅ ETL 完成!")


if __name__ == "__main__":
    if "--mock" in sys.argv:
        run_mock()
    else:
        run_real()
