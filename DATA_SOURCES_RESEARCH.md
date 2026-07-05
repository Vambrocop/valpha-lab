# 新数据源可行性调研(#7·2026-07-03 实测存档)

> 全部候选**当天真实 curl 实测**(✅=200 拿到真数据)。senate 教训前置:免费源先验活再谈。
> 硬门槛:①历史≥5年(理想10+) ②免费/近免费 ③CI 服务端稳定可抓 ④澳洲可达。
> 任何接入都必须:先验写死(文献先验·非看数据编)→ 预注册 candidate_registry → placebo/FDR/OOS 门。

## 🏆 Top 3(历史长度 × 可靠性 × 接入成本)

### ① CFTC COT 期货持仓(仓位族 `positioning`)
- **Legacy 1986+(40年) / TFF 金融期货细分 2006+**;美国政府源=可靠性天花板;零 key 零反爬。
- 端点(实测✅):`cftc.gov/files/dea/history/deacot{年}.zip`、`fut_fin_txt_{年}.zip`、回填包 `deacot1986_2016.zip`。周五 15:30 ET 发布周二数据。
- 候选形态:`{legacy非商业|TFF杠杆基金} × {3年分位<10|>90} × {持有10/20/60日}` ≈12 个;先验=COT 文献(Wang 2003 等):大投机者持仓极端后反转。
- **点时间纪律(命门)**:as-of 周二、周五发布 → 回测统一 lag ≥3 交易日,否则前视。

### ② CBOE Put/Call 比(期权情绪)
- **2006-11→今 ~20 年可无缝拼接**(本次调研最大发现):冻结 CSV(2006→2019-10-04·实测在线)+ 每日 JSON 归档(2019-10-07→今·实测边界)。与项目现有 CBOE CDN(VIX)同源同姿势=接入成本最低。
- 端点(实测✅):`cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpc.csv`(+equitypc);`cdn.cboe.com/data/us/options/market_statistics/daily/{YYYY-MM-DD}_daily_options`(今日 total P/C=0.90)。
- 候选:`{total|equity-only} × {1年滚动z>2|<-2} × {未来10/20日}` ≈8 个;先验=期权情绪经典文献(P/C 极高=恐慌对冲极值→反向偏多;equity-only 更纯)。
- 口径:2012-06 变更+市占漂移 → **只用滚动 z,绝不用绝对阈值**。回填≈1700 个 JSON 请求(1req/s 一次性)。

### ③ NAAIM 仓位指数(与 COT 同族·主动管理人视角)
- **2006-07→今(实测解析 xlsx:1045 周·最新 2026-07-01 mean=84.69)**;官方免费;周四发周三数据。
- 端点(实测✅):`naaim.org/programs/naaim-exposure-index/` 页面→当期 `USE_Data-since-Inception_*.xlsx`(文件名带日期须每次刮页面)。
- 候选:`{mean<30投降|mean>95亢奋|8周变化<-40} × {未来20/40日}` ≈6 个;先验=仓位/情绪极值反向(Baker & Wurgler 谱系)。AAII 免费通道已死,NAAIM 正好补位。

## 第 4 名(顺手项·非主推)
**CNN Fear & Greed**:2020-09-21→今仅 5.8 年;非官方 API(`production.dataviz.cnn.io/.../graphdata/{date}`·一把拉全量 1MB);裸 curl=418 需浏览器头;**CI 机房 IP 未实测**;与现有 VIX/动量部分冗余。若接:第一件事把全量 JSON commit 进仓库当不可变备份。

## 其它可用但低优先
- **EPU 政策不确定性**(1985+·41年·直链CSV✅):先验是"预测波动强、方向弱"→风险预测族。
- **UMich 消费者信心**(1952+·FRED 已接零新基建✅):月频喂不动 N 日 FDR 池,适合当体制调节变量。
- **Wikipedia 金融词条浏览**(2015+✅):噪声大,娱乐性候选。
- **FINRA 融资余额**(1997+·月):页面活但取数管道未走通(Query API 需免费注册),待验证。

## 🚫 别碰名单(实测死/墙/灰)
AAII(会员墙+Incapsula 403·第三方镜像=ToS 灰) · StockTwits(API 暂停注册+CF 403) · Google Trends/pytrends(库 2025-04 归档·裸请求秒 429·官方 API alpha 限邀且仅 1800 天) · Reddit WSB 历史(Pushshift 已死·存档 ToS 灰+NLP 工程大) · Nasdaq Data Link AAII 镜像(403) · Baker Hughes(两域名连不通+先验弱)。

## 遗留待验证
1. CNN API 在 GitHub Actions 机房 IP 是否被拦(接入前 CI 探活)。
2. FINRA Query API(需免费注册)未走通。

---

# 命门相声明规格(#7·2026-07-04 Fable 亲笔·六步①·待 Opus 审规格)

> 两新族进 candidate_space FDR 池。**先验先于数据写死**(下述全部先验来自文献,非看本仓数据挑的);
> 全部候选进 BY-FDR 分母(禁预筛);registry sync 自动锚定 declared_date=注册日,门4 前向累积。

## A. `positioning` 族(COT·16 候选)
- **网格(有限·写死)**:`{market: sp500, nasdaq100} × {series: legacy_noncomm_pct_oi, tff_lev_net_pct_oi} × {extreme: 低(<10) , 高(>90) 滚动3年分位} × {hold: 20, 60 交易日}` = **16**。
- **指标**:legacy=非商业净头寸/OI(数据已算好);TFF=杠杆基金净头寸/OI(载入时算·scale-free 跨年代可比)。
- **状态型 sel**(照 regime 金叉先例):交易日 t 的 sel = "最近一份 `usable_from ≤ t` 的报告落在极端区"——状态持续到下一份报告生效。**点时间铁律:只准用 usable_from,分位窗=纯回看滚动 156 周(不足 156 周不判)**。
- **前向目标**:market=sp500→SP500_long;nasdaq100→NASDAQ_COMP(声明为代理·诚实标注)。
- **先验(Wang 2003·Sanders et al. COT 文献)**:大投机者净头寸极端偏多(>90 分位)→ 未来偏弱;极端偏空(<10)→ 未来偏强(反向)。**方向只作解释性先验;p 按 diff 族既有标准=双侧块自助(block=hold·保守)**。

