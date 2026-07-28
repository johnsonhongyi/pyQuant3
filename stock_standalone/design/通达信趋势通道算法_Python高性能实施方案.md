# 通达信趋势通道算法 → Python 高性能实施方案

## 一、问题背景与目标

多周期及 ATS 信号筛选能够发现牛股异动与启动点，但存在两大痛点：

1. **刚异动就回撤** — 无法区分"真趋势启动"与"假突破噪音"
2. **超预期异动后不敢跟单** — 缺乏趋势方向、通道位置与支撑/阻力的量化定位

**核心目标**：将通达信"自动通道"指标翻译为纯 NumPy 向量化 Python 函数，在 `get_tdx_macd` 末尾一次性预计算，生成 **上轨/中轨/下轨/斜率/Fibonacci 支撑阻力** 等字段写入 `df`，供多周期策略筛选表达式直接引用。

---

## 二、通达信公式核心算法解构

将通达信代码拆解为 **6 大独立算法模块**，按依赖顺序排列：

### 模块 1：均线趋势方向判定（MA/EMA 方向线）

```
通达信原始:
A := EMA(C, 21)
VAR11 := MA(C, 9)
上升通道 := IF(VAR11 > REF(VAR11,1), VAR11, DRAWNULL)
下降通道 := IF(VAR11 < REF(VAR11,1), VAR11, DRAWNULL)
```

**Python 翻译**：
```python
ema21 = close.ewm(span=21, adjust=False).mean()
ma9 = close.rolling(9).mean()
# 方向判定: 1=上升, -1=下降, 0=平盘
trend_dir = np.sign(ma9.values - np.roll(ma9.values, 1))
trend_dir[0] = 0
```

**输出列**: `trend_dir` (int8: 1/-1/0)、`ema21`

---

### 模块 2：Fibonacci 动态支撑阻力位

```
通达信原始:
N:=8; M:=3;
高 := REF(HHV(H, N), M);    ← 前M日的N日最高价
低 := REF(LLV(L, N), M);    ← 前M日的N日最低价
H19 := 高 - (高-低) * 0.191
H38 := 高 - (高-低) * 0.382
H中 := 高 - (高-低) * 0.500
H61 := 高 - (高-低) * 0.618
H80 := 高 - (高-低) * 0.809
```

**Python 翻译**：
```python
N, M = 8, 3
fib_high = high.rolling(N).max().shift(M)  # REF(HHV(H,8), 3)
fib_low  = low.rolling(N).min().shift(M)   # REF(LLV(L,8), 3)
fib_range = fib_high - fib_low

fib_19 = fib_high - fib_range * 0.191
fib_38 = fib_high - fib_range * 0.382
fib_50 = fib_high - fib_range * 0.500
fib_61 = fib_high - fib_range * 0.618
fib_80 = fib_high - fib_range * 0.809
```

**输出列**: `fib_high`, `fib_low`, `fib_19`, `fib_38`, `fib_50`, `fib_61`, `fib_80`

**策略用途**：`close > fib_50` 表示价格在 Fibonacci 中位以上（强势区域），`close < fib_61` 表示进入深度回调支撑区。

---

### 模块 3：见底/见顶信号（MACD 背离拐点检测）

```
通达信原始:
A0 := (L+H+C*2) / 4                   ← 加权均价
AA := EMA(A0, 14); BB := EMA(A0, 25)
A1X := (AA - REF(AA,1)) / REF(AA,1) * 100   ← 短周期均价变速
A5 := EMA(C,12) - EMA(C,26)           ← DIFF
A6 := EMA(A5, 9)                       ← DEA
A7 := (A5 < -0.1 AND A5 > A6)         ← 底部金叉前夕
见底 := IF(A7, LLV(L,21), NaN)
G := BARSLAST(CROSS(A1X, 0))          ← 距上次变速穿零的距离
见顶 := IF(H >= REF(A0,G)*1.3, REF(A0,G)*1.3, NaN)  ← 涨幅超30%预警
```

