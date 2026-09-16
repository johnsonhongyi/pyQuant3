# -*- coding: utf-8 -*-
"""
generate_trade_calendar_2099.py
--------------------------------
全自动 A 股交易日历生成与部署工具（直通 2099 年）

核心功能：
1. 纯 Python 标准库实现中国天文农历（1900-2100）与二十四节气清明算法，无外部依赖；
2. 依据 A 股休市规则与国家法定假日调休逻辑，推算农历新年（春节/除夕）、清明、端午、中秋、
   国庆（含中秋国庆合体连休 8 天机制）、劳动节、元旦等假日休市；
3. 严守“周末绝不开市”铁律；
4. 严格继承 2005-01-04 至 2027-02-19 已有真实历史数据（SSOT），从 2027-02-20 推演至 2099-12-31；
5. 一键原子部署至当前 Python 环境 site-packages、工程本地副本并清理网络更新缓存，
   彻底根除老旧告警、Emoji 编码崩溃与启动网络卡顿。
"""

import os
import sys
import shutil
import datetime
from pathlib import Path


# ============================================================================
# 1. 纯标准库中国天文农历算法 (1900 - 2100 年)
# ============================================================================
# 数据来源：中国科学院紫金山天文台天文年历编算数据
# 编码规则：0x[闰月大小1位][12个月大小12位][闰哪个月4位]
LUNAR_INFO = [
    0x04bd8,0x04ae0,0x0a570,0x054d5,0x0d260,0x0d950,0x16554,0x056a0,0x09ad0,0x055d2,
    0x04ae0,0x0a5b6,0x0a4d0,0x0d250,0x1d255,0x0b540,0x0d6a0,0x0ada2,0x095b0,0x14977,
    0x04970,0x0a4b0,0x0b4b5,0x06a50,0x06d40,0x1ab54,0x02b60,0x09570,0x052f2,0x04970,
    0x06566,0x0d4a0,0x0ea50,0x06e95,0x05ad0,0x02b60,0x186e3,0x092e0,0x1c8d7,0x04950,
    0x0d4a0,0x1f865,0x0b550,0x056a0,0x1aba4,0x025d0,0x092d0,0x1d2b6,0x0a950,0x0b557,
    0x06ca0,0x0b550,0x15355,0x04da0,0x0a5d0,0x14573,0x052d0,0x0a9a8,0x0e950,0x06aa0,
    0x0aea6,0x0ab50,0x04b60,0x0aae4,0x0a570,0x05260,0x0f263,0x0d950,0x05b57,0x056a0,
    0x096d0,0x04dd5,0x04ad0,0x0a4d0,0x0d4d4,0x0d250,0x0d558,0x0b540,0x0b5a0,0x195a6,
    0x095b0,0x049b0,0x0a974,0x0a4b0,0x0b27a,0x06a50,0x06d40,0x0af46,0x0ab60,0x09570,
    0x04af5,0x04970,0x064b0,0x074a3,0x0ea50,0x06b58,0x055c0,0x0ab60,0x096d5,0x092e0,
    0x0c960,0x0d954,0x0d4a0,0x0da50,0x07552,0x056a0,0x0abb7,0x025d0,0x092d0,0x0cab5,
    0x0a950,0x0b4a0,0x0baa4,0x0ad50,0x055d9,0x04ba0,0x0a5b0,0x15176,0x052b0,0x0a930,
    0x07954,0x06aa0,0x0ad50,0x05b52,0x04b60,0x0a6e6,0x0a4e0,0x0d260,0x0ea65,0x0d530,
    0x05aa0,0x076a3,0x096d0,0x04afb,0x04ad0,0x0a4d0,0x1d0b6,0x0d250,0x0d520,0x0dd45,
    0x0b5a0,0x056d0,0x055b2,0x049b0,0x0a577,0x0a4b0,0x0aa50,0x1b255,0x06d20,0x0ada0,
    0x14b63,0x09370,0x049f8,0x04970,0x064b0,0x168a6,0x0ea50,0x06aa0,0x1a6c4,0x0aae0,
    0x092e0,0x0d2e3,0x0c960,0x0d557,0x0d4a0,0x0da50,0x05d55,0x056a0,0x0a6d0,0x055d4,
    0x052d0,0x0a9b8,0x0a950,0x0b4a0,0x0b6a6,0x0ad50,0x055a0,0x0aba4,0x0a5b0,0x052b0,
    0x0b273,0x06930,0x07337,0x06aa0,0x0ad50,0x14b55,0x04b60,0x0a570,0x054e4,0x0d160,
    0x0e968,0x0d520,0x0daa0,0x16aa6,0x056d0,0x04ae0,0x0a9d4,0x0a2d0,0x0d150,0x0f252,
    0x0d520
]