## B. `options_sentiment` 族(P/C·8 候选)
- **网格**:`{series: total_pc, equity_pc} × {extreme: z>+2(恐慌), z<−2(自满)} × {hold: 10, 20}` = **8**。
- **指标**:滚动 252 日 z(纯回看窗含当日 t·收盘已知;暖机不足 252 日不判)。**绝不用绝对阈值**(2012 口径变更/市占漂移·滚动 z 天然吸收)。
- **sel**:日频状态(z 在极端区的交易日);前向照 rebound 惯例从 t 起算 hold 日。目标=SP500_long(P/C 是全市场情绪·标普为市场代理·声明)。
- **先验(期权情绪经典文献)**:P/C 极高=恐慌对冲极值→反向偏多;极低=自满→偏弱。同上,方向为解释先验、p 双侧。

## C. 机器接线(与裁决共用同一定义·永不漂移)
- `autodiscovery.py` 新增 `_positioning_arrays(market,series,extreme)` / `_optsent_arrays(series,extreme)` 返回 (idx, sel, y)——**阈值全为纯回看滚动统计=天然点时间**;走 `_diff_windows` + `block_bootstrap_diff(block=hold)`(rebound/regime 同款)。
- `candidate_space.py`:两族网格声明(append-only 注释记日期/先验/文献);**N_DECLARED 80→104**;test 对账 pin 同步。
- `oos_gate.py`:两族接 `_diff_oos`(arrays 全样本构建·floor 只滤 (sel,y) 到锚后·block=hold)——滚动阈值本身点时间,比 rebound 的"全样本阈值"更干净;full_sign 仍取全样本(注册时既定假说方向·oos 只查锚后同向+p)。
- 前端:discoveries PLAIN_MAP 两族大白话条目(照 opex 先例);survivors_live 描述符**这批不加**(等它们真 survive 再加·防未 survive 先上台)。
- 防泄漏守门测试(必须有):合成数据改"未来段"不得改变任何"过去日"的 sel/阈值;usable_from 之前的报告绝不参与当日 sel。

## D. 判断点(供 Opus 审规格挑)
1. 网格 24 个是否过大(稀释 FDR 检验力)?备选=各砍一档 hold → 12。我倾向 24(诚实全进分母)。
2. 状态型 sel(regime 先例) vs 事件型(仅切换日)——我选状态型,数据多且语义贴"当前仓位环境"。
3. p 用双侧(diff 族标准·保守)而先验只做解释——是否接受?(日历族才有单边机器)
4. NASDAQ_COMP 代理 NDX 期货前向、SP500 代理全市场 P/C 前向——代理声明是否足够诚实?
5. TFF lev_net/OI 归一是否合理(OI 含全部持仓类别)?
6. 警戒:两族都是"极端分位→反转"型——与 rebound 族(p5 跌进极端)在"极端回归"母假设上相关,FDR 跨族栏会自然处理,但要不要在声明注释里明记这层相关(诚实)?我倾向记。

## E. 审②定稿(2026-07-04·全新 Opus 审规格·主脑全盘采纳)
**裁决:改三件即 SOUND-TO-BUILD。** JP1 网格24保留(BY penalty仅+5%·砍档=HARKing);JP3/4/5/6 采纳。
**必改(已并入下方定稿):**
1. **JP2·block 放大(方法学必改)**:Opus 实测极端状态持续期——positioning 是多周状态(episode p90≈30-50交易日·全史仅40-56个独立episode),`block=hold` 会漏掉状态持续段→p 系统性低估→假阳冒进跨族FDR。**定:positioning block = hold + 日 sel-run p90(建造者在真数组实测·估 hold20→block≈60、hold60→≈100),discovery 与 OOS 两处同放大;optsent 尖峰(中位1天)block=hold 保留。**步骤④须报 block 敏感性(新旧块 survive/dead 是否翻转)。别拿 regime block=20 当先例(那是既有欠覆盖非背书)。
2. **H-1 BLOCKER·dispatch 显式加两族**:`autodiscovery.compute_results`(else→fac.get→None→p=1.0 静默永死)与 `oos_gate.oos_verdict`(else→"因子族待接"错误pending)两处必须显式路由 + 防退化测试(两族拿真 p≠1.0·OOS note≠因子族待接)。
3. **H-2 BLOCKER·数组裁剪**:(idx,sel,y) 裁到 ≥ 该 series 首个 usable 报告日(SP500_long 回溯1927·不裁=拿2000+极端日对1927+基率作差=年代错配污染 discovery p)。
**实现陷阱(H-3~H-8·照办)**:156 份**周频报告**上滚分位(绝非156天);sel 用 merge_asof backward(usable_from≤t);前向窗**严格 t+1..t+hold**;market 映射 nasdaq100→"nasdaq";extreme 用 hi/lo 干净token;test_every_candidate_has_shape 白名单加两族+per-family 计数+防泄漏守门(改未来段不改过去 sel/z/分位)。
**记录(H-9~11)**:数据不足→None→p=1.0 诚实;长期 pending 是预期(equity_pc z<-2 全史仅34天·OOS要攒多年);full_sign=全样本数据方向非文献先验(注释写清·先验只解释)。
