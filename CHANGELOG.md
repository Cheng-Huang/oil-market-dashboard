# Changelog

## [2026-03-17f] — 证据层级框架 + 假设驱动分析 + 弱推断约束

> Commit: `4e25c65` — 从「声称→验证」转变为「假设→证据→反证」框架，引入 Evidence Tier 分层和 counter-evidence 约束

### 新增

- **证据层级（Evidence Tier）体系** — 每个数据源标注 A/B/C/D 层级
  - A 层（直接观测）：现货/期货价格、EIA 周度库存/需求/产量、CFTC 持仓、OVX/DXY、航运通行量、钻机数
  - B 层（二手确认）：STEO 实际值、OPEC 国别产量
  - C 层（市场代理）：油轮股价、ETF 期权（USO/XLE）、Polymarket
  - D 层（推演/预测）：STEO 预测值、情景概率
  - 混合层级标注：`maritime = "A/C"`（通行量=A，油轮股=C，不得混用）、`global_balance = "B/D"`（实际值=B，预测值=D）

- **假设框架（Hypothesis-based reasoning）** — 7 类市场研判改用假设标签
  - 每个 `MARKET_CLAIMS` 新增 `hypothesis_label` 字段（如"假设：实物供给通道受阻"）
  - 每个研判新增 `counter_evidence` 字段，明确列出削弱假设的具体数据条件

- **`reports/2026-03-17-daily-v3.md`** — 日报 v3（假设驱动版本，428行）
  - 每个数据段落结构：事实 → 多种一致解释 → 不能确认的事项 → 反证条件
  - 滞后 >7 天数据剔除方向性判断，降级为"背景"
  - 4 个核心假设独立验证：地缘风险成分(中-高) / 供给通道受阻(中) / 空头回补主导(中低) / SPR 释放(中)
  - 触发条件矩阵：供应恶化/僵持/快速缓和 三情景各自的观察指标和失效条件
  - 数据改进路线图：按"减少 AI 补脑空间"优先级排列

### 修改

- **`etl/data_verification.py`**
  - `inventory_data_sources()` 中 11 个数据源全部新增 `evidence_tier` 字段
  - 混合数据源新增 `evidence_tier_note` 解释字段
  - `MARKET_CLAIMS` 7 个研判全部新增 `hypothesis_label` 和 `counter_evidence`
  - `assess_claim_verifiability()` 输出新增 `hypothesis_label` 和 `counter_evidence` 字段

- **`data/signals.json`** — 每个信号新增 `evidence_tier` + `evidence_note`
  - contradictions 中 tanker_stock_vs_maritime 措辞从因果性改为相关性（"与…一致，但也可能…"）

- **`data/verification.json`** — 同步新增证据层级和假设框架字段

## [2026-03-17e] — 2026-03-17 全量数据刷新 + 日报 v2

> Commit: `1feafde` — 16 源 ETL 全量刷新 + 数据驱动日报

### 新增

- **`reports/2026-03-17-daily-v2.md`** — 日报 v2（数据驱动版本，304行）
  - WTI $97.90, Brent $104.31; OVX 119.02（99.4% 分位，极端恐慌）
  - 霍尔木兹通行量 -97%（AIS 数据，实际中断估计 50-70%）
  - 深度 Backwardation：M1-M6 价差 +$15
  - CFTC：空头回补驱动，净多仓 26% 分位
  - 数据交叉验证 + 置信度分层

### 修改

- **数据文件全量刷新** — 15 个 JSON 更新（FRED, EIA, STEO, CFTC, Yahoo Finance, Polymarket, IMF PortWatch, 期权）
  - `data/futures.json` — 期货曲线合约价格更新
  - `data/polymarket.json` — 地缘事件概率更新
  - `data/price.json` / `data/price_eia.json` / `data/price_realtime.json` — 价格数据刷新
  - `data/signals.json` — 信号重新计算
  - 其余数据文件增量更新

---

## [2026-03-17d] — 代码重构: 提取公共 EIA 工具模块 + 去重 + 元数据增强

### 新增