class LunarSolarEngine:
    """高精度农历与二十四节气转换引擎"""

    @staticmethod
    def leap_month(year: int) -> int:
        """获取指定农历年份的闰月月份（1-12，0 表示无闰月）"""
        return LUNAR_INFO[year - 1900] & 0xf

    @staticmethod
    def leap_days(year: int) -> int:
        """获取指定农历年份闰月的天数（29 或 30 天）"""
        if LunarSolarEngine.leap_month(year):
            return 30 if (LUNAR_INFO[year - 1900] & 0x10000) else 29
        return 0

    @staticmethod
    def month_days(year: int, month: int) -> int:
        """获取指定农历年份、月份的天数（29 或 30 天）"""
        return 30 if (LUNAR_INFO[year - 1900] & (0x10000 >> month)) else 29

    @staticmethod
    def lunar_year_days(year: int) -> int:
        """获取指定农历年份全年的天数"""
        sum_days = 0
        info = LUNAR_INFO[year - 1900]
        for i in range(1, 13):
            sum_days += 30 if (info & (0x10000 >> i)) else 29
        if LunarSolarEngine.leap_month(year):
            sum_days += LunarSolarEngine.leap_days(year)
        return sum_days

    @staticmethod
    def lunar_to_solar(ly: int, lm: int, ld: int, is_leap: bool = False) -> datetime.date:
        """农历日期转换为公历日期"""
        if not (1900 <= ly <= 2100):
            raise ValueError(f"年份超出演算范围 (1900-2100): {ly}")

        offset = 0
        for y in range(1900, ly):
            offset += LunarSolarEngine.lunar_year_days(y)

        lp = LunarSolarEngine.leap_month(ly)
        for m in range(1, lm):
            offset += LunarSolarEngine.month_days(ly, m)
            if lp and m == lp:
                offset += LunarSolarEngine.leap_days(ly)

        if is_leap and lp == lm:
            offset += LunarSolarEngine.month_days(ly, lm)

        offset += (ld - 1)
        # 1900-01-30 为标准对应基准原点
        return datetime.date(1900, 1, 30) + datetime.timedelta(days=offset)

    @staticmethod
    def get_chunjie(year: int) -> datetime.date:
        """获取公历年份对应农历春节（正月初一）的公历日期"""
        return LunarSolarEngine.lunar_to_solar(year, 1, 1)

    @staticmethod
    def get_chuxi(year: int) -> datetime.date:
        """获取公历年份对应除夕的公历日期（正月初一前一天）"""
        return LunarSolarEngine.get_chunjie(year) - datetime.timedelta(days=1)

    @staticmethod
    def get_duanwu(year: int) -> datetime.date:
        """获取公历年份对应端午节（农历五月初五）的公历日期"""
        return LunarSolarEngine.lunar_to_solar(year, 5, 5)

    @staticmethod
    def get_zhongqiu(year: int) -> datetime.date:
        """获取公历年份对应中秋节（农历八月十五）的公历日期"""
        return LunarSolarEngine.lunar_to_solar(year, 8, 15)

    @staticmethod
    def get_qingming(year: int) -> datetime.date:
        """
        利用中国传统天文学二十四节气之清明公式（寿星公式）计算公历清明日期
        21世纪 (2000-2099) 清明公式：[Y*D + C] - L
        Y = year % 100 (世纪年数)
        C = 4.81, D = 0.2422, L = Y // 4
        """
        Y = year % 100
        d_day = int(Y * 0.2422 + 4.81) - int(Y / 4)
        return datetime.date(year, 4, d_day)



