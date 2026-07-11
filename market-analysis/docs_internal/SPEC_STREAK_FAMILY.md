# SPEC_STREAK_FAMILY — 连跌/反转 + 长跨度对称反转/延续 候选族规格(六步①·先验先于数据)

起草:Fable 5,2026-07-10。**用户已拍板"开"(2026-07-10),并扩范围**(见 §5)。
状态:**规格修订版定稿**(streak 族 §1–4 原稿 + trailing_extreme 长跨度族 §5–6 加厚),进②审规格→③建造→登记。
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
- 用 ==N 事件日而非 ≥N 状态:一段 7 连跌只在深度 3/4/5 各触发一次(归不同候选),
  sel 游程恒为 1 天 → **block=hold 即可,无需 #7 式 block 放大**(状态族才需要;此处写明理由防审查问)。
- 网格:N∈{3,4,5} × index∈{sp500,nasdaq} × hold∈{1,5,20} = **18 候选**。

**streak_break(连跌后首个上涨日=反转确认)**:sel[t] = (ret[t]>0 且 到 t-1 为止连跌≥N 天)。
- 每段连跌只触发一次;只用 t 收盘信息,无前视。
- 网格:N∈{3,5} × index∈{2} × hold∈{1,5,20} = **12 候选**。

前向:fwd = px[t+hold]/px[t]−1(严格 t+1..t+hold);**尾窗纪律**照 T1 修后范式
(fwd 以 float 含 NaN 先进 df 再 dropna 后派生 y,绝不 (NaN>0)→0)。暖机:无(runlen 从第2天可判)。

## 2. 先验(文献,写于看结果之前)

- streak_down:**短期反转**(Lehmann 1990/Jegadeesh 1990;De Bondt-Thaler 过度反应的日频形式)。
  先验方向=连跌后偏反弹(up>base);预期现代段衰减(被套利,同日历族命运)——recent_p 大概率是坎。
- streak_break:"等首根阳线"的确认式入场,文献支撑弱于①(更多是从业者启发式)。
  先验方向=弱偏正,置信低——**明写:此子族更可能被打回,打回也是有价值的公开答案**。

## 3. 工程接线(照 #7/rebound 先例)

- candidate_space.py:`streak_candidates()` 30 个 + N_DECLARED 104→**134** + 声明注释(先验+相关性)。
- autodiscovery.py:`_streak_arrays(kind, n, hold, index)`(复用 _daily_price;runlen 向量化
  `down.groupby((down==0).cumsum()).cumsum()`)+ `_streak()` 统计(block=hold 块自助+现代段)
  + compute_results 显式路由(H-1:不许静默落 else)。
- oos_gate.py:`_streak_oos` 复用 _diff_oos(锚后过滤,均线类"绝不重启"问题此族不存在)。
- candidate_registry:新 30 候选盖当日锚(append-only)。
- 测试:合成数据版恒跑(runlen 正确性/==N 单触发/break 单触发/尾窗裁剪/H-1 路由反退化),
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

1. **分位必须点时间(PIT)**:p10(t)/p90(t) **只能用 t 时刻之前观测到的 trailing_ret_N 历史**算(expanding
   经验分位 + 暖机),**严禁全样本分位**(那是前视泄漏——本设计头号 look-ahead 陷阱)。
   - 推荐实现:expanding 经验分位,首个可信号日要求 ≥ **min_warmup**(建议 10 年 trailing_ret_N 历史)。
     暖机吃掉早期样本是**已知代价**,如实 declare;别用"全样本 quantile"图省事。
   - **测试须含**:构造一条"全样本分位与 expanding 分位在某点判定相反"的合成序列,断言用的是 expanding、
     那点不被误触发(PIT 反泄漏锁)。
2. **这是状态族(state family),不是事件族**:trailing-N 落进尾部会**连续多天为真**(一轮熊市 = 一大段
   连续 ≤p10 日),与 streak 的 ==N 单日事件不同 → **必须 #7 式 block 放大**(block 见 5.3),
   不能当独立样本。此处与 §1 streak"block=hold 即可"的差异是**故意的**,审查者勿混淆。

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

**block 长度**:状态族 → block = **max(hold, 成形自相关尺度)**;实作取 **block = hold**(前向重叠)
为下限,并**如实 declare**:trailing-N 尾部聚簇使有效独立事件 ≪ 名义 n,置信区间偏乐观——
这是**明写的已知局限**,不靠视觉/措辞掩盖。现代段(recent_p)检查照 streak 族做。

**我主动砍的段(coordinator 授权"数据不足就砍,别硬凑")**:
- **砍 756d(3年)**:De Bondt-Thaler 虽用 3–5 年成形期,但历史上"涨/跌 3 年"的**独立 episode < ~10 个**,
  诚实测不了 → 不纳入。504d(2年)`sp500 only` 即长段的诚实锚点。
- **504d 砍 nasdaq**:纳指 1971+,2 年成形 + 持有的独立周期太少,只留标普(1928+)。
- 若 504d 跑完**普遍 inconclusive**,亦为**预注册接受结果**(进坟场,如实公开)。

### 5.4 工程接线(照 #7/streak 先例)

- **candidate_space.py**:`trailing_extreme_candidates()` 14 个 + N_DECLARED 134→**148** + 声明注释
  (§5.2 跨度依赖先验 + 与 streak/rebound 相关性)。
- **autodiscovery.py**:
  - `_trailing_extreme_arrays(n, hold, index, side)`:复用 `_daily_price`;
    trailing_ret_N 向量化;**PIT expanding 分位 helper**(暖机 min_warmup);
    **首端 formation 暖机 + 尾端 forward-hold** 两端都要 NaN 处理(照 T1:fwd 以 float 含 NaN 先进 df
    再 dropna 派生 y;formation 未成熟段 sel=NaN 排除,别 (NaN)→False 误触发)。
  - `_trailing_extreme()` 统计:**状态族 block 自助(block=hold)** + 现代段(recent_p)。
  - `compute_results` **显式路由**(H-1:不许静默落 else)。
- **oos_gate.py**:`_trailing_extreme_oos` 复用 `_diff_oos`(锚后过滤;均线类"绝不重启"问题此族不存在)。
- **candidate_registry**:14 候选盖当日锚(append-only)。
- **测试(合成数据恒跑·真数据缺 raw 则 skip)**:
  ① **PIT 反泄漏锁**(5.1 命门1);② 状态族多日 sel 正确(连续尾部段);③ block 放大生效;
  ④ **两端窗裁剪**(formation 首端 + forward 尾端);⑤ H-1 路由反退化(缺路由能被杀)。
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
  建造=Sonnet(机械)+主公/Fable(§5.1 两条命门 + PIT 分位 helper + compute_results 路由 + 尾/首窗
  这四处**亲写或逐行亲审**,不是读建造者自述)。
- **分块防 session 截断**:①审规格+改稿 ②建 streak+测 ③审 streak+修 ④建 trailing_extreme+测
  ⑤审 trailing_extreme+修 ⑥全量复算+零翻转脚本+提交;每块中间产物落盘,截断可续。