- **`etl/eia_utils.py`** — EIA API 公共工具模块
  - `fetch_steo_series()` — 拉取单个 EIA STEO series（统一实现）
  - `fetch_eia_intl_production()` — 拉取 EIA International 分国别产量，支持 `convert_to_mbd` 参数

### 重构

- **`etl/fetch_global_demand.py`** — 删除本地 `_fetch_steo_series()`，改用 `eia_utils.fetch_steo_series`；`fetch_eia_intl_production` 重命名为 `fetch_demand_intl_production` 并委托给 `eia_utils`
- **`etl/fetch_opec_production.py`** — 删除本地 `_fetch_steo()` 和 30+ 行内联 EIA International 拉取逻辑，改用 `eia_utils`
- **`etl/fetch_global_inventory.py`** — 删除本地 `_fetch_steo()`，改用 `eia_utils.fetch_steo_series`

### 改进

- **OPEC+ 配额元数据** — 新增 `OPEC_PLUS_QUOTA_REFERENCE` 常量（`"2024-06 OPEC+ 37th JMMC"`），输出 JSON 写入 `quota_reference` 字段，便于识别配额基准是否过时
- **SPR 估算标注** — 日本/中国/欧洲 SPR 估算值新增 `estimate_year: 2024`，明确标注数据版本年份
- **`etl/run_all.py`** — `TOTAL_STEPS` 从硬编码 `16` 改为从步骤列表动态计算 `len(_steps)`，后续增删步骤时自动更新

## [2026-03-17c] — 中期数据扩展: 全球需求/OPEC产量/全球库存/期权情绪 + Dashboard 可视化

### 新增

- **`etl/fetch_global_demand.py`** — 全球石油需求覆盖模块
  - EIA STEO 5 区域月度消费（美国/OECD欧洲/非OECD/OECD/全球），456 期
  - EIA International 5 国原油产量（中国/印度/巴西/挪威/墨西哥），`INTL.57-1-{ISO3}-TBPD.M`
  - 需求份额计算（非OECD≈57%、美国≈19%）+ 月度异常检测
  - JODI UN SDMX API（预留，当前返回 HTTP 500）
  - MPC/VLO/PSX 炼厂股价作为亚洲需求代理
  - 输出：`data/global_demand.json`

- **`etl/fetch_opec_production.py`** — OPEC+ 国别产量监控模块
  - 20 国/地区产量覆盖：STEO 聚合 4 个 + EIA International 国别 16 个
  - OPEC+ 减产执行率计算（硬编码配额: SAU=9.0, RUS=9.0, IRQ=4.0 等）
  - 闲置产能估算（5年峰值 vs 当前产量），总闲置 ≈3.43 mb/d
  - 产量月环比趋势 + 异常检测（MoM > ±5%）
  - 输出：`data/opec_production.json`

- **`etl/fetch_global_inventory.py`** — 全球库存综合模块
  - STEO 美国商业库存月度（`STEO.PASC_US.M`）
  - EIA 周度 5 类库存（原油/库欣/汽油/馏分油/SPR）
  - 隐含库存变化（读取 global_balance.json 供需差值推算，最近 24 月）
  - 浮仓经济性分析（期货曲线 Contango → 浮仓利润估算）
  - 库存偏差分析（当前 vs 5 年均值，支持季节性修正）
  - 全球 SPR 估算（美国实际 + 日/中/欧估算值，合计 ≈2185 mb）
  - 输出：`data/global_inventory.json`

- **`etl/fetch_options.py`** — 期权数据 & Put/Call Ratio 模块
  - Yahoo Finance USO/XLE ETF 期权链（CL=F 期货期权不可用，ETF 作代理）
  - 多 ticker 迭代：USO 19 到期日 + XLE 22 到期日
  - P/C Ratio（Volume + OI）+ IV Skew + 关键 OI Strike 位
  - OVX 增强分析：百分位/regime/vol-of-vol（读取 financial.json）
  - 情绪评估：5 档信号（extreme_bullish → extreme_bearish）
  - 输出：`data/options.json`

- **`etl/fetch_yahoo_realtime.py`** — Yahoo Finance 实时价格快照
  - WTI/Brent/天然气/汽油盘中价格
  - 输出：`data/price_realtime.json`