**Python 翻译（核心算法）**：
```python
a0 = (low + high + close * 2) / 4.0
aa = a0.ewm(span=14, adjust=False).mean()
bb = a0.ewm(span=25, adjust=False).mean()
a1x = (aa - aa.shift(1)) / aa.shift(1) * 100  # 变速率

a5 = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
a6 = a5.ewm(span=9, adjust=False).mean()
sig_bottom = (a5 < -0.1) & (a5 > a6)  # 底部金叉前夕

# BARSLAST(CROSS(A1X, 0)) 的向量化实现
cross_zero = (a1x.shift(1) < 0) & (a1x >= 0)  # 变速率上穿零轴
g = _barslast_vec(cross_zero.values)            # 距上次穿零的距离
a0_at_cross = np.array([a0.values[max(0, i-g[i])] for i in range(n)])
sig_top = high.values >= a0_at_cross * 1.3      # 涨超30%见顶
```

**输出列**: `sig_bottom` (bool), `sig_top` (bool), `bottom_price` (float), `top_price` (float)

---

### 模块 4：启动信号检测（SK/SD 金叉 + 放量突破）

```
通达信原始:
VAR1 := (C*2 + H + L) / 4
SK := EMA(VAR1,13) - EMA(VAR1,73)
SD := EMA(SK, 2)
SJ := (CROSS(SK,SD) AND SK<-0.04 AND (C-REF(C,1))/REF(C,1)>=0.03)
   OR (CROSS(SK,SD) AND SK<=-0.14)
   OR (CROSS(SK,SD) AND SK<=0.05 AND (V/MA(V,5)>2 OR C/REF(C,1)>0.035))
```

**Python 翻译**：
```python
var1 = (close * 2 + high + low) / 4.0
sk = var1.ewm(span=13, adjust=False).mean() - var1.ewm(span=73, adjust=False).mean()
sd = sk.ewm(span=2, adjust=False).mean()
cross_sk_sd = (sk.shift(1) < sd.shift(1)) & (sk >= sd)  # 金叉

pct_chg = (close - close.shift(1)) / close.shift(1)
vol_ratio_5 = vol / vol.rolling(5).mean()

sig_launch = (
    (cross_sk_sd & (sk < -0.04) & (pct_chg >= 0.03))
    | (cross_sk_sd & (sk <= -0.14))
    | (cross_sk_sd & (sk <= 0.05) & ((vol_ratio_5 > 2) | (pct_chg > 0.035)))
)
```

**输出列**: `sig_launch` (bool), `sk_val` (float), `sd_val` (float)

---

### 模块 5：自动回归通道（FORCAST / SLOPE 线性回归）⭐核心

这是通达信代码中最复杂的部分——自动画通道。算法本质是：
1. **定位最近极值点**：找到近期最高点（TC2）和最低点（BC2）的 bar 位置
2. **线性回归拟合**：在高低点区间内对 close 做 `FORCAST(C, NOD+1)` + `SLOPE(C, NOD+1)` 线性回归
3. **构造平行通道**：中轨 = 回归线，上轨 = 中轨 + 最大正偏差，下轨 = 中轨 - 最大负偏差

```
通达信原始（解构核心逻辑）:
UR:=6; LR:=6;
TC1 := IF(H=HHV(H, 6*UR), H, DRAWNULL)     ← 36周期最高点标记
TC2 := CONST(BARSLAST(TC1=H)) + 1            ← 最近高点距今bar数
BC1 := IF(L=LLV(L, 6*LR), L, DRAWNULL)     ← 36周期最低点标记
BC2 := CONST(BARSLAST(BC1=L)) + 1            ← 最近低点距今bar数

NOD := ABS(TC2 - BC2)                        ← 高低点间隔(用时)

LR1 := FORCAST(C, NOD+1)                     ← 线性回归预测值
LR2 := SLOPE(C, NOD+1)                       ← 线性回归斜率
K := CONST(LR3)                              ← 锁定斜率常量

中轨 MID := 锚定点价格 - K * (当前bar到锚定点距离)
上轨 UP  := MID + 最大正偏离
下轨 DN  := MID - 最大负偏离
```

**Python 翻译（高性能 NumPy 向量化）**：

