# SPEC_STREAK_FAMILY — 连跌/反转确认 候选族规格(六步①·先验先于数据)

起草:Fable 5,2026-07-10。状态:**规格已定稿,等用户点头才进②审规格→③建造→登记**。
来源:用户 2026-07-10 提出——"现有信号只认单日暴跌;连跌几天(每天不极端)能不能抄底?
跌了好久后昨天首次上涨,这种怎么识别?"——经查候选池/坟场,确属空档,非旧案重提。

## 0. 防自欺声明(命门)

- 本规格撰写前**只看过触发次数**(样本量/检验力评估),**未看任何前向收益结果**。
  计数记录:纳指55年 连跌3/4/5天=758/363/190次·break≥3/≥5=756/189;标普99年=1423/646/307·1402/304。
- 全网格 30 个候选**一次性全部**进 BY-FDR 分母,不许看完结果再挑;被打回的进坟场公开。
- 与 rebound 族同属"极端回归"母假设,存在相关性——沿 optsent 先例在族声明注释里写明,
  跨族 FDR 栏自然处理。

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

## 4. 验收与停机条件

- 全量 104+30 复算:**既有 104 候选零 verdict 翻转**(分母变大会动 BY 阈值——翻转即停,报用户);
- pytest 全绿;run_all 全量跑通;新旧 n_survive 写进 commit message;
- 双审:审规格(独立 Opus)+ 审实现(全新 Opus);建造=Sonnet(机械)+Fable(统计路由部分亲写或亲审逐行)。