- **`etl/fetch_eia_daily.py`** — EIA 每日现货价格补充
  - 补齐 FRED 滞后时的最新 EIA 日度数据

- **`etl/fetch_maritime_alt.py`** — 航运数据交叉验证
  - 油轮上市公司股价（FRO/STNG/INSW/DHT）多源交叉
  - 输出：`data/maritime_validation.json`

- **Dashboard 7 个新面板**（`web/index.html` + `web/js/app.js` + `web/js/charts.js`）
  - 🌏 全球石油需求 (STEO 区域拆分) — 5 区域消费趋势折线图
  - 🏗️ OPEC+ 主要产油国 — 8 国产量对比折线图，截至日期标注
  - 📋 OPEC+ 减产执行率 & 闲置产能 — 双面板：配额vs实际横向柱图 + 闲置产能柱图
  - 📦 隐含库存变化 (供需推演) — 累库/去库柱图 + 预测区间标注
  - 🛡️ 全球 SPR & 库存偏差 — 双面板：各国SPR柱图 + 偏差仪表盘
  - 📊 期权情绪 & 波动率 (P/C + OVX) — 三栏：P/C卡片 + 到期日柱图 + OVX增强仪表盘
  - charts.js 新增 6 个图表工厂函数：quotaComplianceChart, spareCapacityChart, impliedStockchangeChart, sprBarChart, optionsPCChart

### 修改

- **`etl/run_all.py`** — 管道从 9 步扩展到 16 步
  - [8-10] Yahoo实时价格 + EIA日度 + 航运交叉验证
  - [11-14] 全球需求 + OPEC产量 + 全球库存 + 期权数据
  - meta.json sources 新增 7 个数据源

- **`web/index.html`** — 新增 7 个面板 HTML 结构 + 数据源标注更新
- **`web/js/app.js`** — 新增 7 个 render 函数 + Promise.all 加载 18 个 JSON + handleResize 支持新图表
- **`web/js/charts.js`** — 新增 6 个 ECharts 图表配置工厂函数

### 修复

- **OPEC+ 产量图** — 移除 STEO `us_production`（24 mb/d 含 NGL 等全部液体，口径不同于国别原油产量），改用 8 个 OPEC+ 核心国
- **OPEC+ 产量图** — 数据截取最近 120 个月，避免 1973 年起的 50 年 x 轴；添加"数据截至 YYYY-MM（EIA International 滞后约 3-4 个月）"标注
- **_site 部署** — 修复 `cp -r data _site/data` 嵌套复制问题（先 rm -rf 再 cp）

### 技术说明

- EIA STEO 国别系列（如 `STEO.PATC_CHINA.M`）返回空数据，改用 EIA International API（`INTL.57-1-{ISO3}-TBPD.M`），但仅 activityId=1（产量）可用
- STEO 库存系列仅美国可用（`PASC_US.M`），OECD/欧洲/日本系列返回空
- Yahoo Finance 不提供 CL=F 商品期货期权，改用 USO/XLE ETF 期权作代理
- 中国不公布 SPR 数据，使用行业估算值（≈950 mb）

## [2026-03-17a] — 数据驱动分析框架：验证引擎 + 航运数据可信度 + 分析纪律规则 + 日报

### 新增

- **`etl/data_verification.py`** — 4层数据验证与覆盖度评估引擎
  - Layer 1: 数据源清单（11个源的覆盖范围、新鲜度、盲区）
  - Layer 2: 7类市场研判的验证能力评估（high/medium/low）
    - 地缘风险溢价、投机资金推动 → high
    - 供给中断、需求走弱、炼厂利润、曲线异常 → medium
    - SPR/政策 → low
  - Layer 3: 时效可靠性评分（OVX + 数据滞后 → degraded/acceptable）
  - Layer 4: 覆盖盲区识别 + 5条优先改进建议
  - 输出 `data/verification.json`，作为报告生成的 ground truth

- **`data/verification.json`** — 新增数据验证结果文件
  - 11个数据源的新鲜度和覆盖能力
  - 7个市场研判类型各自的验证检查清单和置信度
  - 时效评估和改进建议

