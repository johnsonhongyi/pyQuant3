import time
import random
import asyncio
import pandas as pd
import json
import re
import sys

sys.path.append("..")
import JohnsonUtil.johnson_cons as ct
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct
from JSONData import tdx_hdf5_api as h5a

log = LoggerFactory.log

# =========================
# Sina Header
# =========================
sinaheader = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0',
    'Host': 'vip.stock.finance.sina.com.cn',
    'Referer': 'http://vip.stock.finance.sina.com.cn',
    'Connection': 'keep-alive',
}

# =========================
# 全局封禁状态（增强）
# =========================
g_sina_blocked = {
    'last_block_time': 0,
    'last_url': '',
    'blocked_until': 0,   # 封禁结束时间
    'reason': '',         # 封禁原因
    'count': 0,           # 连续封禁次数
    'cooling': False      # 是否在冷却模式
}


def set_blocked(seconds, reason='', url=''):
    now = time.time()
    g_sina_blocked['count'] += 1
    g_sina_blocked['last_block_time'] = now
    g_sina_blocked['reason'] = reason
    g_sina_blocked['last_url'] = url

    penalty = min(seconds * (1 + g_sina_blocked['count'] * 0.5), 600)
    g_sina_blocked['blocked_until'] = now + penalty

    log.warning(
        f"[SINA-BLOCK] count={g_sina_blocked['count']} "
        f"penalty={penalty:.1f}s reason={reason} url={url}"
    )

def set_blocked_cooling(reason='', factor=1.23, cooling_sec=300):
    """
    触发冷却模式：
    - limit_time 按 factor 放大
    - 当天禁止递减
    - 冷却时间 cooling_sec 秒
    """
    now = time.time()
    g_sina_blocked['blocked_until'] = now + cooling_sec
    g_sina_blocked['reason'] = reason
    g_sina_blocked['count'] += 1
    g_sina_blocked['cooling'] = True

    # 调整 limit_time
    if hasattr(cct, "sina_dd_limit_time"):
        new_limit = int(cct.sina_dd_limit_time * factor)
        cct.sina_dd_limit_time = new_limit
        log.warning(f"[SINA-COOLING] Triggered due to {reason}, "
                    f"limit_time increased: {new_limit}s, cooling for {cooling_sec}s")


# =========================
# 动态参数计算（功能 3 + 4）
# =========================
def _get_dynamic_fetch_params_increase(base_batch, base_pause, base_limit):
    #尽量使用limit,直到封禁
    is_trade = cct.get_work_time()
    block_cnt = g_sina_blocked['count']

    # batch_size
    if is_trade:
        batch_size = max(5, int(base_batch * 0.4))
    else:
        batch_size = base_batch

    if block_cnt > 0:
        batch_size = max(3, int(batch_size / (1 + block_cnt * 0.7)))

    # pause
    slow = 1 + block_cnt * 0.5
    pause_range = (
        round(base_pause[0] * slow, 2),
        round(base_pause[1] * slow + 0.3, 2)
    )

    # limit_time 联动
    force_cache = False
    limit_time = base_limit
    if block_cnt >= 2:
        limit_time = base_limit * (1 + block_cnt)
        force_cache = True

    return batch_size, pause_range, force_cache, limit_time

def _get_dynamic_fetch_params_noCoolTime(base_batch, base_pause, base_limit):
    """
    反向优化版：
    - base_limit 是当前“已验证安全”的缓存时间
    - 动态逻辑只允许【缩短】limit_time
    - 一旦异常，立即回退到 base_limit
    """

    is_trade = cct.get_work_time()
    block_cnt = g_sina_blocked['count']

    # =========================
    # batch_size（仍然保守）
    # =========================
    if is_trade:
        batch_size = max(5, int(base_batch * 0.4))
    else:
        batch_size = base_batch

    if block_cnt > 0:
        batch_size = max(3, int(batch_size / (1 + block_cnt * 0.7)))

    # =========================
    # pause（随封禁递增）
    # =========================
    slow = 1 + block_cnt * 0.5
    pause_range = (
        round(base_pause[0] * slow, 2),
        round(base_pause[1] * slow + 0.3, 2)
    )

    # =========================
    # limit_time：倒序缩减
    # =========================
    force_cache = False
    limit_time = base_limit

    if block_cnt >= 2:
        # 🚨 连续异常：冻结策略
        force_cache = True
        limit_time = base_limit

    elif block_cnt == 1:
        # ⚠️ 出现一次异常：不尝试缩减
        limit_time = base_limit

    else:
        # ✅ 完全正常，允许尝试缩减
        if is_trade:
            # 交易时间极保守
            shrink_factor = 0.85
        else:
            # 非交易时间可激进一些
            shrink_factor = 0.65

        limit_time = max(
            int(base_limit * shrink_factor),
            int(base_limit * 0.3)   # 下限保护，防止过快
        )

    return batch_size, pause_range, force_cache, limit_time

