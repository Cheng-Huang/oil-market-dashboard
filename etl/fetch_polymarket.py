"""
从 Polymarket Gamma API 获取与石油市场相关的预测市场数据。

策略：Polymarket 没有专门的石油价格市场，但许多地缘政治和宏观事件
      直接影响油价。通过 events 端点获取已知的高相关事件：
  1. 供给侧风险 — 伊朗军事行动、俄乌冲突
  2. 需求侧风险 — 经济衰退
  3. 地缘政治风险 — 北约、中印、以叙关系

使用 Gamma Events API（免费、无需 API Key）：
  GET https://gamma-api.polymarket.com/events?slug=...
"""
import json
import requests
from pathlib import Path

import config

# ── 已知的石油相关事件 (通过 events 端点的 slug 获取) ────
# 每个事件包含多个时间段的子市场，我们取最活跃的
CURATED_EVENTS = {
    "supply_risk": {
        "label": "供给侧风险",
        "events": [
            "us-forces-enter-iran-by",                     # 美军进入伊朗
            "military-action-against-iran-ends-on",        # 对伊朗军事行动结束
        ],
    },
    "demand_risk": {
        "label": "需求侧风险",
        "events": [
            "us-recession-in-2025",                        # 美国经济衰退
        ],
    },
    "geopolitical": {
        "label": "地缘政治",
        "events": [
            "will-russia-invade-a-nato-country-in-2025",   # 俄罗斯入侵北约
            "natoeu-troops-fighting-in-ukraine-in-2025",   # 北约/欧盟出兵乌克兰
            "china-x-india-military-clash-by-december-31", # 中印军事冲突
            "israel-and-syria-normalize-relations-in-2025",# 以叙关系正常化
            "ukraine-election-held-in-2025",               # 乌克兰大选
        ],
    },
}

EVENTS_API = "https://gamma-api.polymarket.com/events"

def _fetch_event(slug):
    """通过 slug 获取单个事件及其子市场。"""
    try:
        resp = requests.get(EVENTS_API, params={"slug": slug}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as e:
        print(f"    ⚠ 获取事件 '{slug}' 失败: {e}")
        return None


def _pick_best_markets(markets):
    """从事件的多个子市场中挑选最佳的（活跃、最高成交量）。"""
    active = [m for m in markets if not m.get("closed") and m.get("active")]
    if not active:
        return []

    # 按成交量排序，返回前 3 个
    active.sort(key=lambda m: float(m.get("volume") or 0), reverse=True)
    return active[:3]


def _parse_market(m, event_slug=""):
    """从原始 API 响应中提取前端需要的字段。"""
    try:
        prices = json.loads(m.get("outcomePrices", "[]"))
        yes_price = float(prices[0]) if len(prices) > 0 else None
    except (json.JSONDecodeError, ValueError, IndexError):
        yes_price = None

    return {
        "id": m.get("id"),
        "question": m.get("question", ""),
        "slug": m.get("slug", ""),
        "yes_price": yes_price,
        "volume": float(m.get("volume") or 0),
        "end_date": (m.get("endDate") or "")[:10],
        "url": f"https://polymarket.com/event/{event_slug}",
    }


def fetch_polymarket_data():
    """
    获取所有已知事件的子市场，按分类整理。

    Returns:
        dict: {
            "categories": {
                "supply_risk": {"label": "...", "markets": [...]},
                ...
            },
            "top_markets": [按成交量排序的所有市场]
        }
    """
    categories = {}
    all_markets = []

    for cat_key, cat_info in CURATED_EVENTS.items():
        cat_markets = []
        for event_slug in cat_info["events"]:
            event = _fetch_event(event_slug)
            if not event:
                continue
            actual_slug = event.get("slug", event_slug)
            markets = event.get("markets", [])
            best = _pick_best_markets(markets)
            for m in best:
                parsed = _parse_market(m, actual_slug)
                if parsed["yes_price"] is not None:
                    cat_markets.append(parsed)

        # 按成交量排序
        cat_markets.sort(key=lambda x: x.get("volume", 0), reverse=True)
        categories[cat_key] = {
            "label": cat_info["label"],
            "markets": cat_markets[:8],
        }
        all_markets.extend(cat_markets)

    # 全局 Top 排序
    all_markets.sort(key=lambda x: x.get("volume", 0), reverse=True)

    return {
        "categories": categories,
        "top_markets": all_markets[:15],
    }


def save_polymarket_data(data):
    out_file = config.DATA_DIR / "polymarket.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    total = sum(len(c["markets"]) for c in data["categories"].values())
    if total == 0:
        print("  ⚠ polymarket.json (0 相关市场 — 所有事件 slug 可能已失效，请检查 CURATED_EVENTS)")
    else:
        print(f"  ✓ polymarket.json ({total} 相关市场)")


# ── CLI 独立运行 ──────────────────────────────────────
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    data = fetch_polymarket_data()
    save_polymarket_data(data)
    for cat_key, cat in data["categories"].items():
        print(f"\n[{cat['label']}]")
        for m in cat["markets"]:
            pct = f"{m['yes_price']:.0%}" if m['yes_price'] is not None else "N/A"
            vol = f"${m['volume']:,.0f}"
            print(f"  {pct} ({vol})  {m['question']}")