- **`reports/2026-03-17-daily.md`** — 日报（数据驱动版本）
  - 基于 verification.json 决定报告能写什么、不能写什么
  - 经路透社/OilPrice 外部数据交叉验证
  - 霍尔木兹-98%确认为真实数据（美伊战争实际影响，非数据错误）
  - 明确标注盲区和不确定性
  - 6大章节：数据验证总览、项目数据发现、市场研判与验证、盲区与不确定性、操作含义、数据改进路线图

### 修改

- **`etl/compute_signals.py`** — 10项分析纪律改进（基于专业投资者评审）
  - Backwardation vs 过剩并存：严重性从 "high" 降为 "medium"，添加共存解释
  - 裂解价差分析：使用审慎多因素语言，要求2-4周+多指标才能确认需求断裂
  - SPR政策：release_likelihood 上限为 "high"（非 "very_high"），使用条件语言
  - STEO供给：正确区分产量 vs 运输（封锁影响贸易流向，不直接导致产量骤降）
  - CFTC持仓：新增驱动分析（short_squeeze/new_longs/mixed）+ P25/P75历史百分位
  - 新增 `_score_consistency()` 评分一致性函数
  - 新增 `price_freshness()` 中的 temporal_risk 评估
  - 新增霍尔木兹数据合理性交叉验证（油价<$120 + 通行量-90% → 数据存疑标记）

- **`etl/fetch_maritime.py`** — 航运数据可信度增强
  - `_assess_risk()` 新增 `data_confidence` 字段（high/medium/low）
  - 通行量降幅>90%且仅<5艘时标记 `data_warning`，含AIS/覆盖率解释

- **`etl/run_all.py`** — 新增步骤 [10] 调用 `data_verification.run_verification()`

- **`etl/config.py`** — 新增 `SIGNAL_CRACK_DAILY_DROP_PCT` 参数

- **数据文件更新** — 全量ETL刷新（3/17运行）
  - `data/signals.json` — 包含所有新增信号字段
  - `data/futures.json` — 12合约WTI曲线（Backwardation, M1=$96.02）
  - `data/inventory.json` — EIA周度库存含SPR
  - `data/maritime.json` — 4航运要道 + 油轮股
  - `data/financial.json` — DXY/OVX/实际利率
  - `data/crack_spread.json` — 3-2-1裂解含汽柴油分拆
  - `data/polymarket.json` — 地缘事件概率

### SKILL.md v2.0 重写（报告生成理念变更）

- **从模板驱动改为数据驱动**：不再用预设模板套数据，而是让数据说话
- **verification.json 作为 ground truth**：先读验证结果，再决定报告能写什么
- **7步分析流程**：数据盘点 → 数据发现 → 外部对照 → 交叉验证 → 盲区识别 → 研判输出 → 改进建议
- **结论强度 = 数据支撑强度**：仅3天数据不能叫"崩塌"，单源异常不能叫"确认"
- **9条常见逻辑陷阱**：Backwardation+过剩不矛盾、裂解下降≠需求断裂、航运极端值先查数据质量等
- **Report Structure**：6章节制，新增"数据验证总览"和"盲区与不确定性"核心章节

### 背景

基于专业投资者对 `reports/2026-03-16-daily-v2.md` 的 10 点结构性评审，涵盖：
- 关键逻辑错误（Backwardation vs 过剩、裂解过度推断、霍尔木兹数据质量）
- 分析纪律问题（STEO解读、SPR政策断言、时间频率错配）
- 形式问题（信号系统外露、结论/评分不一致）

以及用户对 SKILL.md 的哲学性反馈："不应该用模板限定太多，应该让项目数据的结论与网络信息进行比对验证"

---

## [2026-03-16c] — 交易员反馈改进：SPR 政策信号、裂解崩塌检测、STEO 验证、风控规则

> Commit: `10809b6` — 基于资深交易员对日报的 5 点结构性反馈，完善信号引擎和报告生成规则

### 新增

