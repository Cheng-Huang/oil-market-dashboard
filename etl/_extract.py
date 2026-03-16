import json, os
D = os.path.join(os.path.dirname(__file__), '..', 'data')
def ld(f):
    with open(os.path.join(D, f)) as fh: return json.load(fh)

p = ld('price.json'); pe = ld('price_eia.json')
print('=== PRICES ===')
for k in ['wti','brent','spread']:
    if k in p: print(f'  FRED {k}:', p[k][-3:])
for k in ['wti','brent']:
    if k in pe: print(f'  EIA {k}:', pe[k][-3:])

inv = ld('inventory.json')
print('\n=== INVENTORY ===')
for k in ['crude','cushing','gasoline','distillate']:
    if k in inv: print(f'  {k}:', inv[k][-6:])

dem = ld('demand.json')
print('\n=== DEMAND ===')
for k in ['gasoline','distillate']:
    if k in dem: print(f'  {k}:', dem[k][-6:])

prod = ld('production.json')
print('\n=== PRODUCTION ===')
for k in prod:
    v = prod[k]
    if isinstance(v, list): print(f'  {k}:', v[-5:])

m = ld('maritime.json')
print('\n=== MARITIME ===')
cp = m.get('chokepoints', {})
for ck, cv in cp.items():
    ts = cv.get('tanker_stats', {})
    print(f"  {cv.get('name', ck)}: avg_90d={ts.get('avg_90d')}, avg_7d={ts.get('avg_7d')}, prev_90d={ts.get('prev_90d_avg')}")
    rv = cv.get('recent_values', [])
    if rv: print(f"    recent: {rv[-2:]}")
tss = m.get('tanker_stocks', [])
for tv in tss:
    print(f"  tanker {tv.get('ticker')}: {tv.get('label')}, price={tv.get('price')}, 5d={tv.get('change_5d')}%, 1m={tv.get('change_1m')}%")
rs = m.get('risk_signals', [])
if rs: print(f'  risk_signals: {rs}')

poly = ld('polymarket.json')
print('\n=== POLYMARKET ===')
mkts = poly if isinstance(poly, list) else poly.get('markets', [])
for mm in mkts:
    print(f"  [{mm.get('category','')}] {mm.get('question','')[:70]} => {mm.get('outcomes',{})}")

# Global balance recent actual months
bal = ld('global_balance.json')
print('\n=== GLOBAL BALANCE (recent actual) ===')
blist = bal.get('balance', [])
actuals = [b for b in blist if b.get('type') == 'actual']
print(f'  actual months: {actuals[-6:]}')
forecasts = [b for b in blist if b.get('type') == 'forecast']
print(f'  next 3 forecast: {forecasts[:3]}')

# Crack spread
cr = ld('crack_spread.json')
print('\n=== CRACK SPREAD ===')
for k in ['crack_321', 'gasoline_crack', 'diesel_crack']:
    if k in cr and cr[k]: print(f'  {k}:', cr[k][-5:])

# CFTC
cftc = ld('cftc.json')
print('\n=== CFTC ===')
recs = cftc if isinstance(cftc, list) else cftc.get('records', [])
for r in recs[-5:]: print(f'  {r}')

# Financial
fin = ld('financial.json')
print('\n=== FINANCIAL ===')
for k in ['dxy','real_rate','ovx']:
    if k in fin: print(f'  {k}:', fin[k][-3:])

# Drilling
dr = ld('drilling.json')
print('\n=== DRILLING ===')
for k in dr:
    v = dr[k]
    if isinstance(v, list) and v: print(f'  {k}:', v[-6:])

# Futures
fu = ld('futures.json')
print('\n=== FUTURES ===')
print(f"  curve: {fu.get('curve', [])}")
h = fu.get('history', [])
if h: print(f'  history last 3:', h[-3:])
