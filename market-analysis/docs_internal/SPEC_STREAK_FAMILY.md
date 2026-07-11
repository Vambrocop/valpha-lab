# SPEC_STREAK_FAMILY — 连跌/反转 + 长跨度对称反转/延续 候选族规格(六步①·先验先于数据)

起草:Fable 5,2026-07-10。**用户已拍板"开"(2026-07-10),并扩范围**(见 §5)。
状态:**②审规格 R2 修订版**——独立 Opus 审规格回 REQUEST-SPEC-CHANGES,已逐条落实
B1(block 放大)/B2(stage1 即 148)/S1(warmup 常量)/S2(down=ret<0)/S3(暖机基率污染)/
S4(砍段=设计取舍)/S5(p 双侧仅解释性)/N1–N3。**交主公验落实,验过进③建造。**
来源:
- 原案(§1–4):用户 2026-07-10——"现有信号只认单日暴跌;连跌几天(每天不极端)能不能抄底?
  跌了好久后昨天首次上涨,这种怎么识别?"——经查候选池/坟场,确属空档,非旧案重提。
- 扩范围(§5–6):用户 2026-07-10——"我希望有个更长远的,比如涨了好久了会跌、跌了好久会涨,
  这样也是个信号。"→ 加一个**更长跨度、对称双向**的均值回归/延续族。**方向绝不预设**(见 §5.2 先验:
  跨度依赖——短反转/中动量/长弱反转,目的是画出这条曲线,不是赌"涨久必跌")。

## 0. 防自欺声明(命门)

- 本规格撰写前**只看过触发次数**(样本量/检验力评估),**未看任何前向收益结果**。
  计数记录(streak 族):纳指55年 连跌3/4/5天=758/363/190次·break≥3/≥5=756/189;标普99年=1423/646/307·1402/304。
- **trailing_extreme 族(§5)的触发次数尚未统计**——诚实起见不编:建造时**先只出 sel 计数做检验力核对
  (只看次数、绝不看收益),再进结果**。同一防自欺纪律照旧。
- 全网格候选**一次性全部**进 BY-FDR 分母,不许看完结果再挑;被打回的进坟场公开。
  两族合计 **44 个新候选**(streak 30 + trailing_extreme 14),**N_DECLARED 104→148**(算术见 §6)。
- 与 rebound 族同属"极端回归"母假设,streak 与 trailing_extreme 彼此也相关(尾部收益 vs 连跌是同一
  过度反应现象的不同跨度切面)——沿 optsent 先例在**各自**族声明注释里写明相关性,跨族 FDR 栏自然处理。
- **预注册时机**:44 个候选的先验**全部**写于本规格(看结果前);N_DECLARED 一次性跳到 148。
  建造/审查**可分两阶段**(streak 先、trailing_extreme 后),但分母 148 自预注册即锁定——
  首阶段复算就用 148 分母(更保守、更诚实),不因分段而"边看边扩分母"。

## 1. 族定义(两个子族·全部收盘对收盘·严格点时间)

**streak_down(连跌事件日)**:sel[t] = (到 t 收盘为止恰好连跌 N 天,runlen==N)。
- **"跌"的口径写死 `down = ret < 0`(严格小于零)**:平盘 / 四舍五入零 **断开**连跌(不算跌、也不续)。
  §0 计数 758/363/190(纳指)· 1423/646/307(标普)**正是此口径**——若实现成 `ret <= 0`
  会得 766/369/196 对不上,即为口径漂移,**建造/审查以计数复现核对**(实测计数≠声明计数=停下报告)。
- 用 ==N 事件日而非 ≥N 状态:一段 7 连跌只在深度 3/4/5 各触发一次(归不同候选),
  sel 游程恒为 1 天 → **block=hold 即可,无需 #7 式 block 放大**(状态族才需要;此处写明理由防审查问)。
- 网格:N∈{3,4,5} × index∈{sp500,nasdaq} × hold∈{1,5,20} = **18 候选**。

**streak_break(连跌后首个上涨日=反转确认)**:sel[t] = (ret[t]>0 且 到 t-1 为止连跌≥N 天)。
- "涨"= `ret[t] > 0`(严格),"连跌"沿用 streak_down 的 `down = ret < 0` 口径(runlen 同一实现)。
  §0 计数 break≥3/≥5=756/189(纳指)· 1402/304(标普)即此口径,同以计数复现核对。