- **`etl/compute_signals.py`** — 新增 2 个信号计算函数 + 1 个崩塌检测机制
  - `spr_policy_signal()` — SPR/IEA 政策响应评估
    - 综合 WTI 价格水平、航运中断程度、SPR 库存水平，评估战略储备释放概率
    - 四级输出：`very_high` / `high` / `moderate` / `low`
    - 含 SPR 释放容量估算（当前库存 ÷ 最大释放速率 4.4 百万桶/日）
    - 低库存警戒（< 350 百万桶时标注释放空间有限）
  - `steo_data_validation()` — STEO 月度数据异常检测
    - 监控月度供给变动是否超过 ±4 百万桶/日的合理阈值
    - 超阈值数据点标记为 `warning` 或 `critical`，并建议交叉验证
    - 当前正确捕获 2020-05 COVID 冲击（-11.3）和 2026-03 霍尔木兹封锁（-6.06）两个异常点
  - `crack_spread_signal()` — 新增三级崩塌预警机制
    - `critical`：汽油裂解 < $10（炼厂亏损预警）
    - `shutdown`：汽油裂解 < $5（炼厂减产信号，需求端承接断裂）
    - `collapse`：单日跌幅 > 40%（裂解崩塌，地缘溢价不可持续最强信号）
    - 新增 `gas_diesel_divergence` 字段跟踪汽油-柴油裂解分化度
    - 新增 `gasoline_crack_daily_drop_pct` 字段记录单日跌幅

- **`etl/config.py`** — 新增 7 个信号参数
  - `SIGNAL_GASOLINE_CRACK_CRITICAL = 10.0` — 汽油裂解亏损警戒线
  - `SIGNAL_GASOLINE_CRACK_SHUTDOWN = 5.0` — 炼厂减产信号线
  - `SIGNAL_CRACK_DAILY_DROP_PCT = 40.0` — 崩塌判定阈值
  - `SIGNAL_STEO_MAX_MONTHLY_SUPPLY_CHANGE = 4.0` — STEO 月度供给异常阈值
  - `SIGNAL_SPR_RELEASE_PRICE_TRIGGER = 95.0` — SPR 释放价格触发线
  - `SIGNAL_SPR_LOW_LEVEL_MBBL = 350000` — SPR 低库存警戒线
  - `spr_inventory` 加入 `EIA_WEEKLY_SERIES`（series: `PET.WCSSTUS1.W`）

### 修改

- **`etl/compute_signals.py`** — `compute_all_signals()` 输出从 10 组扩展到 12 组
  - 新增 `spr_policy`、`steo_validation` 两个信号组
  - `crack_spread` 信号优先级提升：崩塌信号覆盖所有其他判断逻辑

- **`etl/run_all.py`** — 信号输出增强
  - 裂解崩塌时显示 🚨 特殊提示（含 collapse_alert 级别和汽油裂解价格）
  - SPR 政策信号按 likelihood 分级显示（🚨/⚠️/⚪/✅）
  - STEO 验证异常时显示 🔶 提示（含异常数据点数量）

- **`etl/fetch_eia.py`** — `save_eia_data()` 的 `inventory` 字典新增 `spr` 键

- **`etl/extract_report_data.py`** — INVENTORY 输出新增 `spr` 字段

- **报告生成规则**（SKILL.md）— 5 项重大规则更新
  1. **情景概率**：必须用范围表达（如 10-25%），不得精确到个位；OVX > 80 时加置信区间警示；Polymarket 标注校准性局限
  2. **策略风控**：每个操作建议必须包含止损位、仓位规则、最大亏损、保证金风险、时间窗口
  3. **裂解崩塌**：汽油裂解 < $10 必须提升至核心风险级别，在核心观点 + 裂解分析 + 操作建议三处突出
  4. **SPR/IEA 政策**：油价 > $95 + 供给中断时必须评估 SPR 释放和 IEA 协调响应
  5. **STEO 异常**：月度供给变动 > 4 百万桶/日时标注数据存疑并建议交叉验证

### 背景

