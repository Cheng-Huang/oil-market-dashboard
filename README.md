# 🛢️ Oil Market Dashboard

石油市场核心指标仪表盘 —— 自动汇聚供需、价格、库存、金融条件等关键数据，以可视化图表 + 信号面板辅助原油投资决策。

---

## 目录

- [项目结构](#项目结构)
- [数据来源总表](#数据来源总表)
- [各数据详细说明](#各数据详细说明)
  - [价格数据 (price.json)](#1-价格数据-pricejson)
  - [库存数据 (inventory.json)](#2-库存数据-inventoryjson)
  - [产量数据 (production.json)](#3-产量数据-productionjson)
  - [需求数据 (demand.json)](#4-需求数据-demandjson)
  - [金融条件 (financial.json)](#5-金融条件-financialjson)
  - [CFTC 持仓 (cftc.json)](#6-cftc-持仓-cftcjson)
  - [期货曲线 (futures.json)](#7-期货曲线-futuresjson)
  - [裂解价差 (crack_spread.json)](#8-裂解价差-crack_spreadjson)
  - [全球供需平衡 (global_balance.json)](#9-全球供需平衡-global_balancejson)
  - [钻井数据 (drilling.json)](#10-钻井数据-drillingjson)
  - [综合信号 (signals.json)](#11-综合信号-signalsjson)
- [Hard-coded 参数一览](#hard-coded-参数一览)
- [信号计算逻辑详解](#信号计算逻辑详解)
- [如何使用 / 如何看数据](#如何使用--如何看数据)
- [项目欠缺与改进方向](#项目欠缺与改进方向)
- [更新日志](#更新日志)

---

## 项目结构

```
oil/
├── README.md               ← 本文件
├── requirements.md          # 需求文档
├── 石油投资.md               # 投资指标知识梳理
├── data/                    # JSON 数据文件（ETL 输出 / 前端读取）
│   ├── price.json           # WTI/Brent 价格 + 价差
│   ├── price_eia.json       # EIA 源的价格（备份/对照）
│   ├── futures.json         # WTI 期货曲线 + M1-M2 价差
│   ├── inventory.json       # 原油/库欣/汽油/馏分油库存
│   ├── production.json      # 原油产量、炼厂开工率、净进口
│   ├── demand.json          # 汽油/馏分油隐含需求
│   ├── financial.json       # DXY、实际利率、OVX
│   ├── cftc.json            # CFTC 投机持仓
│   ├── crack_spread.json     # 裂解价差（3-2-1 + 汽油 + 柴油）
│   ├── global_balance.json   # 全球供需平衡（STEO）
│   ├── drilling.json         # 美国钻机数（STEO）
│   ├── signals.json         # 综合信号计算结果（7 维）
│   └── meta.json            # 更新时间戳 + 数据源状态
├── etl/                     # Python 数据获取 & 计算脚本
│   ├── config.py            # API 端点、Series ID、信号阈值
│   ├── run_all.py           # ETL 入口（--mock 生成模拟数据）
│   ├── fetch_eia.py         # EIA API v2 数据拉取
│   ├── fetch_fred.py        # FRED API 数据拉取 + 裂解价差计算
│   ├── fetch_cftc.py        # CFTC Socrata API 数据拉取
│   ├── fetch_futures.py     # Yahoo Finance 期货曲线数据
│   ├── fetch_steo.py        # EIA STEO 全球供需 + 钻机数据
│   ├── compute_signals.py   # 信号计算引擎（7 维信号）
│   ├── generate_mock.py     # 模拟数据生成器
│   └── requirements.txt     # Python 依赖（含 scipy）
└── web/                     # 前端 Dashboard（纯静态）
    ├── index.html
    ├── css/style.css
    └── js/
        ├── app.js           # 主入口：加载数据 + 渲染
        ├── charts.js        # ECharts 图表配置工厂
        └── signals.js       # 信号面板渲染
```

---

## 数据来源总表

| 数据文件 | 数据内容 | 来源 | 可信度 | 更新频率 | 是否为计算/衍生数据 |
|----------|----------|------|--------|----------|---------------------|
| `price.json` — wti | WTI 现货价格 | **FRED** `DCOILWTICO` | ⭐⭐⭐⭐⭐ 官方权威 | 日度（工作日） | ❌ 直接拉取 |
| `price.json` — brent | Brent 现货价格 | **FRED** `DCOILBRENTEU` | ⭐⭐⭐⭐⭐ 官方权威 | 日度（工作日） | ❌ 直接拉取 |
| `price.json` — spread | WTI − Brent 价差 | **计算** | ⭐⭐⭐⭐⭐ 无误差 | 日度 | ✅ `WTI价格 - Brent价格` |
| `price_eia.json` | WTI/Brent 价格 (EIA 源) | **EIA** `PET.RWTC.D` / `PET.RBRTE.D` | ⭐⭐⭐⭐⭐ 官方权威 | 日度 | ❌ 直接拉取 |
| `inventory.json` — crude | 美国原油商业库存 | **EIA** `PET.WCESTUS1.W` | ⭐⭐⭐⭐⭐ 官方权威 | 周度（周三发布） | ❌ 直接拉取 |
| `inventory.json` — cushing | 库欣库存 | **EIA** `PET.W_EPC0_SAX_YCUOK_MBBL.W` | ⭐⭐⭐⭐⭐ 官方权威 | 周度 | ❌ 直接拉取 |
| `inventory.json` — gasoline | 汽油库存 | **EIA** `PET.WGTSTUS1.W` | ⭐⭐⭐⭐⭐ 官方权威 | 周度 | ❌ 直接拉取 |
| `inventory.json` — distillate | 馏分油库存 | **EIA** `PET.WDISTUS1.W` | ⭐⭐⭐⭐⭐ 官方权威 | 周度 | ❌ 直接拉取 |
| `production.json` — crude_production | 美国原油产量 | **EIA** `PET.WCRFPUS2.W` | ⭐⭐⭐⭐⭐ 官方权威 | 周度 | ❌ 直接拉取 |
| `production.json` — refinery_utilization | 炼厂开工率 | **EIA** `PET.WPULEUS3.W` | ⭐⭐⭐⭐⭐ 官方权威 | 周度 | ❌ 直接拉取 |
| `production.json` — net_import | 原油净进口 | **EIA** `PET.WCRNTUS2.W` | ⭐⭐⭐⭐⭐ 官方权威 | 周度 | ❌ 直接拉取 |
| `demand.json` — gasoline | 汽油隐含需求 | **EIA** `PET.WGFUPUS2.W` | ⭐⭐⭐⭐ 估算值 | 周度 | ❌ 直接拉取（EIA 自身为估算） |
| `demand.json` — distillate | 馏分油隐含需求 | **EIA** `PET.WDIUPUS2.W` | ⭐⭐⭐⭐ 估算值 | 周度 | ❌ 直接拉取（EIA 自身为估算） |
| `financial.json` — dxy | 广义贸易加权美元指数 | **FRED** `DTWEXBGS` | ⭐⭐⭐⭐⭐ 美联储官方 | 日度（工作日） | ❌ 直接拉取 |
| `financial.json` — real_rate | 10 年期 TIPS 实际利率 | **FRED** `DFII10` | ⭐⭐⭐⭐⭐ 美联储官方 | 日度（工作日） | ❌ 直接拉取 |
| `financial.json` — ovx | OVX 原油波动率指数 | **FRED** `OVXCLS` | ⭐⭐⭐⭐⭐ CBOE 编制 | 日度（工作日） | ❌ 直接拉取 |
| `cftc.json` | WTI 投机持仓 | **CFTC** Socrata API | ⭐⭐⭐⭐⭐ 监管机构官方 | 周度（周五发布） | ❌ 直接拉取；净多头由脚本计算 `long - short` |
| `futures.json` — curve | WTI 期货曲线快照 (12 个合约) | **Yahoo Finance** | ⭐⭐⭐⭐ 市场数据 | 日度（工作日） | ❌ 直接拉取 |
| `futures.json` — spread_history | M1-M2 近远月价差历史 | **计算** (Yahoo Finance) | ⭐⭐⭐⭐ 市场数据计算 | 日度 | ✅ 从合约价格计算 `M1 - M2` |
| `crack_spread.json` — crack_321 | 3-2-1 裂解价差 $/bbl | **计算** (FRED 数据) | ⭐⭐⭐⭐ 标准行业算法 | 日度 | ✅ `(2×汽油×42 + 柴油×42)/3 - WTI` |
| `crack_spread.json` — gasoline_crack | 汽油裂解价差 | **计算** | ⭐⭐⭐⭐ | 日度 | ✅ `汽油×42 - WTI` |
| `crack_spread.json` — diesel_crack | 柴油裂解价差 | **计算** | ⭐⭐⭐⭐ | 日度 | ✅ `柴油×42 - WTI` |
| `global_balance.json` — world_production | 全球液体燃料产量 百万桶/日 | **EIA STEO** `STEO.PAPR_WORLD.M` | ⭐⭐⭐⭐ 官方预测 | 月度 | ❌ 直接拉取 |
| `global_balance.json` — world_consumption | 全球液体燃料消费 百万桶/日 | **EIA STEO** `STEO.PATC_WORLD.M` | ⭐⭐⭐⭐ 官方预测 | 月度 | ❌ 直接拉取 |
| `global_balance.json` — opec_production | OPEC 液体燃料产量 百万桶/日 | **EIA STEO** `STEO.PAPR_OPEC.M` | ⭐⭐⭐⭐ 官方预测 | 月度 | ❌ 直接拉取 |
| `global_balance.json` — balance | 全球供需平衡（隐含库存变化）| **计算** | ⭐⭐⭐⭐ | 月度 | ✅ `产量 - 消费`，>0累库 <0去库 |
| `drilling.json` — rig_count | 美国原油钻机数 (座) | **EIA STEO** `STEO.CORIPUS.M` | ⭐⭐⭐⭐ 官方预测 | 月度 | ❌ 直接拉取 |
| `signals.json` | 7 维综合信号 | **计算** | ⭐⭐⭐ 规则简化 | 随 ETL 运行 | ✅ 完全由 `compute_signals.py` 计算 |
| `meta.json` | 更新时间戳 | **系统** | — | 随 ETL 运行 | ✅ ETL 运行时生成 |

### 可信度说明

- **⭐⭐⭐⭐⭐**：美国政府机构 (EIA, FRED/美联储, CFTC) 或权威交易所 (CBOE) 直接提供的官方数据，行业标准数据源
- **⭐⭐⭐⭐**：EIA 的"隐含需求"本身是 EIA 基于产量 + 库存 + 进出口推算的估计值，非直接计量，但是行业公认的最佳近似
- **⭐⭐⭐**：信号系统基于简化规则计算，阈值为经验值 hard-code，不代表学术严谨的量化模型

---

## 各数据详细说明

### 1. 价格数据 (price.json)

| 字段 | 含义 | 来源 | 为什么需要 | 如何看 |
|------|------|------|-----------|--------|
| `wti` | 西德克萨斯中质原油（WTI）现货价 $/bbl | FRED `DCOILWTICO` | WTI 是北美原油基准价格，全球最核心的两个油价之一 | 看趋势方向 + 与 Brent 的相对位置 |
| `brent` | 布伦特原油现货价 $/bbl | FRED `DCOILBRENTEU` | Brent 是国际原油基准价格，全球大部分原油以此定价 | 与 WTI 对照，两者走势通常同步 |
| `spread` | WTI − Brent 价差 | **计算**: `WTI - Brent` | 反映地区性供需差异、美国出口物流和管道运力 | 正常在 -$3 ~ -$5 左右；大幅偏离说明区域供需失衡 |

> **注意**：WTI-Brent 价差反映的是跨品种地区供需差异，**不等于** 期货曲线的 Backwardation/Contango。曲线结构信号现已改用真实期货 M1-M2 价差（见 `futures.json`），仅在期货数据不可用时回退使用 WTI-Brent 价差。

### 2. 库存数据 (inventory.json)

| 字段 | 含义 | EIA Series ID | 为什么需要 | 如何看 |
|------|------|---------------|-----------|--------|
| `crude` | 美国原油商业库存（不含 SPR），千桶 | `PET.WCESTUS1.W` | 最直接反映美国原油供需松紧的短线指标 | 去库（下降）= 供不应求 → 利多；累库（上升）= 供过于求 → 利空 |
| `cushing` | 库欣交割库存，千桶 | `PET.W_EPC0_SAX_YCUOK_MBBL.W` | WTI 期货交割地，库存过低可引发逼仓 | 低于 25M bbl 需要警惕；接近库容上限约 76M bbl 则意味储存胀满 |
| `gasoline` | 汽油库存，千桶 | `PET.WGTSTUS1.W` | 汽油是最大的成品油消费品类，季节性强 | 低于 5 年区间下沿 → 需求强/炼能不足；反之供过于求 |
| `distillate` | 馏分油（柴油+航煤）库存，千桶 | `PET.WDISTUS1.W` | 柴油与工业活动强相关，全球贸易景气的温度计 | 走势与经济周期同步，关注与历史区间的对比 |

**如何看库存数据**：
1. **周度变化方向**：连续去库（draw）→ 供需收紧；连续累库（build）→ 宽松  
2. **与历史区间对比**：Dashboard 的面积图展示当前值 vs 5 年均值±1标准差区间  
3. **季节性**：夏季驾车高峰前汽油去库正常，不必恐慌；重点看是否"超季节性"  

### 3. 产量数据 (production.json)

| 字段 | 含义 | EIA Series ID | 为什么需要 | 如何看 |
|------|------|---------------|-----------|--------|
| `crude_production` | 美国原油产量，千桶/日 | `PET.WCRFPUS2.W` | 美国是全球最大产油国，页岩革命后产量弹性极大 | 产量持续上升 → 供给压力增大(利空)；平台期/下降 → 供给受限(利多) |
| `refinery_utilization` | 炼厂开工率 % | `PET.WPULEUS3.W` | 反映炼厂将原油加工成成品油的能力利用率 | 高开工 + 成品油去库 = 需求真实强劲；低开工可能是检修或需求不足 |
| `net_import` | 原油净进口，千桶/日 | `PET.WCRNTUS2.W` | 反映美国对外部原油的依赖程度和贸易流向 | 持续下降 → 美国自给度高；上升 → 国内已不能满足炼厂需求 |

### 4. 需求数据 (demand.json)

| 字段 | 含义 | EIA Series ID | 为什么需要 | 如何看 |
|------|------|---------------|-----------|--------|
| `gasoline` | 汽油表观消费/隐含需求，千桶/日 | `PET.WGFUPUS2.W` | 直接反映消费端的真实消耗水平 | 高于 4 周均值 2%+ → 需求走强；低于 2%+ → 需求走弱 |
| `distillate` | 馏分油表观消费/隐含需求，千桶/日 | `PET.WDIUPUS2.W` | 柴油需求与货运/工业高度正相关 | 走势反映经济基本面，比 PMI 等调查数据更为客观 |

> "隐含需求"是 EIA 基于 `产量 + 进口 - 出口 - 库存变化` 间接推算，不是直接计量消费端——但这是行业公认的最佳近似值。

### 5. 金融条件 (financial.json)

| 字段 | 含义 | FRED Series | 为什么需要 | 如何看 |
|------|------|-------------|-----------|--------|
| `dxy` | 广义贸易加权美元指数 | `DTWEXBGS` | 原油以美元计价，美元走强 → 大宗偏弱 | 对比 200 日均线：突破向上 → 利空商品；跌破 → 利多 |
| `real_rate` | 10Y TIPS 实际利率 % | `DFII10` | 实际利率上升 → 持有实物商品的机会成本上升 | >2% → 对大宗估值有压力；<1% → 有利于大宗 |
| `ovx` | OVX 原油波动率指数（类 VIX） | `OVXCLS` | 衡量市场对原油价格跳涨/跳跌的恐慌程度 | >40 → 高波动/恐慌；20-30 → 正常；<20 → 极低波动（可能酝酿变盘） |

### 6. CFTC 持仓 (cftc.json)

| 字段 | 含义 | 来源 | 为什么需要 | 如何看 |
|------|------|------|-----------|--------|
| `net_long` | 管理资金净多头（合约数） | **计算**: CFTC `m_money_long - m_money_short` | 投机资金的方向性押注，反映"聪明钱"的共识 | 极端高位（>90 分位） → 拥挤风险，可能回撤；极端低位（<10 分位） → 悲观过头，可能反弹 |
| `long` | 管理资金多头持仓 | CFTC Disaggregated COT | 分拆观察多空力量 | — |
| `short` | 管理资金空头持仓 | CFTC Disaggregated COT | 分拆观察多空力量 | — |
| `open_interest` | 总持仓量 | CFTC Disaggregated COT | 市场活跃度参考 | 总持仓萎缩 → 市场缺乏兴趣；扩张 → 资金涌入 |

**数据源详情**：
- 接口：CFTC Socrata Open Data API (`https://publicreporting.cftc.gov/resource/72hh-3qpy.json`)
- 合约代码：`067651`（WTI 原油）
- 无需 API Key，公开免费
- Disaggregated Futures Only 报告，Management Money 分类

### 7. 期货曲线 (futures.json)

| 字段 | 含义 | 来源 | 为什么需要 | 如何看 |
|------|------|------|-----------|--------|
| `curve` | WTI 期货曲线快照（未来 12 个月合约价格） | **Yahoo Finance** (`yfinance`) | 展示市场对未来各月油价的预期 | 曲线向下 = Backwardation（近月贵）；曲线向上 = Contango（远月贵） |
| `m1_m2_spread` | 近月-次月价差 (M1-M2) | **计算**: `第1合约 - 第2合约` | 最核心的期限结构指标 | > 0 = Backwardation（利多）；< 0 = Contango（利空） |
| `m1_m6_spread` | 近月-6月后价差 (M1-M6) | **计算**: `第1合约 - 第6合约` | 中期曲线斜率，反映更深层的供需预期 | 绝对值 > $1 说明曲线很陡，方向性强 |
| `structure` | 当前期限结构判断 | **计算** | 快速参考 | `"backwardation"` / `"contango"` / `"flat"` |
| `spread_history` | M1-M2 价差历史时间序列 | **计算** + 累积 | 观察曲线结构演变趋势 | 从 Contango 转 Backwardation 通常伴随油价上涨 |

**数据源详情**：
- 接口：Yahoo Finance (`yfinance` Python 库)
- Ticker 格式：`CL{month_code}{year}.NYM`，如 `CLJ26.NYM` = 2026年4月合约
- 无需 API Key，免费使用
- 历史价差采用累积模式：每次 ETL 运行追加当天数据，首次运行时尝试从合约历史回填

### 8. 裂解价差 (crack_spread.json)

| 字段 | 含义 | 计算公式 | 为什么需要 | 如何看 |
|------|------|----------|-----------|--------|
| `crack_321` | 3-2-1 裂解价差 $/bbl | `(2×汽油价×42 + 柴油价×42)/3 − WTI` | 衡量炼厂利润，反映成品油需求强度 | > $20 = 高利润/需求强；< $10 = 低利润/需求弱 |
| `gasoline_crack` | 汽油裂解价差 | `汽油价($/gal) × 42 − WTI` | 汽油端炼厂利润 | 夏季驾车高峰前通常走高 |
| `diesel_crack` | 柴油裂解价差 | `柴油价($/gal) × 42 − WTI` | 柴油端炼厂利润 | 柴油与工业/运输相关性高 |

**数据源**：WTI 价格 FRED `DCOILWTICO`，汽油价格 FRED `DRGASNYH`（纽约港常规汽油现货），柴油价格 FRED `DHOILNYH`（纽约港二号取暖油现货）。42 为每桶加仑数。

### 9. 全球供需平衡 (global_balance.json)

| 字段 | 含义 | EIA STEO Series | 为什么需要 | 如何看 |
|------|------|-----------------|-----------|--------|
| `world_production` | 全球液体燃料产量，百万桶/日 | `STEO.PAPR_WORLD.M` | 观察全球供给总量及趋势 | 持续上升 → 供给压力 |
| `world_consumption` | 全球液体燃料消费，百万桶/日 | `STEO.PATC_WORLD.M` | 观察全球需求总量及趋势 | 与产量对比判断供需松紧 |
| `opec_production` | OPEC 液体燃料产量，百万桶/日 | `STEO.PAPR_OPEC.M` | OPEC 主导全球边际供给 | 减产 → 利多；增产 → 利空 |
| `non_opec_production` | 非 OPEC 产量，百万桶/日 | `STEO.PAPR_NONOPEC.M` | 页岩油等非OPEC供给增量 | — |
| `balance` | 供需平衡（产量−消费），百万桶/日 | **计算** | 最核心的全球供需松紧指标 | > 0 = 累库（供过于求）；< 0 = 去库（供不应求）|

### 10. 钻井数据 (drilling.json)

| 字段 | 含义 | EIA STEO Series | 为什么需要 | 如何看 |
|------|------|-----------------|-----------|--------|
| `rig_count` | 美国原油钻机数（座）| `STEO.CORIPUS.M` | 钻机数是产量的**领先指标**（6-9个月），比产量本身更能预判供给拐点 | 钻机减少 → 未来产量下降 → 利多；增加 → 利空 |

### 11. 综合信号 (signals.json)

这是**完全由 `compute_signals.py` 计算出来的衍生数据**，不来自任何外部 API。信号系统基于简化规则，详见下文。

---

## Hard-coded 参数一览

以下参数定义在 [etl/config.py](etl/config.py) 中，是人工设定的经验阈值，**不是从数据中动态计算**的：

| 参数 | 值 | 用途 | 设定依据 |
|------|-----|------|----------|
| `SIGNAL_INVENTORY_WEEKS` | `3` | 库存连续 N 周同向变化才触发信号 | 经验法则：避免单周噪音，3 周是常用的观察窗口 |
| `SIGNAL_CUSHING_WARN_MBBL` | `25.0` （百万桶） | 库欣库存低于此值触发逼仓警告 | 库欣总库容约 76M bbl，25M 为行业公认的低位警戒线 |
| `SIGNAL_FUTURES_BACK_THRESHOLD` | `0.10` ($/bbl) | M1-M2 期货价差高于此值判定 Backwardation | 期货市场的最小变动单位约 $0.01，$0.10 为有意义的门槛 |
| `SIGNAL_FUTURES_CONTANGO_THRESHOLD` | `-0.10` ($/bbl) | M1-M2 期货价差低于此值判定 Contango | 同上 |
| `SIGNAL_CONTANGO_THRESHOLD` | `-1.0` ($/bbl) | WTI-Brent 价差回退阈值（无期货数据时用） | 跨品种价差波动更大，需要更宽的阈值 |
| `SIGNAL_BACK_THRESHOLD` | `0.5` ($/bbl) | WTI-Brent 价差回退阈值（无期货数据时用） | 同上 |
| `SIGNAL_OVX_PANIC` | `40.0` | OVX 超过此值为高波动/恐慌 | 历史上 OVX>40 对应剧烈行情（2020 年飙至 300+） |
| `SIGNAL_REAL_RATE_HIGH` | `2.0` (%) | 10Y 实际利率高于此值对大宗构成压力 | 2% 为近年来的经验分水岭 |
| `SIGNAL_POSITIONING_HIGH_PCT` | `90` (百分位) | 净多头高于 90 分位触发拥挤警告 | 反身性回撤风险的经典判断，90 分位为通用阈值 |
| `SIGNAL_POSITIONING_LOW_PCT` | `10` (百分位) | 净多头低于 10 分位 → 利多 | 悲观极端时往往有反弹机会 |

**Mock 数据中的 hard-coded 初始值** (`generate_mock.py`)：

| 参数 | Hard-coded 值 | 说明 |
|------|---------------|------|
| WTI 起始价 | `$68.0` | 随机游走初始值，模拟 2024-2025 年水平 |
| Brent 溢价 | `~$3.5 ± 0.5` | Brent 通常比 WTI 贵 $3-5 |
| 原油库存基线 | `430,000` 千桶 | 模拟 EIA 历史水平 |
| 库欣库存基线 | `32,000` 千桶 | 模拟历史中位水平 |
| 汽油库存基线 | `235,000` 千桶 | 模拟历史中位水平 |
| DXY 起始 | `104.5` | 模拟 2024-2025 年美元强势水平 |
| OVX 起始 | `28.0` | 模拟正常波动率水平 |
| 实际利率起始 | `1.85%` | 模拟 2024-2025 年水平 |
| CFTC 净多头起始 | `180,000` 合约 | 模拟中等偏多水平 |

> Mock 数据仅用于前端开发和演示，不影响真实 API 模式。

---

## 信号计算逻辑详解

所有信号由 [etl/compute_signals.py](etl/compute_signals.py) 计算，输出 4 种状态：

| 状态 | 含义 | Dashboard 显示 |
|------|------|----------------|
| `bullish` | 利多/看涨 | 🟢 绿色 |
| `bearish` | 利空/看跌 | 🔴 红色 |
| `warning` | 警惕/风险 | ⚠️ 黄色 |
| `neutral` | 中性/无明确方向 | ⚪ 灰色 |

### 信号 1：库存趋势 (`inventory`)
- **输入**：`inventory.json` → crude 原油库存序列
- **逻辑**：计算周度差分，取最近 3 周变化
  - 全部 < 0（连续去库）→ 🟢 bullish
  - 全部 > 0（连续累库）→ 🔴 bearish
  - 有涨有跌 → ⚪ neutral
- **附加**：库欣库存 < 25,000 千桶 → `cushing_warning: true`

### 信号 2：曲线结构 (`curve`)
- **输入**：优先 `futures.json` → M1-M2 真实期货价差；无期货数据时回退到 `price.json` → WTI-Brent 价差
- **期货数据模式（优先）**：
  - M1-M2 价差 > $0.10 → 🟢 bullish (标记 "Backwardation")
  - M1-M2 价差 < -$0.10 → 🔴 bearish (标记 "Contango")
  - 介于两者 → ⚪ neutral (标记 "Flat")
  - 同时输出 M1-M6 价差、曲线合约数量等辅助信息
- **WTI-Brent 回退模式**：
  - 最新价差 > $0.5 → 🟢 bullish (标记 "Backwardation*")
  - 最新价差 < -$1.0 → 🔴 bearish (标记 "Contango*")
  - 介于两者 → ⚪ neutral (标记 "Flat*")
  - 标签带 `*` 表示使用近似数据，非真实期货数据
- **数据来源**：Yahoo Finance 免费期货数据（`yfinance`），获取 WTI CL 各月合约价格

### 信号 3：需求强度 (`demand`)
- **输入**：`demand.json` → gasoline + distillate 需求序列
- **逻辑**：分别比较最近一周 vs 前 4 周均值
  - 最近值 > 4 周均值 × 1.02 → bullish
  - 最近值 < 4 周均值 × 0.98 → bearish
  - ±2% 以内 → neutral
- **综合**：汽油看多 + 馏分油不看空 → 🟢; 两者都看空 → 🔴; 其余 → ⚪

### 信号 4：钻井活动 (`drilling`)
- **输入**：优先 `drilling.json` → rig_count 钻机数序列；无钻机数据时回退到 `production.json` → crude_production
- **逻辑**：比较最近 3 个月（或 4 周）均值 vs 再前 3 个月（或 4 周）均值
  - 最近均值 > 前期 × 1.01（钻机增加 1%+）→ 🔴 bearish（未来供给增加利空）
  - 最近均值 < 前期 × 0.99（钻机减少 1%+）→ 🟢 bullish（未来供给减少利多）
  - 其余 → ⚪ neutral
- **数据源**：EIA STEO `STEO.CORIPUS.M`（美国原油钻机数），产量回退模式标注 `source: production_proxy`

### 信号 5：全球供需 (`opec`) — *新增*
- **输入**：`global_balance.json` → balance（全球供需平衡序列）+ opec_production（OPEC 产量）
- **逻辑**：取最近 3 个月平衡值均值
  - 均值 < -0.3 百万桶/日（持续去库）→ 🟢 bullish（供不应求）
  - 均值 > +0.3 百万桶/日（持续累库）→ 🔴 bearish（供过于求）
  - 其余 → ⚪ neutral
- **附加**：同时跟踪 OPEC 产量趋势（increasing / decreasing / stable）
- **数据源**：EIA STEO 月度全球液体燃料产量/消费预测

### 信号 6：金融条件 (`financial`)
- **输入**：`financial.json` → dxy, real_rate, ovx
- **逻辑**：积分制，初始 score = 0
  - DXY > 200 日均线 → score -= 1
  - 实际利率 > 2.0% → score -= 1
  - OVX > 40 → score -= 1
- **综合**：score ≤ -2 → 🔴 bearish; score ≥ 0 → 🟢 bullish; 其余 → ⚪ neutral

### 信号 7：持仓拥挤度 (`positioning`)
- **输入**：`cftc.json` → net_long 序列
- **逻辑**：计算当前值在历史序列中的百分位
  - > 90 分位 → ⚠️ warning（多头拥挤，回撤风险）
  - < 10 分位 → 🟢 bullish（极端悲观，可能反弹）
  - 10-90 分位 → ⚪ neutral
- **注意**：百分位基于拉取到的历史数据范围（默认约 3 年 / 156 周），不是全历史

---

## 如何使用 / 如何看数据

### 环境准备

```bash
# 1. 安装 Python 依赖
cd etl && pip install -r requirements.txt

# 2. 配置 API Keys（在项目根目录创建 .env）
echo "EIA_API_KEY=你的EIA_Key" >> ../.env
echo "FRED_API_KEY=你的FRED_Key" >> ../.env
```

API Key 申请：
- EIA：https://www.eia.gov/opendata/register.php （免费）
- FRED：https://fred.stlouisfed.org/docs/api/api_key.html （免费）
- CFTC：无需 Key

### 运行 ETL

```bash
# 真实数据
cd etl && python run_all.py

# 模拟数据（无需 API Key，用于演示）
cd etl && python run_all.py --mock
```

### 查看 Dashboard

直接用浏览器打开 `web/index.html`（或本地启动 HTTP 服务）：

```bash
cd web && python -m http.server 8080
# 浏览器访问 http://localhost:8080
```

### 日常使用建议

**每周必看**：
1. 📦 **库存**：EIA 周三发布 → 看原油 + 汽油 + 馏分油是去库还是累库
2. 📈 **WTI/Brent 价差**：有无异常偏离
3. 📊 **CFTC 持仓**：净多头是否到了拥挤极端

**每月关注**：
1. 🏭 **产量趋势**：美国原油产量有没有趋势性拐点
2. 💰 **金融条件**：美元 + 实际利率 + OVX 综合判断

**信号面板用法**：
- 3 个以上维度同方向 → 较强信号，可增加仓位信心
- 信号分裂（有多有空）→ 方向不明确，控制仓位
- `⚠️ warning` 出现 → 警惕风险事件或拥挤回撤

---

## 项目欠缺与改进方向

### 🔴 重大缺陷

| 问题 | 说明 | 改进方案 |
|------|------|----------|
| **~~无真正期货曲线数据~~** ✅ 已修复 | 已通过 Yahoo Finance (`yfinance`) 接入 WTI CL 期货各月合约价格，曲线结构信号现使用真实 M1-M2 近远月价差。无期货数据时自动回退到 WTI-Brent 价差近似 | Dashboard 新增期货曲线图 + M1-M2 价差走势图 |
| **~~无 OPEC 数据~~** ✅ 已修复 | 通过 EIA STEO 接入全球供需平衡数据（世界产量/消费、OPEC/非OPEC 产量）。新增 `fetch_steo.py` + `global_balance.json`，Dashboard 新增“全球供需平衡”面板和 `opec` 信号 | 可进一步接入 OPEC MOMR PDF 解析获取配额数据 |
| **~~无钻机数据~~** ✅ 已修复 | 通过 EIA STEO `STEO.CORIPUS.M` 接入美国原油钻机数。新增 `drilling.json`，Dashboard 新增“美国原油钻机数”面板，钻井活动信号优先使用钻机数 | 可进一步接入 Baker Hughes 周度数据获取更高频更新 |
| **无 DUC 和页岩盆地数据** | EIA Drilling Productivity Report 数据未接入 | 向 EIA API 扩展获取 DPR 系列 |

### 🟡 逻辑简化

| 问题 | 说明 | 改进方案 |
|------|------|----------|
| **信号阈值全部 hard-coded** | 阈值是经验值，不随数据自适应 | 改用动态分位数（如用过去 N 年数据计算 Z-score 或百分位）替代固定阈值 |
| **~~5 年区间只用均值±标准差模拟~~** ✅ 已修复 | 库存图现按 ISO 周序号（week-of-year）分组历史数据，计算每周的 min/max 区间带，当前年份与真正的季节性历史区间对比。数据不足时回退到邻近周或均值±标准差 | 可进一步优化为分位数带（如 10%-90%）|
| **CFTC 百分位基于有限历史** | 仅用拉取的约 3 年数据计算百分位，如果数据窗口短则不够稳健 | 拉取更长历史（CFTC 有 2006 年起全量 CSV），或使用全量历史来计算 |
| **需求信号过于简化** | 仅比较最近一周 vs 4 周均值，缺乏季节性调整 | 加入同比（YoY）比较，或与 5 年同期对比 |
| **~~曲线结构信号用错数据源~~** ✅ | 已修复：优先使用真实期货 M1-M2 价差，回退到 WTI-Brent | 可进一步接入 CME 付费数据提高精度 |

### 🟢 功能增强方向

| 方向 | 说明 |
|-------|------|
| **~~裂解价差 (Crack Spread)~~** ✅ 已实现 | 3-2-1 Crack Spread + 汽油/柴油分别裂解价差，使用 FRED 汽油(`DRGASNYH`)/柴油(`DHOILNYH`)/WTI 价格计算，新增 `crack_spread.json` + Dashboard 面板 |
| **自动化调度** | 接入 GitHub Actions cron 或本地 crontab，实现每日/每周自动更新 |
| **历史数据补全** | 当前 EIA 只拉 5 年，FRED 拉 2 年；可扩展到 10 年以上，提供更完整的历史视角 |
| **移动端适配** | 当前 Dashboard 在手机上可用但体验一般，图表需要更好的响应式设计 |
| **数据异常告警** | ETL 失败、数据缺失、数值异常跳变时缺乏告警机制 |
| **多重时间周期** | 只有日度/周度视图，缺少月度/季度趋势聚合视图 |
| **地缘事件标注** | 在价格图上叠加重大地缘事件标注线（制裁、OPEC 会议、飓风等） |
| **回测与绩效** | 对信号系统做历史回测，评估每个信号的预测准确率 |
| **导出 / 订阅** | 支持导出 CSV、邮件/微信推送每周摘要 |
| **国际数据补充** | 中国/印度进口量、全球航运数据、SPR 动态等 |

### 🔧 工程改进

| 方向 | 说明 |
|-------|------|
| **错误处理不够健壮** | API 失败后 data/*.json 仍保留旧数据，无法区分"未更新"和"数据正常但没变" |
| **缺少数据校验** | 没有检查拉取的数据是否合理（如价格为负、库存突变 100%+ 等） |
| **缺少单元测试** | 计算逻辑无测试覆盖 |
| **前端无框架** | 纯 Vanilla JS + Tailwind CDN，代码组织简单但扩展性有限；可考虑引入 Vue/React |
| **Meta 信息不完整** | `meta.json` 只记录 ETL 是否运行，不记录每个数据源的实际最新日期和数据条数 |

---

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 数据获取 | Python 3 + requests + yfinance | 调用 EIA / FRED / CFTC 的 REST API + Yahoo Finance 期货数据 |
| 配置 | python-dotenv | API Key 通过 `.env` 文件管理 |
| 前端 | HTML + Vanilla JS | 纯静态，fetch 加载 JSON |
| 图表 | ECharts 5 | 深色主题，支持交互缩放 |
| 样式 | Tailwind CSS (CDN) | 快速搭建深色 Dashboard |

---

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 免责声明

本项目仅供个人学习和研究使用，**不构成任何投资建议**。数据来源于公开的政府和机构 API，信号系统基于简化的规则模型，存在诸多局限性。投资决策请结合专业分析和个人风险承受能力。