- 每段连跌只触发一次;只用 t 收盘信息,无前视。
- 网格:N∈{3,5} × index∈{2} × hold∈{1,5,20} = **12 候选**。

前向:fwd = px[t+hold]/px[t]−1(严格 t+1..t+hold);**尾窗纪律**照 T1 修后范式
(fwd 以 float 含 NaN 先进 df 再 dropna 后派生 y,绝不 (NaN>0)→0)。暖机:无(runlen 从第2天可判)。

## 2. 先验(文献,写于看结果之前)

- streak_down:**短期反转**(Lehmann 1990/Jegadeesh 1990;De Bondt-Thaler 过度反应的日频形式)。
  先验方向=连跌后偏反弹(up>base);预期现代段衰减(被套利,同日历族命运)——recent_p 大概率是坎。
- streak_break:"等首根阳线"的确认式入场,文献支撑弱于①(更多是从业者启发式)。
  先验方向=弱偏正,置信低——**明写:此子族更可能被打回,打回也是有价值的公开答案**。
- **检验统计量 p 值双侧,方向先验仅作解释性**(照 positioning/optsent 注释)——先验写方向是为诚实记录
  预期、不是单边押注,更**不许事后按结果挑边**(测出反方向≠"猜错"要改叙事,是曲线上的真实一点)。

## 3. 工程接线(照 #7/rebound 先例)

- **candidate_space.py:stage 1 一次性声明全部 148**(B2 修订):`streak_candidates()`(30)**与**
  `trailing_extreme_candidates()`(14)**同批加入枚举**,**N_DECLARED 104→148 一步到位**(不是 104→134→148)。
  - **理由(命门)**:`adjudicate(expect_n)` + `len(enumerate)==N_DECLARED` 断言会把 N_DECLARED 逼成
    实枚举数;若 streak 阶段只声明 134,BY 分母偏松→更易存活,**违反 §0 分母锁定**。故 trailing 的
    14 个候选**在 stage 1 就必须被枚举出来**(哪怕 trailing 的 discovery 尚未建),靠下述"未就绪→p=1.0"兜底。
  - **子算术常量 + 对账护栏(N3)**:`N_STREAK = 30`、`N_TRAILING = 14`、`N_DECLARED = 104 + N_STREAK + N_TRAILING = 148`
    写成显式相加(不填魔数);**加一条测试**断言 `len(list(enumerate_candidates())) == N_DECLARED`
    且分族计数 == N_STREAK / N_TRAILING(分母漂移护栏,防日后误增删候选悄悄改分母)。
  - 声明注释:各族分别写先验 + 相关性(streak↔rebound↔trailing 同"极端回归"母假设)。
- autodiscovery.py:`_streak_arrays(kind, n, hold, index)`(复用 _daily_price;runlen 向量化
  `down.groupby((down==0).cumsum()).cumsum()`,其中 `down = (ret < 0)` 见 §1 S2 口径)+ `_streak()`
  统计(block=hold 块自助+现代段)+ compute_results 显式路由(H-1:不许静默落 else)。
- **trailing 未就绪期的 H-1 兜底**(B2):`compute_results` 对 trailing 候选**显式路由**到 `_trailing_extreme`;
  该函数在 stat/数据未就绪(如 streak 先落地、trailing 尚未建)时**返回 None → p=1.0**——走既有
  "数据不足→进分母、永不存活"模式,满足 H-1(不静默落 else、不把候选踢出分母)。