基于资深交易员对 `reports/2026-03-16-daily.md` 的评审反馈：
- 反馈 #1：情景概率分配过于自信，缺乏方法论支撑
- 反馈 #2：汽油裂解 $7.70 崩塌被低估为"偏弱"，实际是地缘溢价不可持续的最强信号
- 反馈 #3：Calendar Spread 策略缺少止损位和仓位管理
- 反馈 #4：完全缺失 SPR 释放和 IEA 协调响应维度
- 反馈 #5：3 月 STEO 供给骤降 6 百万桶/日数据极端罕见，需要交叉验证

## [2026-03-16b] — 数据发布 GitHub + Actions 自动化 ETL + 信号引擎增强

> Commit: `6fe74a4`

### 新增

- **`.github/workflows/etl.yml`** — GitHub Actions 每日定时 ETL
  - 每天 UTC 14:00（北京时间 22:00）自动运行全量 ETL 管道
  - 数据变化时自动 commit & push 到 `main` 分支
  - 支持 `workflow_dispatch` 手动触发
  - 需在 repo Secrets 配置 `EIA_API_KEY` 和 `FRED_API_KEY`

- **`etl/compute_signals.py`** — 新增 3 个信号计算函数
  - `crack_spread_signal()` — 裂解价差信号，含 3-2-1 Crack、汽油/柴油裂解分拆、20d/60d 均线比较、需求交叉验证
  - `cross_analysis()` — 交叉分析引擎，检测曲线结构 vs 供需平衡矛盾、油轮股 vs 航运量异常
  - `price_freshness()` — 现货 vs 期货数据时滞计算，lag > 3 天时触发报告警告

- **`etl/run_all.py`** — 新增 `_fix_price_freshness()` 函数
  - 当 FRED 价格滞后 EIA 时，自动补齐更新的数据点

- **`data/` 目录** — 15 个 JSON 数据文件首次纳入版本控制
  - signals.json, price.json, price_eia.json, inventory.json, demand.json, production.json, crack_spread.json, futures.json, global_balance.json, drilling.json, cftc.json, financial.json, maritime.json, polymarket.json, meta.json

- **`reports/2026-03-16-daily.md`** — 首份基于真实数据的石油市场投资日报

- **`etl/extract_report_data.py`** / **`etl/_extract.py`** — 数据提取辅助脚本

### 修改

- **`.gitignore`** — 移除 `data/` 条目，允许数据文件推送到 GitHub
- **`etl/config.py`** — FRED 汽油价格 series ID 从 `DRGASNYH`（已下线）改为 `DGASNYH`
- **`etl/fetch_steo.py`** — `_compute_balance()` 新增 `supply`、`demand`、`type`（actual/forecast）字段
- **`etl/generate_mock.py`** — 模拟数据适配新的 balance 格式（含 type/supply/demand）
- **`etl/run_all.py`** — 信号打印逻辑适配 `cross_analysis`（无 signal 字段）和 `price_freshness`
- **`etl/compute_signals.py`** — `compute_all_signals()` 新增加载 `crack_spread.json`、`maritime.json`，调用新信号函数

### 修复

- **`etl/config.py`** — FRED series `DRGASNYH` 已被 FRED 删除导致 400 Client Error，替换为 `DGASNYH`（Conventional Gasoline Prices: New York Harbor）

## [2026-03-16] — 航运要道 + 预测市场模块

### 新增

- **`etl/fetch_maritime.py`** — 航运要道监控模块
  - 从 IMF PortWatch (ArcGIS) 获取霍尔木兹海峡、曼德海峡、苏伊士运河、马六甲海峡的每日油轮/总船舶通行量
  - 计算 7 日 / 90 日滚动均值，周环比变化
  - 基于通行量骤降自动生成风险信号（danger / warning / normal）
  - 通过 Yahoo Finance 拉取油轮上市公司（FRO, STNG, INSW, DHT）股价作为运价代理

- **`etl/fetch_polymarket.py`** — Polymarket 预测市场模块
  - 通过 Gamma Events API 获取石油相关地缘政治事件的概率数据
  - 覆盖供给侧风险（伊朗）、需求侧风险（经济衰退）、地缘政治（俄乌/北约/中印）三个分类
  - 按成交量排序，每分类展示最活跃的 8 个子市场

