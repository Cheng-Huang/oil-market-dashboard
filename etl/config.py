"""
ETL 配置：API 端点、Series ID、输出路径等
"""
import os
from pathlib import Path

# ── 目录 ──────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── API Keys（从环境变量或 .env 读取）─────────────────
EIA_API_KEY = os.getenv("EIA_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# ── EIA API v2 ────────────────────────────────────────
EIA_BASE = "https://api.eia.gov/v2/petroleum"

# Series ID → 本地 key 映射
EIA_WEEKLY_SERIES = {
    "crude_inventory":      "PET.WCESTUS1.W",   # 原油商业库存
    "cushing_inventory":    "PET.W_EPC0_SAX_YCUOK_MBBL.W",   # 库欣库存
    "gasoline_inventory":   "PET.WGTSTUS1.W",   # 汽油库存
    "distillate_inventory": "PET.WDISTUS1.W",   # 馏分油库存
    "spr_inventory":        "PET.WCSSTUS1.W",   # 战略石油储备 (SPR)
    "crude_production":     "PET.WCRFPUS2.W",   # 美国原油产量
    "refinery_utilization": "PET.WPULEUS3.W",   # 炼厂开工率
    "gasoline_demand":      "PET.WGFUPUS2.W",   # 汽油表观消费
    "distillate_demand":    "PET.WDIUPUS2.W",   # 馏分油表观消费
    "crude_net_import":     "PET.WCRNTUS2.W",   # 原油净进口
}

EIA_DAILY_SERIES = {
    "wti_price":   "PET.RWTC.D",    # WTI 现货
    "brent_price": "PET.RBRTE.D",   # Brent 现货
    "gasoline_spot_price": "PET.EER_EPMRU_PF4_RGC_DPG.D",  # NY Harbor 汽油现货 $/gal
}

# ── FRED ──────────────────────────────────────────────
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

FRED_SERIES = {
    "dxy":        "DTWEXBGS",   # 广义贸易加权美元指数
    "real_rate":  "DFII10",     # 10Y TIPS 实际收益率
    "ovx":        "OVXCLS",     # OVX 原油波动率
    "wti_price":  "DCOILWTICO", # WTI 日度价格（FRED 也有）
    "brent_price":"DCOILBRENTEU",# Brent 日度价格
    "gasoline_price": "DGASNYH",  # NY Harbor 常规汽油现货 $/gal (旧ID DRGASNYH 已下线)
    "heating_oil_price": "DHOILNYH",  # NY Harbor 2号取暖油现货 $/gal
}

# ── CFTC ──────────────────────────────────────────────
# Disaggregated Futures Only – 用 Socrata Open Data API
CFTC_ENDPOINT = (
    "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
)
# WTI Crude Oil CFTC code
CFTC_CONTRACT_CODE = "067651"

# ── 信号参数 ──────────────────────────────────────────
SIGNAL_INVENTORY_WEEKS = 3       # 连续 N 周判断趋势
SIGNAL_CUSHING_WARN_MBBL = 25.0  # 库欣库容警戒线 (百万桶)

# 期货曲线结构 —— 使用 WTI 近远月 (M1-M2) 真实价差
# 替代了旧版 WTI-Brent 跨品种价差近似
SIGNAL_FUTURES_BACK_THRESHOLD = 0.10   # M1-M2 > 此值 → Backwardation ($/bbl)
SIGNAL_FUTURES_CONTANGO_THRESHOLD = -0.10  # M1-M2 < 此值 → Contango ($/bbl)

# 保留旧阈值供 WTI-Brent 价差参考（不再用于曲线判断）
SIGNAL_CONTANGO_THRESHOLD = -1.0 # WTI-Brent Deep Contango (仅参考)
SIGNAL_BACK_THRESHOLD = 0.5      # WTI-Brent Backwardation (仅参考)

SIGNAL_OVX_PANIC = 40.0          # OVX 恐慌阈值
SIGNAL_REAL_RATE_HIGH = 2.0      # 高实际利率阈值
SIGNAL_POSITIONING_HIGH_PCT = 90 # CFTC 净多头高分位
SIGNAL_POSITIONING_LOW_PCT = 10  # CFTC 净多头低分位

# ── 裂解价差崩塌预警 ────────────────────────────────
SIGNAL_GASOLINE_CRACK_CRITICAL = 10.0  # 汽油裂解 < 此值 → 炼厂亏损预警
SIGNAL_GASOLINE_CRACK_SHUTDOWN = 5.0   # 汽油裂解 < 此值 → 炼厂减产信号
SIGNAL_CRACK_DAILY_DROP_PCT = 40.0     # 汽油裂解单日跌幅% → 崩塌信号

# ── STEO 数据验证 ──────────────────────────────────
SIGNAL_STEO_MAX_MONTHLY_SUPPLY_CHANGE = 4.0  # 月度供给变化 > 此值(百万桶/日) → 需要交叉验证

# ── SPR 释放评估 ──────────────────────────────────
SIGNAL_SPR_RELEASE_PRICE_TRIGGER = 95.0  # WTI > 此价 + 供给中断 → SPR释放概率高
SIGNAL_SPR_LOW_LEVEL_MBBL = 350000       # SPR < 此水平(千桶) → 释放空间有限
