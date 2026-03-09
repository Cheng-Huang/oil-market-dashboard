# 石油投资指标 Dashboard — 需求文档

> **版本**：v1.2  
> **日期**：2026-03-09  
> **作者**：自动生成  
> **状态**：Draft

---

## 1. 项目概述

### 1.1 目标

构建一个**单页 Web Dashboard**，自动汇聚石油市场核心指标数据，以可视化图表 + 关键数字卡片的形式呈现，帮助投资者快速判断原油市场的供需紧张程度、价格结构信号和宏观金融条件。

### 1.2 核心用户

个人石油/能源投资者，需要每天/每周快速浏览关键指标，辅助交易决策。

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **一屏总览** | 打开页面即可看到所有核心指标的最新状态，无需翻页 |
| **数据优先** | 所有指标来自官方/权威 API，标注数据源和更新时间 |
| **信号明确** | 用颜色/箭头/标签直观表达"利多 / 利空 / 中性"信号 |
| **低维护** | 前端纯静态部署（GitHub Pages / Vercel），后端用定时脚本拉数据生成 JSON |

---

## 2. 功能模块

Dashboard 按投资分析优先级分为 **7 个模块**，对应 [石油投资.md](石油投资.md) 中的 7 大类指标。

### 模块 A：价格总览（Header Banner）

| 指标 | 展示形式 | 数据源 |
|------|----------|--------|
| WTI 现货/近月价格 | 大字 + 日变动 % + 迷你折线（30天） | EIA API / FRED |
| Brent 现货/近月价格 | 大字 + 日变动 % + 迷你折线（30天） | EIA API / FRED |
| WTI-Brent 价差 | 数字 + 条形标注正常区间 | 计算字段 |
| 市场状态标签 | "Backwardation" / "Contango" 彩色标签 | 期货曲线计算 |

### 模块 B：供需与库存

| 指标 | 图表类型 | 数据源 | 更新频率 |
|------|----------|--------|----------|
| 美国原油商业库存 | 面积图（52周 + 5年区间带） | EIA API `PET.WCESTUS1.W` | 周 |
| 库欣（Cushing）库存 | 折线图 + 库容警戒线 | EIA API `PET.WCUSTP11.W` | 周 |
| 汽油库存 | 面积图（52周 + 5年区间带） | EIA API | 周 |
| 馏分油库存 | 面积图（52周 + 5年区间带） | EIA API | 周 |
| 美国原油产量 | 折线图 | EIA API `PET.WCRFPUS2.W` | 周 |
| 炼厂开工率 | 折线图 + 参考均值 | EIA API | 周 |
| 成品油隐含需求（汽油 + 馏分油） | 柱形图（周比/年比） | EIA API 计算 | 周 |
| 原油净进口 | 折线图 | EIA API | 周 |

**信号逻辑**：
- 库存连续 3 周去库（draw）→ 显示 🟢 利多
- 库存连续 3 周累库（build）→ 显示 🔴 利空
- 库欣库存低于 25M bbl → 显示 ⚠️ 逼仓风险

### 模块 C：OPEC+ 与全球供需平衡

| 指标 | 图表类型 | 数据源 | 更新频率 |
|------|----------|--------|----------|
| OPEC 产量（实际 vs 配额） | 分组柱形图 | OPEC MOMR PDF 解析 / EIA 月报 | 月 |
| 全球供需平衡（供给 - 需求 = 隐含库存变化） | 柱形图（正=累库，负=去库） | EIA STEO / OPEC 月报 | 月 |
| 全球需求增速预测（当季 & 下季） | 数字卡片 + 上修/下修箭头 | EIA STEO | 月 |

### 模块 D：美国页岩油与钻井

| 指标 | 图表类型 | 数据源 | 更新频率 |
|------|----------|--------|----------|
| Baker Hughes 钻机数（石油） | 折线图（2年） | Baker Hughes / 第三方 | 周 |
| DUC 数量 | 折线图 | EIA DPR | 月 |
| 主要页岩盆地产量趋势 | 堆叠面积图（Permian, Eagle Ford, Bakken 等） | EIA DPR | 月 |

