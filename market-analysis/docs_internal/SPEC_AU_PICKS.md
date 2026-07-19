# SPEC_AU_PICKS — 澳股荐股 + 零调参回测(B3·六步协议)

> Fable 主脑亲写规格(2026-07-17)。**R2:②全新 Opus 独立审出 2 BLOCKER + 7 SHOULD + 5 NIT,
> 已全部落入本版**(B-1 FMG 截断须实证 / B-2 股息口径不对称须披露 / S-1 forward_ledger 零改)。
> B3 = 澳洲区最重一件:荐股进独立 append-only 公开计分账本 + **同一规则零调参回测披露门**。
> 六步:①规格 → ②独立审规格(done·R2)→ ③建(账本 Sonnet/回测 Opus)→ ④审(账本 Fable/
> 回测双审 Fable+全新 Opus)→ ⑤修 → ⑥Fable 亲验数字+提交。

## 0. 定位与红线
- 与美股 pick_ledger 完全同构:**敢荐就敢认账**——每条荐股入场→满 HOLD_TD 交易日 vs 基准自动结算→公开胜率。
- **独立账本 `data/au_pick_ledger.csv`,绝不与美股混**(基准不同不可比);挂 ledger_sidecar 哈希链。
- **披露门(用户拍板语义,防走形)**:门=披露门非表现门——`au_backtest.json` + au.html 回测披露块与荐股区
  **同一 commit** 上线,**结果好坏照登**。"回测好才上线"=发表偏倚,不是选项。结果很差→照发布,上线与否
  带结果升级用户。数据质量问题(拆股垃圾/断档)→真停机修数据。
- **股息口径不对称(B-2·必披露)**:个股序列=含息复权总回报(auto_adjust),^AXJO=除息价格指数 →
  存在 ≈股息率(AU ~4%/年 ≈0.3%/20td)的**持续性口径顺风,对「看好」系统性有利——这不是 edge**。
  live 账本 caveat + 回测 meta/页面都必须明写。〔口径判断点·已默认 lean:保留 ^AXJO(33.6y 长史)+
  强披露,而非换 TR ETF 基准(STW 2008 起,砍 ~15 年史);拍板后可换,一行改〕
- 非投资建议、不可交易(成本/滑点/税)、会错、过去≠未来——caveat 全套照美股 + AU 专属注。

## 1. `au_pick_ledger.py` — 荐股账本(pick_ledger 配置级克隆)

### 1.1 规则与口径零克隆(防漂移命门)
**直接 `from pick_ledger import _select_picks, _outcome, _followable, MOM_WIN, VOL_WIN, N_PICKS`——
绝不复制函数体**(S-1:_outcome/_followable 皆 bench-agnostic,复制=埋漂移)。两市场规则/命中口径=
同一份代码;AU 只自写薄 `_settle` 包一层(BENCH="^AXJO", HOLD_TD=20)。`PICK_RULE` 文案 AU 自带
(注明"与美股同一规则、同一代码")。

### 1.2 配置差异(全部差异仅此)
| 项 | 美股 | AU |
|---|---|---|
| UNIVERSE | raw/stocks_prices.csv | **raw/au/au_stocks_prices.csv**(新·§1.3) |
| BENCH | QQQ | **^AXJO**(本地取价·§1.4) |
| HOLD_TD | 20 | 20(同) |
| LOG | data/pick_ledger.csv | data/au_pick_ledger.csv |
| 币种 | USD | **AUD 本币**(两腿同币零汇率调整) |
| 输出 | pick_ledger.json | au_picks.json(web+docs) |

**N-1 键一致性(防静默丢票)**:宽表列名 = `.AX` ticker = `_select_picks` 输出 symbol = settle 的
px 字典键;bench 键锁 `"^AXJO"`(fetch_data_au 的 series.name 已是 `^AXJO`,**文件名 AXJO.csv ≠ 键名**,
建造时别把文件名当键)。

### 1.3 fetch_data_au 顺手落宽表
股票循环里已有各票 Series——顺手拼宽表 `raw/au/au_stocks_prices.csv`(date×ticker,28 列,
与美股 stocks_prices.csv 同构)。~5 行,不改现有单票 csv 输出。