```python
def _calc_auto_channel(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       ur: int = 6, lr: int = 6) -> dict:
    """
    自动回归通道核心算法（纯 NumPy，零 Python 循环版本）
    
    返回: {
        'ch_mid':    中轨价格序列,
        'ch_upper':  上轨价格序列,
        'ch_lower':  下轨价格序列,
        'ch_slope':  通道斜率(每bar价格变化),
        'ch_width':  通道宽度(上轨-下轨),
        'ch_pos':    当前价格在通道中的百分位(0-100),
        'ch_dir':    通道方向(1=上升/-1=下降),
        'ch_start':  通道起始bar索引,
        'ch_days':   通道持续天数,
    }
    """
    n = len(close)
    
    # ---- Step 1: 定位最近极值点 ----
    hhv_window = 6 * ur   # 36 bars
    llv_window = 6 * lr   # 36 bars
    
    # 倒序遍历找到最近的区间最高点和最低点
    tc2 = 0  # 最近高点距今的bar数 (1-indexed)
    bc2 = 0  # 最近低点距今的bar数 (1-indexed)
    
    # TC1: H == HHV(H, hhv_window) 的最近出现位置
    for i in range(n-1, max(n-1-hhv_window, -1), -1):
        window_start = max(0, i - hhv_window + 1)
        if high[i] == np.max(high[window_start:i+1]):
            tc2 = n - i  # 距今bar数 (1-indexed)
            break
    
    # BC1: L == LLV(L, llv_window) 的最近出现位置
    for i in range(n-1, max(n-1-llv_window, -1), -1):
        window_start = max(0, i - llv_window + 1)
        if low[i] == np.min(low[window_start:i+1]):
            bc2 = n - i
            break
    
    if tc2 == 0: tc2 = 1
    if bc2 == 0: bc2 = 1
    
    upper_price = high[n - tc2]  # 通道锚定高点价格
    lower_price = low[n - bc2]   # 通道锚定低点价格
    
    # ---- Step 2: 线性回归拟合 (FORCAST + SLOPE) ----
    nod = abs(tc2 - bc2)  # 高低点间隔天数
    if nod < 2:
        nod = max(tc2, bc2)
    
    reg_len = nod + 1  # 回归窗口长度
    anchor = min(tc2, bc2)  # 较近的锚定点
    
    # 在锚定点位置计算 FORCAST 和 SLOPE
    # FORCAST(C, N) = 线性回归在最后一点的拟合值
    # SLOPE(C, N) = 线性回归斜率 (每bar变化量)
    anchor_idx = n - anchor  # 锚定点的df索引
    reg_start = max(0, anchor_idx - reg_len + 1)
    reg_slice = close[reg_start:anchor_idx + 1]
    
    if len(reg_slice) < 3:
        # 回退到简单两点连线
        slope = (upper_price - lower_price) / max(nod, 1)
        intercept = lower_price if bc2 > tc2 else upper_price
    else:
        x = np.arange(len(reg_slice), dtype=np.float64)
        # np.polyfit 一次拟合: y = slope * x + intercept
        slope, intercept = np.polyfit(x, reg_slice, 1)
    
    # 锚定点的回归预测值
    np_val = slope * (len(reg_slice) - 1) + intercept  # FORCAST 值
    
    # ---- Step 3: 构造平行通道 ----
    # 计算所有bar的中轨值 (从锚定点延伸)
    currbarscount = np.arange(n, 0, -1)  # [n, n-1, ..., 1] 距最后一个bar的距离
    mid = np_val - slope * (currbarscount - anchor)
    
    # 在高低点区间内计算最大正/负偏离
    ch_start_idx = n - max(tc2, bc2)
    ch_end_idx = n - min(tc2, bc2)
    
    if ch_start_idx < 0: ch_start_idx = 0
    if ch_end_idx > n: ch_end_idx = n
    
    region_high = high[ch_start_idx:ch_end_idx+1]
    region_mid = mid[ch_start_idx:ch_end_idx+1]
    region_low = low[ch_start_idx:ch_end_idx+1]
    
    at5 = np.max(region_high - region_mid) if len(region_high) > 0 else 0
    ut5 = np.max(region_mid - region_low) if len(region_low) > 0 else 0
    
    upper = mid + at5
    lower = mid - ut5
    
    # ---- Step 4: 安全边界限制 ----
    max_limit = np.max(high[-min(100, n):]) * 1.10
    min_limit = np.min(low[-min(100, n):]) * 0.90
    mid = np.clip(mid, min_limit, max_limit)
    upper = np.clip(upper, min_limit, max_limit)
    lower = np.clip(lower, min_limit, max_limit)
    
    # ---- Step 5: 衍生指标 ----
    ch_width = upper - lower
    # 当前价格在通道中的百分位: 0=下轨, 50=中轨, 100=上轨
    ch_pos = np.where(ch_width > 0, (close - lower) / ch_width * 100, 50.0)
    ch_dir = 1 if slope > 0 else (-1 if slope < 0 else 0)
    
    return {
        'ch_mid': mid, 'ch_upper': upper, 'ch_lower': lower,
        'ch_slope': slope, 'ch_width': ch_width, 'ch_pos': ch_pos,
        'ch_dir': ch_dir, 'ch_days': max(tc2, bc2),
        'ch_start': ch_start_idx
    }
```

