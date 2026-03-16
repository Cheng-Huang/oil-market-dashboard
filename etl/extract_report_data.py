#!/usr/bin/env python3
"""Extract all data from JSON files for report generation."""
import json, os, sys

DATA = os.path.join(os.path.dirname(__file__), '..', 'data')

def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)

def main():
    # --- Signals ---
    signals = load('signals.json')
    print("=== SIGNALS ===")
    print(json.dumps(signals, indent=2, ensure_ascii=False))

    # --- Prices ---
    price = load('price.json')
    print("\n=== PRICES (last 5) ===")
    for k in ['wti_price', 'brent_price']:
        if k in price:
            print(f"  {k}: {price[k][-5:]}")

    price_eia = load('price_eia.json')
    print("\n=== EIA PRICES (last 3) ===")
    for k in ['wti_price', 'brent_price', 'gasoline_spot_price']:
        if k in price_eia:
            print(f"  {k}: {price_eia[k][-3:]}")

    # --- Inventory ---
    inv = load('inventory.json')
    print("\n=== INVENTORY (last 5 weeks) ===")
    for k in ['crude_inventory', 'cushing_inventory', 'gasoline_inventory', 'distillate_inventory']:
        if k in inv:
            print(f"  {k}: {inv[k][-5:]}")

    # --- Production ---
    prod = load('production.json')
    print("\n=== PRODUCTION (last 5) ===")
    for k in ['crude_production', 'refinery_utilization']:
        if k in prod:
            print(f"  {k}: {prod[k][-5:]}")

    # --- Demand ---
    dem = load('demand.json')
    print("\n=== DEMAND (last 5) ===")
    for k in ['gasoline_demand', 'distillate_demand', 'crude_net_import']:
        if k in dem:
            print(f"  {k}: {dem[k][-5:]}")

    # --- Crack Spread ---
    crack = load('crack_spread.json')
    print("\n=== CRACK SPREAD (last 5) ===")
    print(f"  crack_321: {crack.get('crack_321', [])[-5:]}")
    print(f"  gasoline_crack: {crack.get('gasoline_crack', [])[-5:]}")
    print(f"  diesel_crack: {crack.get('diesel_crack', [])[-5:]}")

    # --- Futures Curve ---
    futures = load('futures.json')
    print("\n=== FUTURES CURVE ===")
    print(f"  curve: {futures.get('curve', [])}")
    hist = futures.get('history', [])
    if hist:
        print(f"  history (last 3): {hist[-3:]}")

    # --- Global Balance ---
    bal = load('global_balance.json')
    print("\n=== GLOBAL BALANCE (last 6) ===")
    for k in ['balance', 'opec_production', 'non_opec_production']:
        if k in bal:
            print(f"  {k}: {bal[k][-6:]}")

    # --- Drilling ---
    drill = load('drilling.json')
    print("\n=== DRILLING (last 6) ===")
    print(f"  us_rig_count: {drill.get('us_rig_count', [])[-6:]}")

    # --- CFTC ---
    cftc = load('cftc.json')
    print("\n=== CFTC (last 5) ===")
    recs = cftc if isinstance(cftc, list) else cftc.get('records', [])
    for r in recs[-5:]:
        print(f"  {r}")

    # --- Financial ---
    fin = load('financial.json')
    print("\n=== FINANCIAL (last 3) ===")
    for k in ['dxy', 'real_rate', 'ovx']:
        if k in fin:
            print(f"  {k}: {fin[k][-3:]}")

    # --- Maritime ---
    mar = load('maritime.json')
    print("\n=== MARITIME ===")
    for cp in mar.get('chokepoints', []):
        name = cp.get('name', '')
        vals = cp.get('values', [])[-3:]
        print(f"  {name}: {vals}")
    print("  tanker_stocks:")
    for ts in mar.get('tanker_stocks', []):
        print(f"    {ts}")

    # --- Polymarket ---
    poly = load('polymarket.json')
    print("\n=== POLYMARKET ===")
    mkts = poly if isinstance(poly, list) else poly.get('markets', [])
    for m in mkts:
        print(f"  [{m.get('category','')}] {m.get('question','')[:60]} => {m.get('outcomes',{})}")

if __name__ == '__main__':
    main()