### 模块 E：价格结构与市场内部信号

| 指标 | 图表类型 | 数据源 | 更新频率 |
|------|----------|--------|----------|
| WTI 期货曲线（近 12 个月合约） | 折线图 + Back/Contango 标注 | CME / EIA | 日 |
| 近月时间价差（M1-M2, M1-M6） | 折线图（90天） | 计算字段 | 日 |
| 裂解价差 3-2-1 Crack Spread | 折线图（1年） | FRED / EIA | 日 |
| 汽油裂解价差 | 折线图 | 计算字段 | 日 |
| 柴油裂解价差 | 折线图 | 计算字段 | 日 |

**信号逻辑**：
- 近月价差 > 0（Backwardation）→ 市场紧 🟢
- 近月价差 < -$1（Deep Contango）→ 供给宽松 🔴
- 3-2-1 Crack Spread > 历史 75 分位 → 炼厂利润高 / 需求强 🟢

### 模块 F：金融条件

| 指标 | 图表类型 | 数据源 (FRED series) | 更新频率 |
|------|----------|---------------------|----------|
| 美元指数（广义贸易加权） | 折线图 + 200 日均线 | FRED `DTWEXBGS` | 日 |
| 美国 10Y 实际利率 | 折线图 | FRED `DFII10` | 日 |
| OVX 原油波动率指数 | 折线图 + 恐慌阈值线 | FRED `OVXCLS` | 日 |
| CFTC WTI 投机净多头 | 柱形图（正/负着色） | CFTC COT CSV | 周 |

**信号逻辑**：
- DXY 突破 200 日均线向上 → 利空商品 🔴
- OVX > 40 → 高波动风险 ⚠️
- 投机净多处于历史 90 分位以上 → 拥挤回撤风险 ⚠️

### 模块 G：综合信号面板（Signal Summary）

页面顶部或侧边栏固定显示一个**信号汇总卡片**：

| 维度 | 当前信号 | 基于 |
|------|----------|------|
| 库存趋势 | 🟢/🔴/⚪ | 库存连续变化方向 |
| 曲线结构 | 🟢/🔴/⚪ | Back/Contango |
| 需求强度 | 🟢/🔴/⚪ | 成品油隐含需求 vs 季节性 |
| 钻井活动 | 🟢/🔴/⚪ | 钻机数变化趋势 |
| 金融条件 | 🟢/🔴/⚪ | DXY + 实际利率 + OVX 综合 |
| 持仓拥挤度 | 🟢/🔴/⚪ | CFTC 净多头分位 |

---

## 3. 数据架构