### 1.4 forward_ledger **零改**(S-1·审后修正)
`fl.settle` 的 bench 只是传入 px 字典的键(`px.get(bench)`),**从不调 yfinance**。
AU 在自己的 `run()` 里从 raw/au/*.csv 拼本地 px 字典(28 票 + `"^AXJO"` 键)喂现成 `fl.settle`,
**forward_ledger 一个字节不动**——美股回归风险归零。§3.7 测试保留作守门。
入场=出榜**次日收盘**(面板只有收盘价);满 HOLD_TD 交易日结算;命中口径经 import 的 `_outcome`
与美股逐字节同。HEADER 同美股 15 列。append-only,幂等。

### 1.5 AU 专属 caveat(美股全套之上追加)
- **股息口径不对称声明(B-2 全文)**;
- franking 不含(无可靠免费源宁缺勿猜);
- 池=ASX50 精选 28 只(现全高流动性档);ASX 本地日=交易日;
- FMG 在池但规则窗口(126d)须全落在实证真起点之后(§2.2 B-1 的截断对 live 面板同样适用——
  **宽表里 FMG 截断日前置 NaN,live 与回测同一份截断逻辑**,单一真相源);
- 池(28 巨头)≈ ^AXJO 主导权重 → 超额天然被压("打赢你自己"),AU 集中度比美股更极端(N-3)。

### 1.6 挂接
run_all 挂 `au_checkup.py` 之后;不入 --light;ledger_sidecar 加 au_pick_ledger.csv;
au.html 加「荐股(独立计分)」区(照 picks.html 骨架·当期名单+攒战绩提示+账本表·zh/en·as-of 铁律)。

## 2. `au_pick_backtest.py` — 同一规则零调参回测(披露门)

### 2.1 定位(诚实语义·页面大字·全部进 meta 供 S-6 机器守门)
**这不是"策略验证",是"同一规则的历史轨迹披露"**:
> ⚠ **回测池 = 今天的 ASX50 成分回望**(1993 年的你不可能知道今天谁在池里)——含严重幸存者偏差,
> 结果系统性偏乐观。前向公开计分(账本)才是真裁决。
另四条(同进 meta):
- **股息口径顺风**(B-2):含息个股 vs 除息指数,「看好」侧系统性受益,非 edge;
- **非独立性**(S-5):同决策日 6 只同截面强相关 + AU 银行/矿业集中 → 有效独立样本 ≪ 记录条数,
  hit% 只作描述、不可当胜率精度;
- **相位锁定**(S-4):决策日从最早可行日起每 HOLD_TD 交易日一个(确定性、预注册、无挑选);
  结果对 20 个相位起点敏感,本回测锁最早可行相位、不做相位扫描(扫描=调参,§2.4 禁)——已披露局限;
- 非重叠窗口、无多重校正(单一预注册规则)、描述性、过去≠未来。

### 2.2 机制(零调参 = 只用 §1 同款常量与同一 `_select_picks`)
- 数据:raw/au 单票全史 csv 拼面板(**fail-soft:某票 csv 缺失→该票缺席+计数,不崩**·N-5);基准 ^AXJO。
- **B-1·FMG 截断须实证(建造者第 0 步,硬前置)**:dump FMG 2002–2004 **逐日价格+量级**,定位壳价
  ($0.00x)→真价($x.xx)的跳变日,截断日=**该实证日期**(不许用圆整 2003-01-01)。宽表中截断日前
  全 NaN;**FMG 在"实证真起点 + 126 个干净交易日"之前不可选**(NaN-through-cutoff 自然满足,仍须
  单测断言首个可选动量窗不跨边界)。实证日期若不干净(多段跳变/无法定位)→ **停下报告**。
- **S-3·老票身份逐一扫全**:共享千禧前起始日的全部老票(≈14 只:BHP/NAB/WBC/ANZ/WES/RIO/WDS/QBE/
  STO/JHX/SHL/AMC/SUN/FMG),逐票 dump 1988–1992 价格量级人眼核对(WDS 2022 更名、JHX/AMC 海外重域
  是易踩点)。发现壳价级异常 → 同 FMG 处理并停报。**抽样在 honesty-critical 数据门上是不必要的赌**。
- 滚动:锚点=**最早可行决策日**(bench+126 暖机就绪日,确定性),此后每 HOLD_TD 交易日一个决策日
  (非重叠);**末端护栏(S-7):其后不足 HOLD_TD+1 交易日的决策日不生成**(历史回测不该有 pending)。
- PIT:决策只用 `px.loc[:asof]` 切片(_select_picks 的 rank 是当日截面、vol/mom 只回看——②审已核
  "切片正确即零前瞻");
- **入场/出场复用 `fl.fwd`(S-2)**:每决策日对选中票与 ^AXJO 各调 `fl.fwd`(followable=次日起,
  hold=HOLD_TD, trading_days=True),**与 live 账本逐字节同逻辑**——入场=次交易日收盘、出场=其后第
  HOLD_TD 交易日收盘。禁止手搓入场循环(off-by-one 温床)。
- 退市/窗内缺价:该条 dropped+计数(与 `_followable` 同语义)——注意 dropped 处理**不解决** §2.1 的
  结构性幸存者偏差,文案别混淆两者。

### 2.3 输出 `au_backtest.json`(web+docs)
- 总体:n_calls、n_settled、hit 率(总/看好/看淡)、call_excess 均值+中位、dropped 计数;
- 分年:每年 n/hit率/平均 call_excess + **当年可选票数**(N-2:让读者直观看到早年幸存者池多薄);
- meta:rule(引 PICK_RULE)、hold、bench、期间、**§2.1 五条声明全文**(幸存者/股息口径/非独立性/
  相位/描述性)、FMG 实证截断日与依据、generated。
- au.html 荐股区内嵌「回测披露」块(同一 commit·结果好坏照登·zh/en)。

### 2.4 统计边界(别越)
不做显著性检验/p 值;不做参数扫描/相位扫描;不与美股回测比较排名。

## 3. 测试(pytest·合成面板不碰网络——raw/au 已 gitignore,CI 无真数据)
1. 规则零克隆守门:`au_pick_ledger._select_picks is pick_ledger._select_picks`(同一对象;
   _outcome/_followable 同);
2. 账本幂等/append-only(照 test_ipo_alerts 范式);
3. 回测 PIT:构造未来暴涨票,断言不影响切片决策日的选择;
4. **B-1 跨边界守门**:构造壳/真跳变合成序列(0.001→5.0),断言截断后首个可选动量窗**不含跨边界价**
   (即动量非天文数字);2002 前 NaN/截断后有值;
5. 非重叠+锚定:相邻决策日间隔==HOLD_TD 交易日,首决策日==最早可行日;
6. **S-2 入场纪律**:`entry_date > 决策日`(次日,防抢跑);
7. dropped 语义:窗内缺价不入结算、计数正确;
8. 美股回归:pick_ledger 现路径不动(forward_ledger 零改,此测为守门);
9. **S-6 披露机器门**:断言 au_backtest.json.meta 含幸存者偏差/FMG 截断/股息口径三声明关键字段
   (防声明被静默删——披露门从人眼门升级为机器门);
10. N-4 两腿对齐:合成面板上断言个股腿与 bench 腿 entry/exit 日期一致。

## 4. 建造分工与审查(六步落位)
- ③ 账本+宽表+前端 = Sonnet;回测 = Opus(算法+PIT+B-1 实证)。
- ④ 账本 = Fable 单审;**回测 = 双审(Fable + 全新 Opus)**。
- ⑥ Fable 亲验:抽 2 个决策日手算 call_excess 对账;分年表与总体对账;五条声明页面可见。

## 停机点
- 回测结果差 → **照发布**,上线与否带结果升级用户(沉默跳过不是选项);
- FMG 实证截断日不干净(多段跳变/定位不了)→ 停报;
- 老票逐一扫出壳价异常 → 同 FMG 处理后停报重跑;
- 数据质量问题(拆股垃圾/断档)→ 真停机修数据;
- 任何人想加显著性声称/参数扫描/相位扫描/换规则重跑 → 停(吹票机的门)。
