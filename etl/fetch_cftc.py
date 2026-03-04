"""
从 CFTC 公开数据拉取 WTI 原油投机持仓数据
使用 Socrata Open Data API (无需 API Key)
"""
import json
import requests
from config import CFTC_ENDPOINT, CFTC_CONTRACT_CODE, DATA_DIR


def fetch_cftc_positioning(limit: int = 200) -> list[dict]:
    """
    拉取 CFTC Disaggregated COT 数据（WTI 原油）
    返回 [{date, net_long, long, short, open_interest}, ...]
    """
    params = {
        "$where": f"cftc_contract_market_code='{CFTC_CONTRACT_CODE}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": limit,
        "$select": (
            "report_date_as_yyyy_mm_dd,"
            "m_money_positions_long_all,"
            "m_money_positions_short_all,"
            "open_interest_all"
        ),
    }
    resp = requests.get(CFTC_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    rows = resp.json()

    result = []
    for r in rows:
        try:
            mm_long = float(r.get("m_money_positions_long_all", 0))
            mm_short = float(r.get("m_money_positions_short_all", 0))
            oi = float(r.get("open_interest_all", 0))
            date_raw = r.get("report_date_as_yyyy_mm_dd", "")
            result.append({
                "date": date_raw[:10],
                "net_long": mm_long - mm_short,
                "long": mm_long,
                "short": mm_short,
                "open_interest": oi,
            })
        except (ValueError, TypeError, KeyError):
            pass
    result.sort(key=lambda x: x["date"])
    return result


def save_cftc_data(data: list[dict]):
    with open(DATA_DIR / "cftc.json", "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    print("  CFTC: WTI 投机持仓 ...")
    try:
        data = fetch_cftc_positioning()
        save_cftc_data(data)
        print(f"    → {len(data)} records")
        print("✓ CFTC 数据已保存")
    except Exception as e:
        print(f"    ✗ 失败: {e}")