- oos_gate.py:`_streak_oos` 复用 _diff_oos(锚后过滤,均线类"绝不重启"问题此族不存在)。
- candidate_registry:新 44 候选(streak 30 + trailing 14)盖当日锚(append-only)。
- 测试:合成数据版恒跑(runlen 正确性/==N 单触发/break 单触发/尾窗裁剪/H-1 路由反退化/**分母对账**),
  真数据版缺 raw 则 skip(CI 纪律)。
- survivors_live:若有存活,接当前态描述符(今天连跌几天/是否 break 日——trivially PIT)。

## 4. 验收与停机条件(streak 族;全族合并验收见 §6)

- 全量复算:**既有候选零 verdict 翻转**(分母用 148——翻转即停,报用户);
- pytest 全绿;run_all 全量跑通;新旧 n_survive 写进 commit message;
- 双审:审规格(独立 Opus)+ 审实现(全新 Opus);建造=Sonnet(机械)+Fable(统计路由部分亲写或亲审逐行)。

---

## 5. 长跨度对称反转/延续子族 `trailing_extreme`(2026-07-10 用户扩范围)

母命题:**尾部累计收益极端 → 后续方向?** 对称双向覆盖用户的"涨了好久 / 跌了好久"。
灵魂 = **画出跨度曲线**(短反转→中动量→长弱反转),不是证明"涨久必跌"。

### 5.1 族定义(单指数时间序列·收盘对收盘·严格点时间)

**sel[t] = (trailing-N 累计收益处于历史极端分位)**,分 low / high 两侧对称:
- `low`  侧(跌了好久):trailing_ret_N[t] ≤ p10(t)  —— 对应用户"跌了好久"
- `high` 侧(涨了好久):trailing_ret_N[t] ≥ p90(t)  —— 对应用户"涨了好久"
- 其中 `trailing_ret_N[t] = px[t]/px[t−N] − 1`。

**前向**:fwd = px[t+hold]/px[t] − 1,up 率 vs **全样本基率**(复用现有 `_diff_windows` 口径,与 streak 族一致)。

**⚠ 两条命门(写死,不许留给建造者自定;违反=停下报告)**:

1. **分位必须点时间(PIT)**:p10(t)/p90(t) **只能用 t 时刻(含当期)及之前观测到的 trailing_ret_N 历史**算
   (expanding 经验分位,**含当期 t**——对齐既有 `_rolling_pctrank` 口径),**严禁全样本分位**
   (那是前视泄漏——本设计头号 look-ahead 陷阱)。
   - 暖机写死常量(**S1**):`_TRAILING_WARMUP = 2520`(≈10 年 trailing_ret_N 历史;照 `_POS_WINDOW=156`
     先例,**不留"建议",直接常量**)。首个可信号日要求已积累 ≥ `_TRAILING_WARMUP` 个 trailing_ret_N 观测。
     暖机吃掉早期样本是**已知代价**,如实 declare;别用"全样本 quantile"图省事。
   - **测试须含**:构造一条"全样本分位与 expanding 分位在某点判定相反"的合成序列,断言用的是 expanding、
     那点不被误触发(PIT 反泄漏锁)。
2. **这是状态族(state family),不是事件族**:trailing-N 落进尾部会**连续多天为真**(一轮熊市 = 一大段
   连续 ≤p10 日;trailing-504 尾部单段可达**数百天**,比 positioning(~51)聚簇更狠),与 streak 的
   ==N 单日事件不同 → **必须 #7 式 block 放大**(具体见 §5.3 `TRAILING_BLOCK_EXTRA`),**绝不能当独立样本、
   绝不能 block=hold**。此处与 §1 streak"block=hold 即可"的差异是**故意的**,审查者勿混淆。

### 5.2 先验(文献·跨度依赖·写于看结果之前)

**方向绝不预设为"涨久必跌"**。按 lookback 分三段,各写各的诚实先验:

| lookback N | 跨度 | 先验方向 | 文献 |
|---|---|---|---|
| 63d(3月)/126d(6月)/252d(12月) | **中** | **动量/延续**(high 侧续涨 up>base、low 侧续跌 up<base) | Jegadeesh-Titman 1993 |
| 504d(24月) | **长** | 弱反转(De Bondt-Thaler 方向:high→回落、low→反弹) | De Bondt-Thaler 1985 |

- **中跨度 = 明写"我们预期测到 NOT-反转(动量)"**——若结果是"涨的继续涨",那是**发现不是失败**
  (映射曲线的中段);把它当胜利记,不许事后改叙事成"反转失败"。
- 长跨度先验**置信低、检验力枯竭**——**大概率 inconclusive,那是预注册接受的诚实结果**,照实进坟场。
- 短跨度(日频反转)已由 §1 streak 族覆盖;1 月(21d)**考虑过但不纳入**(短期反转、紧邻 streak 族,
  且会膨胀候选数伤 FDR)——写明是为了让审查者知道这是深思后的取舍,不是遗漏。
- **p 值双侧,上表方向先验仅作解释性**(同 §2 S5)——写"中跨度预期动量"是诚实记录预期、**不是单边押注**;
  测出反方向或 inconclusive **都不许事后按结果挑边改叙事**,它们都是跨度曲线上的真实取样点。

### 5.3 网格(纪律裁剪·hold 与 lookback 匹配·共 14 候选)

**hold 每个 lookback 只配一个"成形/持有匹配"值**(去掉 hold 维度 = 最大且最可辩护的裁剪:
既控 FDR 又贴动量/反转文献的成形≈持有惯例):

| lookback N | 匹配 hold | side | index | 小计 |
|---|---|---|---|---|
| 63d | 21d | low+high | sp500+nasdaq | 4 |
| 126d | 63d | low+high | sp500+nasdaq | 4 |
| 252d | 126d | low+high | sp500+nasdaq | 4 |
| 504d | 126d | low+high | **sp500 only** | 2 |
| | | | **合计** | **14** |

**N1(504d 为何配 hold=126 而非 252)**:hold 意在测"极端之后一段可交易的前瞻期",不必等于 lookback;
252d 持有会让前向窗与成形窗量级相当、进一步压低本已稀缺的独立样本且实用性差(半年是可操作前瞻上限)。
故 504d 与 252d 共用 hold=126——**这也让"成形越长、前瞻固定"的对比更干净**(隔离 lookback 单变量)。

**block 长度(B1·写死统一放大,不许 block=hold)**:状态族 → **block = hold + `TRAILING_BLOCK_EXTRA`**,
`_trailing_extreme`(discovery)与 `_trailing_extreme_oos`(OOS)**两处同一公式、同一常量**。
- **`TRAILING_BLOCK_EXTRA` 怎么定(照 #7 `_positioning_block` 先例)**:建造时**实测**各
  (n×side×index) 的 **sel 连续极端段长度分布**(只看"状态持续多少天"、**不看任何前向收益**,防自欺安全),
  取分段长度 **p90**,再取**全族最保守(最大)**那个,**写死为常量**。trailing-504 单段可达数百天 →
  该常量会显著大于 hold(这正是命门2 要的放大;block=hold 会抬高虚假存活=反诚实)。
- **不按候选各自调 block**:全族同一常量,**否则=新增 researcher-DoF**(可挑 block 调存活率)。
- **建造顺序(写死)**:① 实现 PIT 分位 → ② 定义 sel → ③ 实测各 (n×side×index) sel 段长 p90 → ④ 定
  `TRAILING_BLOCK_EXTRA`(取全族 max)→ ⑤ 接 block 自助。**不得先拍脑袋填 block 再回填**。
- 即便如此放大,仍**如实 declare**:尾部聚簇使有效独立事件 ≪ 名义 n、CI 仍偏乐观——明写的已知局限,
  不靠视觉/措辞掩盖。现代段(recent_p)检查照 streak 族做。

**网格设计取舍:哪些跨度/指数"永不枚举"(S4·预注册前的设计裁剪,基于文献非数字断言)**:
- **不设 756d(3 年)候选**:De Bondt-Thaler 用 3–5 年成形期,而**这么长的成形+持有周期在 ~95 年史里
  天然只有极少数不重叠 episode**(文献常识,非本族实测数字——§0 已声明 trailing 触发次数尚未统计,
  故此处**不援引具体计数**)。这是**预注册前的网格设计决定 → 这些组合永不进入枚举、不占 148 分母**。
- **504d 不设 nasdaq 候选**:纳指 1971+,2 年成形+持有的不重叠周期本就稀少 → 同理设计裁剪,只枚举标普(1928+)。
- **与"枚举了但暖机后 sel 太少"严格区分(命门)**:凡**已枚举进 148** 的候选,即便暖机(10y)后有效样本
  很少,**一律留在分母、`_trailing_extreme` 返回 p=1.0 永不存活**(照"数据不足→进分母永不存活"),
  **绝不在建造期把它从枚举里删**——那会把 BY 分母拉下来、放松存活门(反诚实)。
  即:**设计期可不枚举(基于文献),枚举后绝不因样本少而回删**。

### 5.4 工程接线(照 #7/streak 先例)

- **candidate_space.py**:`trailing_extreme_candidates()` 14 个;**14 个在 stage 1 即与 streak 一起枚举**
  (见 §3 B2:N_DECLARED 一步到 **148**,不经 134 中转)+ 声明注释(§5.2 跨度依赖先验 + 与 streak/rebound 相关性)。
- **autodiscovery.py**:
  - `_trailing_extreme_arrays(n, hold, index, side)`:复用 `_daily_price`;trailing_ret_N 向量化;
    **PIT expanding 分位 helper**(暖机 `_TRAILING_WARMUP=2520`,含当期 t,见 §5.1)。
  - **三个"未成熟"来源都要从整数组 dropna(S3·堵 H-2 基率污染)**——照 positioning"裁到首个可判定状态":
    (a)**首端 formation 暖机**:前 N 天无 trailing_ret_N;
    (b)**分位暖机**:前 `_TRAILING_WARMUP` 个 trailing_ret_N 观测内分位不可信(**这是更长的那道边界**);
    (c)**尾端 forward-hold**:末 hold 天无前向。
    以上未成熟日 **sel=NaN 且从整数组 dropna(基率也一并剔)**,绝不 `(NaN)→False` 当"未触发的正常日"
    污染全样本基率;fwd 照 T1 以 float 含 NaN 先进 df 再 dropna 派生 y。
  - `_trailing_extreme()` 统计:**状态族 block 自助,block = hold + `TRAILING_BLOCK_EXTRA`**
    (§5.3 定死;**非 block=hold**)+ 现代段(recent_p)。
  - `compute_results` **显式路由**到 `_trailing_extreme`(H-1:不许静默落 else);
    **stat/数据未就绪 → 返回 None → p=1.0**(进分母永不存活,见 §3 B2 兜底)。
- **oos_gate.py**:`_trailing_extreme_oos` 复用 `_diff_oos`(锚后过滤;均线类"绝不重启"问题此族不存在);
  **block 用与 discovery 同一 `hold + TRAILING_BLOCK_EXTRA` 公式/同一常量**(B1:两处一致)。
- **candidate_registry**:14 候选盖当日锚(append-only)。
- **测试(合成数据恒跑·真数据缺 raw 则 skip)**:
  ① **PIT 反泄漏锁**(§5.1 命门1);② 状态族多日 sel 正确(连续尾部段);
  ③ **block 放大生效**(断言用的是 `hold+TRAILING_BLOCK_EXTRA` 非 hold;可用"人造长聚簇段使 block=hold
     虚假存活、放大后被杀"的对照);④ **三端裁剪**——尤其覆盖**最长的分位暖机边界(2520)**,
     不只 formation(N 天)/forward(hold 天)两个短边界,并验基率未被未成熟日污染;
  ⑤ H-1 路由反退化(缺路由 / 未就绪未走 p=1.0 能被杀);⑥ 分母对账(§3 N3,含 N_TRAILING=14)。
- **survivors_live**:若有存活,接当前态描述符(今天 trailing-N 收益在历史第几分位——trivially PIT)。

## 6. 全族合并验收与停机条件(streak §1–4 + trailing_extreme §5)

- **N_DECLARED 算术**:104(原基线)+ 30(streak:18+12)+ 14(trailing_extreme)= **148**。
  预注册即锁 148 分母;分段建造时首阶段也用 148(见 §0)。
- **零翻转停机(命门)**:全量 104+30+14 复算,**既有 104(及先落地的 streak)候选零 verdict 翻转**——
  分母增大会动 BY 阈值,**任何翻转即停机报用户**(BY 分母变大是已 declare 的已知风险)。
  验收**用脚本 diff verdict 列**,不许肉眼:改动前存现行 verdict 快照 → 复算后逐条 diff。
- **预注册接受的结果**:trailing_extreme 中跨度大概率测出**动量**(非反转)= 发现;长跨度大概率
  **inconclusive** = 诚实答案进坟场。二者都**不算失败**,不许事后改先验叙事。
- pytest 全绿;run_all 全量跑通;新旧 n_survive 写进 commit message;candidate_registry/ledger append-only。
- **双审(公开统计族)**:审规格(独立 Opus)+ 审实现(全新 Opus,与审规格者 + 建造者均不同上下文);
  建造=Sonnet(机械)+主公/Fable **亲写或逐行亲审的五处热区**(不是读建造者自述):
  ① §5.1 命门1 PIT expanding 分位 helper(含当期 t·warmup 2520);② `TRAILING_BLOCK_EXTRA` 实测定值
  (sel 段长 p90 取全族 max·只看状态不看收益);③ 三端未成熟 dropna(formation/分位暖机/forward·基率不污染);
  ④ compute_results 显式路由 + 未就绪→p=1.0 兜底;⑤ discovery 与 OOS 两处 block 公式/常量一致。
- **分块防 session 截断**:①审规格+改稿(本轮)②建 streak+测 ③审 streak+修
  ④建 trailing:先 PIT 分位→定义 sel→**实测 sel 段长定 `TRAILING_BLOCK_EXTRA`**→接 block+测(顺序写死,见 §5.3)
  ⑤审 trailing+修 ⑥全量 148 复算+零翻转脚本+提交;每块中间产物落盘,截断可续。
