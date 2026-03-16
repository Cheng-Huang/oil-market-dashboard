# Changelog

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