def _get_dynamic_fetch_params(base_batch, base_pause, base_limit):
    """
    反向优化版 + 冷却模式：
    - base_limit 是当前“已验证安全”的缓存时间
    - 异常触发冷却 -> limit_time 按系数增长
    - 正常 -> 倒序缩减
    """

    is_trade = cct.get_work_time()
    block_cnt = g_sina_blocked.get('count', 0)

    # =========================
    # 冷却模式优先
    # =========================
    if g_sina_blocked.get('cooling', False):
        batch_size = max(3, int(base_batch * 0.3))
        pause_range = (0.8, 1.2)
        force_cache = True
        limit_time = cct.sina_dd_limit_time  # 放大后的冷却值
        return batch_size, pause_range, force_cache, limit_time

    # =========================
    # batch_size（仍然保守）
    # =========================
    if is_trade:
        batch_size = max(5, int(base_batch * 0.4))
    else:
        batch_size = base_batch

    if block_cnt > 0:
        batch_size = max(3, int(batch_size / (1 + block_cnt * 0.7)))

    # =========================
    # pause（随封禁递增）
    # =========================
    slow = 1 + block_cnt * 0.5
    pause_range = (
        round(base_pause[0] * slow, 2),
        round(base_pause[1] * slow + 0.3, 2)
    )

    # =========================
    # limit_time：倒序缩减
    # =========================
    force_cache = False
    limit_time = base_limit

    if block_cnt >= 2:
        # 🚨 连续异常：冻结策略
        force_cache = True
        limit_time = base_limit

    elif block_cnt == 1:
        # ⚠️ 出现一次异常：不尝试缩减
        limit_time = base_limit

    else:
        # ✅ 完全正常，允许尝试缩减
        shrink_factor = 0.85 if is_trade else 0.65
        limit_time = max(int(base_limit * shrink_factor), int(base_limit * 0.3))

    return batch_size, pause_range, force_cache, limit_time