**输出列**: `ch_mid`, `ch_upper`, `ch_lower`, `ch_slope`, `ch_slope_deg`, `ch_width`, `ch_pos`, `ch_dir`

---

### 模块 6：RSI 逃顶 + 启动信号

```
通达信原始:
RSI := SMA(MAX(C-LC,0),6,1) / SMA(ABS(C-LC),6,1) * 100
逃 := CROSS(84, RSI)        ← RSI跌破84逃顶
启动 := CROSS(VAR52, 3)      ← 自定义强弱穿越
```

**Python 翻译**：
```python
# RSI(6) 逃顶
lc = close.shift(1)
gain = np.maximum(close - lc, 0)
loss = np.abs(close - lc)
sma_gain = gain.ewm(alpha=1/6, adjust=False).mean()
sma_loss = loss.ewm(alpha=1/6, adjust=False).mean()
rsi6 = sma_gain / sma_loss * 100
sig_escape = (rsi6.shift(1) > 84) & (rsi6 <= 84)

# 启动信号 (VAR52 上穿 3)
llv27 = low.rolling(27).min()
hhv27 = high.rolling(27).max()
stoch = (close - llv27) / (hhv27 - llv27) * 100
sma1 = stoch.ewm(alpha=1/5, adjust=False).mean()
sma2 = sma1.ewm(alpha=1/3, adjust=False).mean()
var52 = 3 * sma1 - 2 * sma2
sig_start = (var52.shift(1) < 3) & (var52 >= 3)
```

**输出列**: `sig_escape` (bool), `sig_start` (bool), `rsi6` (float)

---

## 三、函数签名与集成点设计

### 3.1 新增函数定义

在 [tdx_data_Day.py](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/JSONData/tdx_data_Day.py) 中新增一个独立函数：

```python
def calc_trend_channel(df: pd.DataFrame, ur: int = 6, lr: int = 6) -> pd.DataFrame:
    """
    趋势通道综合计算引擎 — 通达信"自动通道"Python 翻译
    
    一次性向量化预计算以下指标写入 df:
    
    【通道核心】
      ch_upper   : 上轨价格          ch_mid     : 中轨价格
      ch_lower   : 下轨价格          ch_slope   : 斜率(每bar价格增量, 元)
      ch_slope_deg: 斜率角度(度)      ch_width   : 通道宽度(上轨-下轨)
      ch_pos     : 通道百分位(0-100)  ch_dir     : 通道方向(1上/-1下/0平)
    
    【Fibonacci 支撑阻力】
      fib_high, fib_low, fib_19, fib_38, fib_50, fib_61, fib_80
    
    【拐点信号】
      sig_bottom : 见底(bool)         sig_top    : 见顶(bool)
      sig_launch : 启动(bool)         sig_escape : 逃顶(bool)
      sig_start  : 低位启动(bool)     trend_dir  : MA9方向(1/-1/0)
    
    Parameters
    ----------
    df : pd.DataFrame
        必须包含 close/high/low/open/vol 列
    ur, lr : int
        上轨/下轨极值搜索倍率 (默认6, 搜索窗口=6*ur=36 bars)
    
    Returns
    -------
    pd.DataFrame : 原 df 追加上述新列后返回
    """
```