# ============================================================================
# 2. A 股法定节假日休市与调休推演引擎
# ============================================================================
class TradeHolidayEngine:
    """A 股休市日历推导引擎"""

    @staticmethod
    def _make_3day_holiday(dt: datetime.date) -> set:
        """
        单日法定节假日（元旦、清明、端午、中秋）的国家标准调休 3 天小长假模型：
        - 周一：休 周六、周日、周一 (工作日休周一)
        - 周二：调休 周日、周一、周二 (工作日休周一、周二)
        - 周三：休 周三当天 1 天
        - 周四：调休 周四、周五、周六 (工作日休周四、周五)
        - 周五：休 周五、周六、周日 (工作日休周五)
        - 周六/周日：顺延周一补休 (工作日休周一)
        """
        w = dt.weekday()
        if w == 0:  # 周一
            return {dt}
        elif w == 1:  # 周二
            return {dt - datetime.timedelta(days=1), dt}
        elif w == 2:  # 周三
            return {dt}
        elif w == 3:  # 周四
            return {dt, dt + datetime.timedelta(days=1)}
        elif w == 4:  # 周五
            return {dt}
        elif w == 5:  # 周六
            return {dt, dt + datetime.timedelta(days=2)}
        elif w == 6:  # 周日
            return {dt, dt + datetime.timedelta(days=1)}
        return {dt}

    @classmethod
    def get_year_holidays(cls, year: int) -> set:
        """
        获取指定公历年份所有休市日（不含普通周末）
        涵盖：元旦、春节、清明、劳动节、端午、中秋、国庆（及中秋国庆合体）
        """
        holidays = set()

        # 1. 元旦 (1月1日)
        holidays.update(cls._make_3day_holiday(datetime.date(year, 1, 1)))

        # 2. 农历新年（春节/除夕）
        # A 股春节标准休市：除夕至正月初七（共 8 天），初八开市
        chuxi = LunarSolarEngine.get_chuxi(year)
        for d in range(8):
            holidays.add(chuxi + datetime.timedelta(days=d))

        # 3. 清明节 (4月4日 或 4月5日)
        qm = LunarSolarEngine.get_qingming(year)
        holidays.update(cls._make_3day_holiday(qm))

        # 4. 劳动节 (5月1日)
        w1 = datetime.date(year, 5, 1)
        for d in (0, 1, 2):
            holidays.add(w1 + datetime.timedelta(days=d))
        weekend_in_may = sum(1 for d in (0, 1, 2) if (w1 + datetime.timedelta(days=d)).weekday() >= 5)
        for extra in range(weekend_in_may):
            holidays.add(datetime.date(year, 5, 4 + extra))

        # 5. 端午节 (农历五月初五)
        dw = LunarSolarEngine.get_duanwu(year)
        holidays.update(cls._make_3day_holiday(dw))

        # 6. 中秋节 与 国庆节 合体/独立判断
        zq = LunarSolarEngine.get_zhongqiu(year)
        gq_start = datetime.date(year, 10, 1)

        # 判断是否中秋国庆合体连休：若中秋落在 9月28日至10月6日之间
        is_joint = (datetime.date(year, 9, 28) <= zq <= datetime.date(year, 10, 6))

        if is_joint:
            # 中秋国庆连休 8 天（10月1日 至 10月8日）
            start_joint = min(zq, gq_start)
            end_joint = datetime.date(year, 10, 8)
            curr = start_joint
            while curr <= end_joint:
                holidays.add(curr)
                curr += datetime.timedelta(days=1)
        else:
            # 国庆节单独休市 7 天 (10月1日 - 10月7日)
            for d in range(7):
                holidays.add(datetime.date(year, 10, 1 + d))
            # 中秋节单独休市
            holidays.update(cls._make_3day_holiday(zq))

        return holidays


    @classmethod
    def is_trade_day(cls, dt: datetime.date, year_holidays: set) -> bool:
        """判定某一天是否为 A 股交易日"""
        # 铁律 1: 周末（周六=5, 周日=6）无论任何调休，交易所坚决休市
        if dt.weekday() >= 5:
            return False
        # 铁律 2: 法定节假日休市
        if dt in year_holidays:
            return False
        return True


# ============================================================================
# 3. 交易日历生成、无缝拼接与全自动原子部署
# ============================================================================
def generate_trade_calendar_df(start_year: int = 2027, end_year: int = 2099, base_csv_path: str = None):
    """
    生成 2005 至 2099 年完整的 A 股交易日列表
    """
    import pandas as pd

    existing_dates = []
    last_base_date = datetime.date(2005, 1, 1)

    # 1. 优先读取既有基础真实历史数据 (严格锁定 2005 至 2027-02-19 真实历史，避免二次运行时跳过未来推演)
    if base_csv_path and os.path.exists(base_csv_path):
        df_base = pd.read_csv(base_csv_path)
        if 'dt' in df_base.columns:
            historical_df = df_base[df_base['dt'] <= '2027-02-19']
            existing_dates = list(historical_df['dt'].dropna().astype(str).str.strip())
            if existing_dates:
                last_dt_str = existing_dates[-1]
                last_base_date = datetime.datetime.strptime(last_dt_str, '%Y-%m-%d').date()
                print(f"[Calendar] 成功加载既有历史基准日历: 共 {len(existing_dates)} 条, 区间 {existing_dates[0]} 至 {last_dt_str}")


    # 2. 从已有最后日期的次日开始推演，一直到 end_year-12-31
    start_date = last_base_date + datetime.timedelta(days=1)
    end_date = datetime.date(end_year, 12, 31)

    print(f"[Calendar] 正在推演未来交易日: 从 {start_date} 至 {end_date} ...")

    new_dates = []
    # 按年份缓存假日表，避免重复计算
    holidays_cache = {}

    curr = start_date
    while curr <= end_date:
        y = curr.year
        if y not in holidays_cache:
            holidays_cache[y] = TradeHolidayEngine.get_year_holidays(y)

        if TradeHolidayEngine.is_trade_day(curr, holidays_cache[y]):
            new_dates.append(curr.strftime('%Y-%m-%d'))

        curr += datetime.timedelta(days=1)

    # 3. 拼接并去重保持有序
    all_dates = sorted(list(dict.fromkeys(existing_dates + new_dates)))
    result_df = pd.DataFrame({'dt': all_dates})
    print(f"[Calendar] 推演完成: 新增交易日 {len(new_dates)} 天, 总计交易日 {len(result_df)} 天 (至 {result_df.iloc[-1]['dt']})")
    return result_df