# =========================
# URL 构建
# =========================
def _get_sina_Market_url(market='sh_a', num='200'):
    url_list = []
    url = ct.JSON_Market_Center_CountURL % market
    data = cct.get_url_data(url, timeout=10)
    cnt = re.findall('(\d+)', data or '')
    if cnt:
        page_cnt = max(1, -(-int(cnt[0]) // int(num)))
        for p in range(1, page_cnt + 1):
            url_list.append(ct.JSON_Market_Center_RealURL % (p, num, market))
    return url_list


# =========================
# 数据解析（强风控识别）
# =========================
def _parsing_Market_price_json(url):
    text = cct.get_url_data_R(url, headers=sinaheader)
    if not text:
        raise ValueError("empty response")
    if text in ('null', 'None') or text.startswith('<html'):
        raise ValueError("blocked html/null")

    try:
        text = text.replace('changepercent', 'percent').replace('turnoverratio', 'ratio')
        js = json.loads(text)
    except Exception:
        raise ValueError("json decode failed")

    df = pd.DataFrame(js, columns=ct.SINA_Market_COLUMNS)
    df = df.loc[df.volume >= 0]
    if df.empty:
        raise ValueError("empty dataframe")

    return df


# =========================
# 异步抓取（自适应节流）
# =========================
async def _fetch_with_delay(url, pause_range):
    now = time.time()
    if now < g_sina_blocked['blocked_until']:
        wait = g_sina_blocked['blocked_until'] - now
        log.warning(f"[SINA-WAIT] {wait:.1f}s")
        await asyncio.sleep(wait)

    try:
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, _parsing_Market_price_json, url)
    except Exception as e:
        log.error(f"Fetch url error: {url}, {e}")
        # 触发冷却模式
        set_blocked_cooling(reason=str(e), factor=1.23, cooling_sec=300)
        df = None
        set_blocked(60, str(e), url)
        return None

    sleep_t = random.uniform(*pause_range)
    await asyncio.sleep(sleep_t)
    return df

def _can_update_limit_time_base(base_limit, limit_time):
    """
    判断是否满足写回 global.ini 的条件
    """
    # 时间条件
    now = time.localtime()
    if not (now.tm_hour == 14 and now.tm_min >= 50 or now.tm_hour > 14):
        return False

    # 必须真的缩小了
    if limit_time >= base_limit:
        return False

    # 当天必须没有被封
    if g_sina_blocked['count'] > 0:
        return False

    # 防止极端缩减
    if limit_time < int(base_limit * 0.3):
        return False

    return True


def _can_update_limit_time(
    base_limit,
    limit_time,
    min_sample_sec=10800,    # 至少 15 分钟安全样本
):
    """
    判断是否允许将 limit_time 写回 global.ini
    条件：
    1. 每天只允许写一次
    2. 当天必须无封禁
    3. 必须有足够安全运行样本
    4. 只允许 14:50 ~ 15:00 窗口
    5. limit_time 必须真实缩小
    """

    now = time.localtime()

    # ========= 时间窗口限制 =========
    # 14:50 <= time < 15:00
    if not (
        (now.tm_hour == 14 and now.tm_min >= 50) or
        (now.tm_hour == 15 and now.tm_min == 0)
    ):
        return False

    # 15:00 之后禁止
    if now.tm_hour >= 15 and now.tm_min > 0:
        return False

    # ========= 必须真实缩小 =========
    if limit_time >= base_limit:
        return False

    # ========= 当天不能被封 =========
    if g_sina_blocked.get('count', 0) > 0:
        return False

    # ========= 最小安全样本 =========
    # 使用首次成功获取时间作为样本起点
    first_ok_ts = getattr(cct, '_sina_first_ok_ts', None)
    if not first_ok_ts:
        return False

    if time.time() - first_ok_ts < min_sample_sec:
        return False

    # ========= 每天只写一次 =========
    today = time.strftime("%Y%m%d", now)

    # last_write_day = cct.CFG.get("general","sina_dd_limit_day",fallback="")
    last_write_day = cct.CFG.get_with_writeback(
        section="general",
        option="sina_dd_limit_day",
        fallback="0",       # 默认是 0，表示未写
        value_type="str"
        )

    if last_write_day == today:
        return False

    return True

def _update_sina_limit_time(limit_time):
    """
    写入 global.ini，并同步更新 cct.sina_dd_limit_time（内存态）
    """
    try:
        limit_time = int(limit_time)
        cct.CFG.set_and_save(
            section="general",
            key="sina_dd_limit_time",
            value=limit_time
        )

        # 🔑 同步模块级缓存值（关键）
        cct.sina_dd_limit_time = limit_time
        today = time.strftime("%Y%m%d")
        cct.CFG.set_and_save(
            section="general",
            key="sina_dd_limit_day",
            value=today
        )
        log.warning(
            f"[SINA-LIMIT-UPDATE] sina_dd_limit_time={limit_time}"
        )
        return True

    except Exception as e:
        log.error(f"[SINA-LIMIT-UPDATE-FAIL] {e}")
        return False

# =========================
# 主入口（完整优化版）
# =========================
def get_sina_Market_json(market='all', showtime=True, num='100', batch_size=50, pause_range=(0.2, 0.5)):
    start = time.time()
    h5_fname = 'get_sina_all_ratio'
    h5_table = f'all_{num}'
    base_limit = cct.sina_dd_limit_time

    batch_size, pause_range, force_cache, limit_time = _get_dynamic_fetch_params(
        batch_size, pause_range, base_limit
    )

    log.info(f'batch_size:{batch_size} pause_range:{pause_range} force_cache:{force_cache} limit_time:{limit_time}')
    # --------- HDF 缓存 ---------
    h5 = h5a.load_hdf_db(h5_fname, table=h5_table, limit_time=limit_time)
    if h5 is not None and len(h5) > 0 and 'timel' in h5.columns:
        o_time = h5[h5.timel != 0].timel
        if len(o_time) > 0:
            l_time = time.time() - o_time.iloc[0]
            if force_cache or l_time < limit_time:
                log.warning(f"[HDF-USE] rows={len(h5)} l_time={l_time:.1f}")
                return h5

    # --------- URL 构建 ---------
    url_list = []
    # SINA_Market_KEY = {'sh': 'sh_a', 'sz': 'sz_a', 'cyb': 'cyb','kcb':'kcb','bj':'hs_bjs'}
    if market == 'all':
        for m in ('sh_a', 'sz_a' ,'hs_bjs'):
            url_list.extend(_get_sina_Market_url(m, num))
    else:
        url_list = _get_sina_Market_url(ct.SINA_Market_KEY.get(market, market), num)

    if not url_list:
        log.error("no url list")
        return []

    log.info(
        f"[SINA-FETCH] urls={len(url_list)} batch={batch_size} "
        f"pause={pause_range} block={g_sina_blocked['count']}"
    )

    df_list = []
    loop = asyncio.get_event_loop()

    for i in range(0, len(url_list), batch_size):
        tasks = [_fetch_with_delay(u, pause_range) for u in url_list[i:i + batch_size]]
        try:
            rs = loop.run_until_complete(asyncio.gather(*tasks))
        except Exception as e:
            set_blocked(120, f"batch error:{e}")
            break

        for r in rs:
            if r is not None and not r.empty:
                df_list.append(r)

    if not df_list:
        log.error("no data fetched")
        return []

    df = pd.concat(df_list, ignore_index=True)
    if 'ratio' in df.columns:
        df['ratio'] = df['ratio'].astype(float).round(1)
    if 'percent' in df.columns:
        df['percent'] = df['percent'].astype(float).round(2)
    df = df.drop_duplicates('code').set_index('code')

    h5a.write_hdf_db(h5_fname, df, table=h5_table, append=False)

    if showtime:
        print(f"Market-df:{time.time() - start:.1f}s {len(df)}", end=' ')

    # =========================
    # 14:50 后自动收敛 limit_time
    # =========================
    if not hasattr(cct, "_sina_first_ok_ts"):
        cct._sina_first_ok_ts = time.time()
    if _can_update_limit_time(base_limit, limit_time):
        log.warning(
            f"[SINA-LIMIT-CANDIDATE] base={base_limit} new={limit_time}"
        )
        _update_sina_limit_time(limit_time)

    return df


# =========================
# 测试
# =========================
if __name__ == '__main__':
    log.setLevel(LoggerFactory.INFO)
    df = get_sina_Market_json()
    import ipdb; ipdb.set_trace()