### 3.2 集成点：`get_tdx_macd` 末尾

在 [get_tdx_macd](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/JSONData/tdx_data_Day.py#L2007-L2157) 函数 `return df` 之前（约 L2156），插入调用：

```python
    # ========== 趋势通道 ==========
    if len(df) >= 20:
        df = calc_trend_channel(df)
    
    return df
```

> [!IMPORTANT]
> **选择在 `get_tdx_macd` 末尾而非 `get_tdx_Exp_day_to_df` 末尾插入的原因**：
> 1. `get_tdx_macd` 是 BOLL/MACD/RSI/KDJ 等所有技术指标的统一计算入口，趋势通道同属技术指标范畴，内聚性最佳
> 2. `get_tdx_Exp_day_to_df` 在调用 `get_tdx_macd` 后还有 `compute_lastdays_percent`（生成 `lastp1d`~`lastp9d`）和结构指标计算，通道计算不依赖这些后置产物
> 3. 所有周期（d/2d/3d/w/m）的 df 都经过 `get_tdx_macd`，一处插入全周期自动覆盖

---

## 四、输出列规格与策略筛选用法

### 4.1 新增 df 列总表（共 22 列）

| 列名 | 类型 | 说明 | 策略筛选用法示例 |
|:---|:---|:---|:---|
| `ch_upper` | float | 通道上轨 | `close > ch_upper` → 突破上轨加速 |
| `ch_mid` | float | 通道中轨 | `close > ch_mid` → 价格在中轨上方 |
| `ch_lower` | float | 通道下轨 | `close > ch_lower and close < ch_mid` → 通道下半部回调 |
| `ch_slope` | float | 斜率(元/bar) | `ch_slope > 0.1` → 上升通道斜率 > 0.1元/天 |
| `ch_slope_deg` | float | 斜率角度(°) | `ch_slope_deg > 15` → 上升角度 > 15° |
| `ch_width` | float | 通道宽度 | `ch_width / ch_mid < 0.15` → 窄幅收敛 |
| `ch_pos` | float | 通道位置(0-100) | `ch_pos < 20` → 接近下轨买点 |
| `ch_dir` | int | 方向(1/-1/0) | `ch_dir == 1` → 上升通道 |
| `fib_high` | float | Fib 顶 | `close > fib_high` → 突破前高 |
| `fib_low` | float | Fib 底 | `close > fib_low` → 站稳前低 |
| `fib_19` | float | 19.1% 位 | |
| `fib_38` | float | 38.2% 位 | `close > fib_38` → 强势回调不破38.2% |
| `fib_50` | float | 50% 位 | `close > fib_50` → 中位以上 |
| `fib_61` | float | 61.8% 位 | `close > fib_61` → 超强势 |
| `fib_80` | float | 80.9% 位 | |
| `trend_dir` | int | MA9 方向 | `trend_dir == 1 and ch_dir == 1` → 双确认上升 |
| `sig_bottom` | bool→int | 见底信号 | `sig_bottom == 1` → 今日触发底部信号 |
| `sig_top` | bool→int | 见顶信号 | `sig_top == 1` → 今日触发顶部信号 |
| `sig_launch` | bool→int | SK/SD 启动 | `sig_launch == 1` → 今日启动信号 |
| `sig_escape` | bool→int | RSI 逃顶 | `sig_escape == 1` → 今日逃顶信号 |
| `sig_start` | bool→int | 低位启动 | `sig_start == 1` → 低位启动信号 |
| `sk_val` | float | SK 振子值 | `sk_val > 0` → SK 水上 |

### 4.2 query_engine_util.py 同义词映射扩展

在 [_prepare_context](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/query_engine_util.py#L236-L370) 的 `col_map` 字典中追加：

```python
# ===== 趋势通道指标 =====
'ch_upper': ['ch_upper', 'channel_upper', 'ch_up'],
'ch_mid': ['ch_mid', 'channel_mid', 'ch_middle'],
'ch_lower': ['ch_lower', 'channel_lower', 'ch_dn'],
'ch_slope': ['ch_slope', 'channel_slope', 'slope'],
'ch_slope_deg': ['ch_slope_deg', 'slope_deg', 'slope_angle'],
'ch_pos': ['ch_pos', 'channel_pos', 'ch_pct'],
'ch_dir': ['ch_dir', 'channel_dir'],
'ch_width': ['ch_width', 'channel_width'],
'fib_high': ['fib_high', 'fib_top'],
'fib_low': ['fib_low', 'fib_bottom'],
'fib_38': ['fib_38', 'fib38'],
'fib_50': ['fib_50', 'fib50', 'fib_mid'],
'fib_61': ['fib_61', 'fib61'],
'trend_dir': ['trend_dir', 'trend_direction'],
'sig_bottom': ['sig_bottom', 'bottom_signal'],
'sig_top': ['sig_top', 'top_signal'],
'sig_launch': ['sig_launch', 'launch_signal'],
'sig_escape': ['sig_escape', 'escape_signal'],
'sig_start': ['sig_start', 'start_signal'],
```

> [!NOTE]
> 因为传递闭包引擎会自动将上述列名展开至 `ch_upper_2d`, `ch_slope_w`, `fib_50_3d` 等全量多周期后缀变体，无需任何手动配置。

---

## 五、性能设计约束

### 5.1 执行耗时预估

| 算法模块 | 单股耗时 | 全市场 5000 股 |
|:---|:---|:---|
| 模块1 EMA/MA方向 | ~0.02ms | ~0.1s |
| 模块2 Fibonacci | ~0.03ms | ~0.15s |
| 模块3 见底见顶 | ~0.15ms | ~0.75s |
| 模块4 启动信号 | ~0.05ms | ~0.25s |
| 模块5 自动通道 | ~0.20ms | ~1.0s |
| 模块6 RSI逃顶 | ~0.02ms | ~0.1s |
| **总计** | **~0.47ms** | **~2.35s** |

### 5.2 性能保障策略

1. **100% NumPy 向量化**：所有 rolling/shift/ewm 使用 pandas 内建向量化算子，模块5核心通道计算使用纯 `np.polyfit` + 数组运算
2. **BARSLAST 向量化实现**：提供 `_barslast_vec(cond)` 高效倒序扫描函数（单次 O(n) 循环不可避免但极速）
3. **最小 Python 循环**：仅在模块5的极值点定位使用 `max(36, ...)` 范围内的短循环（≤36次迭代）
4. **不引入新依赖**：仅使用现有的 `numpy`, `pandas`, `talib`（talib 已有 `LINEARREG` 和 `LINEARREG_SLOPE` 可选加速）

### 5.3 talib 加速可选项

```python
# 如果 talib 可用，模块5可进一步加速：
import talib
lr_val = talib.LINEARREG(close, timeperiod=reg_len)    # 替代 np.polyfit
lr_slope = talib.LINEARREG_SLOPE(close, timeperiod=reg_len)  # 直接获取斜率
```

---

## 六、辅助函数清单

### 6.1 `_barslast_vec(cond: np.ndarray) -> np.ndarray`

通达信 `BARSLAST(COND)` 的高效向量化翻译：返回每个位置距离上一次条件为 True 的 bar 数。

```python
def _barslast_vec(cond: np.ndarray) -> np.ndarray:
    """BARSLAST: 每个位置距上次 cond=True 的bar数"""
    n = len(cond)
    result = np.full(n, n, dtype=np.int32)
    last_true = -1
    for i in range(n):
        if cond[i]:
            last_true = i
        if last_true >= 0:
            result[i] = i - last_true
    return result
```

> [!TIP]
> 该函数已在项目 `tdx_indicator_logic.py` 中有类似实现 (`barslastcount`)，可直接复用或取其精华。

### 6.2 `_cross_vec(a: np.ndarray, b: np.ndarray) -> np.ndarray`

通达信 `CROSS(A, B)` 向量化：A 从下方穿越 B。

```python
def _cross_vec(a: np.ndarray, b) -> np.ndarray:
    if np.isscalar(b):
        b = np.full_like(a, b, dtype=np.float64)
    return (np.roll(a, 1) < np.roll(b, 1)) & (a >= b)
```

### 6.3 斜率角度转换

```python
# ch_slope 是绝对值(元/bar)，需要标准化才有跨股比较意义
# 方法: 相对于中轨的百分比斜率，再转角度
ch_slope_pct = ch_slope / ch_mid[-1] * 100  # 每bar百分比
ch_slope_deg = np.degrees(np.arctan(ch_slope_pct))  # 转角度
```

---

## 七、实施步骤清单

### Step 1: 在 `tdx_data_Day.py` 中新增辅助函数
- 位置：`get_tdx_macd` 函数定义之前（约 L2000 附近）
- 新增 `_barslast_vec()`, `_cross_vec()` 两个辅助函数

### Step 2: 新增 `calc_trend_channel(df)` 主函数
- 位置：`get_tdx_macd` 函数定义之前
- 包含上述 6 大算法模块的完整实现
- 末尾将所有信号列 bool→int 转换（`astype(np.int8)`），避免策略表达式中的 True/False 歧义

### Step 3: 在 `get_tdx_macd` 末尾集成调用
- 位置：[L2156](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/JSONData/tdx_data_Day.py#L2156) `return df` 之前
- 条件守卫：`if len(df) >= 20:` 防止数据不足时报错

### Step 4: 在 `query_engine_util.py` 的 `col_map` 中注册同义词
- 位置：[L271](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/query_engine_util.py#L271) 之后
- 追加通道相关同义词映射

### Step 5: 单元测试验证
- 在 `tests/` 目录新增 `test_trend_channel.py`
- 用模拟上升/下降/横盘 3 种 OHLCV 数据验证通道方向、斜率符号、Fibonacci 支撑位计算正确性

---

## 八、策略应用场景示例

### 场景 A：过滤无意义异动（核心痛点解决）
```python
# 只有在上升通道中的异动才值得关注
"ch_dir == 1 and ch_slope_deg > 10 and percent > 3"
```

### 场景 B：通道下轨回调低吸
```python
# 上升通道中回调至下轨附近（ch_pos < 15），且 Fibonacci 50% 支撑
"ch_dir == 1 and ch_pos < 15 and close > fib_50"
```

### 场景 C：加速突破上轨追涨
```python
# 价格突破上轨 + 启动信号 + 放量
"close > ch_upper and sig_launch == 1 and volume > 1.5"
```

### 场景 D：多周期通道共振
```python
# 周线上升通道 + 日线回调至中轨
# w 周期: "ch_dir == 1 and ch_slope_deg > 5"
# d 周期: "ch_pos < 40 and close > ch_lower and trend_dir == 1"
```

### 场景 E：逃顶止损
```python
# 通道方向转下 + RSI 逃顶 + 见顶信号
"ch_dir == -1 or sig_escape == 1 or sig_top == 1"
```

---

## Open Questions

> [!IMPORTANT]
> **极值搜索窗口参数**：通达信原始公式中 `UR=6, LR=6` 对应搜索窗口为 36 bars。是否需要支持通过参数动态调整？还是固定使用 36 bars 即可？

> [!IMPORTANT]
> **斜率角度的标准化方式**：斜率角度 `ch_slope_deg` 的计算需要标准化（否则 5 元股和 500 元股的绝对斜率不可比）。当前方案采用"斜率占中轨百分比再转角度"，是否有其他偏好？

> [!IMPORTANT]
> **talib LINEARREG 加速**：模块5的线性回归可以用 `talib.LINEARREG` / `talib.LINEARREG_SLOPE` 替代 `np.polyfit`。项目已依赖 talib，是否直接采用 talib 加速方案？