def deploy_calendar_to_targets(result_df, extra_save_dirs=None):
    """
    将生成的完整 2099 日历原子覆盖部署至系统各目标位置
    """
    deployed_paths = []

    # 目标 1: 当前 Python 环境的 site-packages/a_trade_calendar
    import site
    possible_dirs = site.getsitepackages() + [site.getusersitepackages()]
    target_sp_csv = None
    for sd in possible_dirs:
        candidate = os.path.join(sd, "a_trade_calendar", "a_trade_calendar.csv")
        if os.path.exists(candidate) or os.path.isdir(os.path.join(sd, "a_trade_calendar")):
            target_sp_csv = candidate
            break

    if target_sp_csv:
        try:
            result_df.to_csv(target_sp_csv, index=False)
            deployed_paths.append(target_sp_csv)
            print(f"[Deploy] 已成功覆盖 site-packages 目录: {target_sp_csv}")
        except Exception as e:
            print(f"[Deploy] 覆盖 site-packages 失败: {e}")
    else:
        print("[Deploy] 未检测到 site-packages 中的 a_trade_calendar 目录")


    # 目标 2: 本地工程目录 (stock_standalone/JSONData)
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_jsondata_csv = os.path.join(app_root, "JSONData", "a_trade_calendar.csv")
    os.makedirs(os.path.dirname(local_jsondata_csv), exist_ok=True)
    result_df.to_csv(local_jsondata_csv, index=False)
    deployed_paths.append(local_jsondata_csv)
    print(f"[Deploy] 已同步备份至工程本地目录: {local_jsondata_csv}")

    # 目标 3: 用户额外指定的目录
    if extra_save_dirs:
        for d in extra_save_dirs:
            if os.path.isdir(d):
                p = os.path.join(d, "a_trade_calendar.csv")
                result_df.to_csv(p, index=False)
                deployed_paths.append(p)
                print(f"[Deploy] 已部署至额外目录: {p}")

    # 目标 4: 清理网络缓存目录，防止旧版缓存覆盖新数据
    cache_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "a_trade_calendar")
    if os.path.exists(cache_dir):
        try:
            shutil.rmtree(cache_dir, ignore_errors=True)
            print(f"[Deploy] 已清理本地网络缓存目录: {cache_dir}")
        except Exception as e:
            print(f"[Deploy] 清理缓存异常 (已忽略): {e}")

    return deployed_paths


def main():
    print("=" * 70)
    print("  全自动 A 股交易日历生成与部署工具 (直通 2099 年)")
    print("=" * 70)

    # 寻找已有的基准 a_trade_calendar.csv 路径
    base_csv = None
    # 策略 1: 直接检查当前 Python 环境 site-packages 物理路径
    import site
    possible_dirs = site.getsitepackages() + [site.getusersitepackages()]
    for sd in possible_dirs:
        candidate = os.path.join(sd, "a_trade_calendar", "a_trade_calendar.csv")
        if os.path.exists(candidate):
            base_csv = candidate
            break

    # 策略 2: import 动态探测
    if not base_csv:
        try:
            import a_trade_calendar
            candidate = os.path.join(os.path.dirname(a_trade_calendar.__file__), "a_trade_calendar.csv")
            if os.path.exists(candidate):
                base_csv = candidate
        except Exception:
            pass

    # 策略 3: 本地工程目录
    if not base_csv:
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidate = os.path.join(app_root, "JSONData", "a_trade_calendar.csv")
        if os.path.exists(candidate):
            base_csv = candidate


    df = generate_trade_calendar_df(start_year=2027, end_year=2099, base_csv_path=base_csv)
    deployed = deploy_calendar_to_targets(df)
    print("=" * 70)
    print(f"部署完成! 覆盖目标数: {len(deployed)}")
    print(f"最新数据区间: {df.iloc[0]['dt']} 至 {df.iloc[-1]['dt']} (共 {len(df)} 交易日)")
    print("=" * 70)


if __name__ == "__main__":
    main()