- **`web/index.html`** — 新增航运要道面板和 Polymarket 面板的 HTML 结构
- **`web/js/app.js`** — 新增 `renderMaritime()` 和 `renderPolymarket()` 渲染函数
  - 航运模块：风险信号卡片、咽喉要道统计卡片、霍尔木兹海峡通行量柱线图、油轮运价指标
  - Polymarket 模块：三列分类展示，带概率进度条和 Polymarket 链接
  - 新增 `escapeHtml()` 工具函数防止 XSS

### 修改

- **`etl/run_all.py`** — 集成新模块
  - 新增 `[6/9] Polymarket` 和 `[7/9] 航运数据` 步骤
  - `meta.json` 的 `sources` 新增 `polymarket` 和 `maritime` 字段
- **`web/index.html`** — Footer 数据来源新增 Polymarket / IMF PortWatch

### 修复

- **`etl/run_all.py`** — 修正 ETL 步骤编号不一致问题（部分步骤显示 `[x/6]`，部分显示 `[x/9]`），统一为 `[1/9]` ~ `[9/9]`
- **`etl/fetch_polymarket.py`** — 当所有事件 slug 失效导致市场数为 0 时，输出警告提示检查 `CURATED_EVENTS` 配置
- **`web/js/charts.js`** — 修复 `lineChart()` 按数组位置而非日期对齐多 series 数据的 bug，导致日期范围不同的数据系列（如炼厂开工率 1990~ vs 原油产量 1983~）错位，2019 年后的炼厂开工率无法显示。现改用 `Set` 合并所有日期为统一 x 轴，用 `Map` 按日期查找对应值

## [2026-03-09] v1.2 — P1 修复

### 新增

- **EIA STEO 数据源** — 接入 Short-Term Energy Outlook 月度数据，新增 `fetch_steo.py`
  - 全球供需平衡：世界产量/消费、OPEC/非OPEC 产量 → `global_balance.json`
  - 美国原油钻机数 (`STEO.CORIPUS.M`) → `drilling.json`

- **前端面板**
  - 🌍 全球供需平衡 (STEO)：双轴图展示产量/消费折线 + 供需平衡柱状
  - 🔧 美国原油钻机数：折线图展示历史钻机数趋势

- **信号引擎升级（6 维 → 7 维）**
  - 新增 `opec` 信号（全球供需）：基于近 3 月供需平衡均值判断利多/利空
  - `drilling` 信号升级：优先使用钻机数（领先指标），回退到产量代理
  - 信号面板 UI 同步更新，显示 7 个信号维度

### 修改

- **`etl/run_all.py`** — 新增 STEO 步骤（[3/6]），总步骤从 5 增至 6
- **`etl/generate_mock.py`** — 新增 `global_balance.json` 和 `drilling.json` 模拟数据

### 修复

- **库存图 5 年季节性区间带** — 从简单均值±标准差改为按 ISO 周序号分组的历史 min/max 计算，支持邻近周回退

## [2026-03-08] v1.1 — P0 修复

### 新增

- **裂解价差 (Crack Spread)** — 3-2-1 + 汽油/柴油分别裂解价差
  - 新增 FRED 数据源：`DRGASNYH`（汽油）、`DHOILNYH`（柴油）
  - `fetch_fred.py` 新增 `_compute_crack_spread()` → `crack_spread.json`
  - 前端新增 🔥 裂解价差面板

- **原油净进口图表** — `production.json` 中已有 `net_import` 数据，新增前端渲染
  - 前端新增 🚢 原油净进口面板

### 修复

- **`etl/requirements.txt`** — 补充 `scipy>=1.11` 依赖（`compute_signals.py` 中使用）

## [2026-03-04] v1.0 — 初始版本

- 项目初始化：7 大指标模块 + 6 维信号系统
- 数据源：EIA API v2、FRED API、CFTC Socrata、Yahoo Finance
- 前端：ECharts 5 + Tailwind CSS 深色主题 Dashboard
- ETL：支持真实 API 拉取和 `--mock` 模拟数据模式
- 部署：静态文件，可部署到 GitHub Pages / Vercel / 任意静态服务