### 3.1 数据获取层

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐
│  EIA API v2  │   │  FRED API    │   │  CFTC CSV    │
│ (petroleum)  │   │ (DTWEXBGS,   │   │ (COT weekly) │
│              │   │  DFII10,     │   │              │
│              │   │  OVXCLS)     │   │              │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────┐
│            Python ETL 脚本（定时运行）                  │
│  - 拉取 API → 清洗 → 计算衍生指标 → 输出 JSON            │
│  - 运行方式: GitHub Actions cron / 本地 crontab        │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │  /data/*.json  │  ← 静态 JSON 文件
              └────────┬───────┘
                       │
                       ▼
              ┌────────────────┐
              │  前端 Dashboard │  ← 纯客户端渲染
              │  (HTML/JS)     │
              └────────────────┘
```

### 3.2 数据文件结构

```
/data
  ├── price.json           # WTI/Brent 价格、价差
  ├── inventory.json       # 原油/汽油/馏分油/Cushing 库存
  ├── production.json      # 美国产量、炼厂开工率、进出口
  ├── demand.json          # 成品油隐含需求
  ├── opec.json            # OPEC 产量、全球供需平衡
  ├── drilling.json        # 钻机数、DUC、页岩盆地产量
  ├── futures_curve.json   # 期货曲线、时间价差
  ├── crack_spread.json    # 裂解价差
  ├── financial.json       # DXY、实际利率、OVX
  ├── cftc.json            # CFTC 持仓
  ├── signals.json         # 综合信号计算结果
  └── meta.json            # 各数据源最后更新时间戳
```

### 3.3 API Key 需求

| 服务 | Key 类型 | 申请地址 |
|------|----------|----------|
| EIA Open Data v2 | 免费 API Key | https://www.eia.gov/opendata/register.php |
| FRED | 免费 API Key | https://fred.stlouisfed.org/docs/api/api_key.html |
| CFTC | 无需 Key（公开 CSV） | — |

---

## 4. 技术选型

### 4.1 数据获取 & ETL（Python）

| 组件 | 选型 | 理由 |
|------|------|------|
| HTTP 请求 | `httpx` / `requests` | 简单可靠 |
| 数据处理 | `pandas` | 清洗、计算衍生指标 |
| 定时调度 | GitHub Actions (cron) | 零服务器成本 |
| 配置管理 | `.env` + `python-dotenv` | API Key 安全存放 |

### 4.2 前端（纯静态 SPA）

| 组件 | 选型 | 理由 |
|------|------|------|
| 框架 | 原生 HTML + Vanilla JS（或 Vue 3 轻量） | 无需构建工具，部署简单 |
| 图表库 | **ECharts** 或 **Lightweight Charts (TradingView)** | ECharts 对金融数据可视化支持好，中文友好 |
| UI 样式 | Tailwind CSS（CDN） | 快速搭建深色主题 Dashboard |
| 数据加载 | `fetch()` 读取 `/data/*.json` | 无需后端 API |

### 4.3 部署

| 方案 | 说明 |
|------|------|
| **GitHub Pages** | 免费静态托管，配合 GitHub Actions 自动更新数据 |
| **Vercel** | 备选，支持 Serverless Function（如果后期需要后端） |

---

## 5. 页面布局（Wireframe）

```
┌─────────────────────────────────────────────────────────────────┐
│  🛢️ Oil Market Dashboard                    最后更新: 2026-03-04 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────────────┐  │
│  │ WTI     │ │ Brent   │ │ WTI-Brent│ │ Signal Summary      │  │
│  │ $68.42  │ │ $72.15  │ │ -$3.73  │ │ 库存: 🟢 曲线: 🟢   │  │
│  │ +1.2%   │ │ +0.8%   │ │ Back.   │ │ 需求: ⚪ 持仓: ⚠️   │  │
│  └─────────┘ └─────────┘ └─────────┘ └──────────────────────┘  │
│                                                                 │
├──────────────────────────┬──────────────────────────────────────┤
│  📦 库存与供需            │  📈 价格结构                          │
│  ┌──────────────────┐    │  ┌──────────────────────────────┐    │
│  │ [原油库存面积图]  │    │  │ [期货曲线折线图]              │    │
│  │ 52周+5年区间带    │    │  │ 近12月合约价格               │    │
│  └──────────────────┘    │  └──────────────────────────────┘    │
│  ┌────────┐ ┌────────┐   │  ┌──────────────────────────────┐    │
│  │Cushing │ │汽油库存│   │  │ [裂解价差折线图]              │    │
│  │[折线图]│ │[面积图]│   │  │ 3-2-1 / 汽油 / 柴油          │    │
│  └────────┘ └────────┘   │  └──────────────────────────────┘    │
├──────────────────────────┼──────────────────────────────────────┤
│  🏭 产量与钻井            │  💰 金融条件                          │
│  ┌──────────────────┐    │  ┌──────────────────────────────┐    │
│  │ [产量+开工率图]   │    │  │ [DXY + 实际利率 双轴图]       │    │
│  └──────────────────┘    │  └──────────────────────────────┘    │
│  ┌──────────────────┐    │  ┌──────────────────────────────┐    │
│  │ [钻机数折线图]    │    │  │ [OVX 波动率 + CFTC持仓图]     │    │
│  └──────────────────┘    │  └──────────────────────────────┘    │
├──────────────────────────┴──────────────────────────────────────┤
│  🌐 OPEC & 全球供需平衡                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ [OPEC实际产量 vs 配额 分组柱形图] [全球供需平衡 柱形图]    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 项目结构

```
oil-dashboard/
├── README.md
├── requirements.md          # 本文档
├── .env.example             # API Key 模板
├── .github/
│   └── workflows/
│       └── update-data.yml  # GitHub Actions 定时拉取数据
├── etl/
│   ├── requirements.txt     # Python 依赖
│   ├── config.py            # 配置（API endpoints, series IDs）
│   ├── fetch_eia.py         # EIA 数据拉取
│   ├── fetch_fred.py        # FRED 数据拉取
│   ├── fetch_cftc.py        # CFTC 持仓数据拉取
│   ├── compute_signals.py   # 衍生指标 & 信号计算
│   └── run_all.py           # 入口：按顺序运行所有 ETL
├── data/                    # 生成的 JSON（被 git track 或 artifact）
│   ├── price.json
│   ├── inventory.json
│   ├── ...
│   └── meta.json
└── web/
    ├── index.html           # Dashboard 主页
    ├── css/
    │   └── style.css        # 自定义样式（深色主题）
    └── js/
        ├── app.js           # 主逻辑：加载 JSON → 渲染图表
        ├── charts.js        # ECharts 图表配置封装
        └── signals.js       # 信号卡片渲染逻辑
```

---

## 7. 开发阶段规划

### Phase 1：数据管道 MVP（1-2 周）

- [ ] 申请 EIA / FRED API Key
- [ ] 实现 `fetch_eia.py`：拉取库存、产量、炼厂开工率、需求数据
- [ ] 实现 `fetch_fred.py`：拉取 DXY、DFII10、OVX
- [ ] 实现 `fetch_cftc.py`：下载并解析 COT CSV
- [ ] 实现 `compute_signals.py`：计算价差、信号
- [ ] 输出 `/data/*.json`，验证数据完整性

### Phase 2：前端 Dashboard MVP（1-2 周）

- [ ] 搭建 HTML 页面骨架 + Tailwind 深色主题
- [ ] 实现价格总览卡片（WTI/Brent/价差/曲线状态）
- [ ] 实现库存模块图表（5 年区间带面积图）
- [ ] 实现价格结构模块（期货曲线 + 裂解价差）
- [ ] 实现金融条件模块（DXY + 利率 + OVX + CFTC）
- [ ] 实现综合信号面板

### Phase 3：自动化 & 完善（1 周）

- [ ] 配置 GitHub Actions 定时任务（每日/周触发 ETL）
- [ ] 部署到 GitHub Pages
- [ ] 添加数据更新时间戳显示
- [ ] 移动端响应式适配
- [ ] 添加 OPEC/钻井数据（如有可靠数据源）

### Phase 4：增强（可选）

- [ ] 历史数据回溯选择器（选择时间范围）
- [ ] 数据下载功能（导出 CSV）
- [ ] 邮件/Webhook 推送信号变化提醒
- [ ] 对比分析视图（同比/环比）

---

## 8. 信号计算规则详细定义

### 8.1 库存趋势信号

```python
def inventory_signal(weekly_changes: list[float], n=3) -> str:
    """最近 n 周库存变化方向"""
    recent = weekly_changes[-n:]
    if all(c < 0 for c in recent):
        return "bullish"      # 连续去库 → 利多
    elif all(c > 0 for c in recent):
        return "bearish"      # 连续累库 → 利空
    else:
        return "neutral"
```

### 8.2 曲线结构信号

```python
def curve_signal(m1_price: float, m2_price: float) -> str:
    spread = m1_price - m2_price
    if spread > 0.5:
        return "bullish"      # Backwardation
    elif spread < -1.0:
        return "bearish"      # Deep Contango
    else:
        return "neutral"
```

### 8.3 持仓拥挤度信号

```python
def positioning_signal(net_long: float, historical_series: list[float]) -> str:
    percentile = scipy.stats.percentileofscore(historical_series, net_long)
    if percentile > 90:
        return "warning"      # 过度拥挤
    elif percentile < 10:
        return "bullish"      # 极度悲观，可能反转
    else:
        return "neutral"
```

### 8.4 金融条件信号

```python
def financial_signal(dxy_vs_ma200: float, real_rate: float, ovx: float) -> str:
    score = 0
    if dxy_vs_ma200 > 0:     score -= 1   # 美元强 → 利空油
    if real_rate > 2.0:       score -= 1   # 高实际利率 → 利空风险资产
    if ovx > 40:              score -= 1   # 高波动
    
    if score <= -2:
        return "bearish"
    elif score >= 0:
        return "bullish"
    else:
        return "neutral"
```

---

## 9. 非功能性需求

| 维度 | 要求 |
|------|------|
| **性能** | 首屏加载 < 3s（JSON 总量控制在 2MB 内） |
| **可用性** | 支持 Chrome / Safari / Firefox 最新版 |
| **响应式** | 桌面端 2 列布局，平板/手机单列堆叠 |
| **主题** | 默认深色（Dark），投资类 Dashboard 标准色调 |
| **数据新鲜度** | 日频数据延迟 < 24h，周频数据延迟 < 48h |
| **错误处理** | JSON 加载失败时显示"数据暂不可用"占位符，不白屏 |
| **安全** | API Key 仅存放在 GitHub Secrets / .env，不进入前端代码 |

---

## 10. 风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| EIA/FRED API 限流或不可用 | 数据更新中断 | 本地缓存上次成功结果；加重试逻辑 |
| 期货曲线数据需付费（CME） | 模块 E 数据不完整 | 优先用 EIA 现货价格替代；或使用免费替代源（Yahoo Finance / Quandl） |
| OPEC PDF 格式变化 | 解析脚本失效 | 初期手动录入关键数字；后续迭代提升解析鲁棒性 |
| Baker Hughes 页面反爬 | 钻机数据获取困难 | 使用第三方数据聚合服务或手动更新 |
| 免费数据源延迟 | 决策时效性降低 | 对时效要求高的用户说明数据延迟情况 |

---

## 附录 A：EIA API v2 关键 Series ID

| 指标 | Series ID | 频率 |
|------|-----------|------|
| 原油商业库存（不含 SPR） | `PET.WCESTUS1.W` | 周 |
| 库欣库存 | `PET.WCUSTP11.W` | 周 |
| 汽油库存 | `PET.WGTSTUS1.W` | 周 |
| 馏分油库存 | `PET.WDISTUS1.W` | 周 |
| 美国原油产量 | `PET.WCRFPUS2.W` | 周 |
| 炼厂开工率 | `PET.WPULEUS3.W` | 周 |
| 成品油表观消费（汽油） | `PET.WGFUPUS2.W` | 周 |
| 成品油表观消费（馏分油） | `PET.WDIUPUS2.W` | 周 |
| 原油净进口 | `PET.WCRNTUS2.W` | 周 |
| WTI 现货价 | `PET.RWTC.D` | 日 |
| Brent 现货价 | `PET.RBRTE.D` | 日 |

## 附录 B：FRED Series ID

| 指标 | Series ID |
|------|-----------|
| 广义贸易加权美元指数 | `DTWEXBGS` |
| 10 年期 TIPS 实际收益率 | `DFII10` |
| OVX 原油波动率指数 | `OVXCLS` |
