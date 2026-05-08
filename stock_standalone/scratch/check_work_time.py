import sys
import os
sys.path.append(os.getcwd())

from JohnsonUtil import commonTips as cct
import datetime

print("当前系统实际时间:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("cct.get_trade_date_status() 状态:", cct.get_trade_date_status())
print("cct.get_last_trade_date() 结果:", cct.get_last_trade_date())
print("cct.get_work_time_duration() 结果:", cct.get_work_time_duration())
