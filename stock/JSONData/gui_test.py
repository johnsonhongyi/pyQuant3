from tkinter import *
# from pandastable import Table, TableModel
# import sys
# sys.path.append('../')
import tdx_data_Day as tdd

code = '999999'
df = tdd.get_tdx_Exp_day_to_df(code, type='f', start=None, end=None, dl=30, newdays=None)

# class TestApp(Frame):
#     """Basic test frame for the table"""
#     def __init__(self, parent=None):
#         self.parent = parent
#         Frame.__init__(self)
#         self.main = self.master
#         self.main.geometry('800x600+200+100')
#         self.main.title('Table app')
#         f = Frame(self.main)
#         f.pack(fill=BOTH,expand=1)
#         # df = TableModel.getSampleData()
#         self.table = pt = Table(f, dataframe=df,
#                                 showtoolbar=True, showstatusbar=True)
#         pt.show()
#         return

# app = TestApp()
# app.mainloop()

resample = 'd'
code='000002'
dl=60

def tdx_profile_test():
    # time_s=time.time()
    # for i in range(20):
    #     df = tdd.get_tdx_exp_low_or_high_power(code, dl=dl, end=None, ptype='low', power=False, resample=resample)
    df = tdd.get_tdx_exp_low_or_high_power(code, dl=dl, end=None, ptype='low', power=False, resample=resample)
        # print("time:%s"%( round((time.time()-time_s),2) ))
    # print("done")

# https://vimsky.com/examples/detail/python-method-profile.run.html

profile_name = './profile.out'

import os
if not os.path.exists(profile_name):
    import profile
    # # profile.run('tdx_profile_test()',options.profile)
    profile.run('for i in range(20): tdx_profile_test()',profile_name)
else:
    print("exists profile_name:%s"%(profile_name))

import pstats
stats = pstats.Stats(profile_name)
stats.strip_dirs().sort_stats('time', 'calls').print_stats(30)
# stats.strip_dirs().sort_stats('time', 'cum').print_stats(30)
# stats.strip_dirs().sort_stats('cum', 'time').print_stats(30) 
# df = tdd.get_tdx_exp_low_or_high_power(code, dl=dl, end=None, ptype='low', power=False, resample=resample)
# python -m cProfile-o cpf_out.txt mytest.py

# import pstats
# p=pstats.Stats('./cpf_out.txt')
# p.print_stats()
# #根据调用次数排序
# p.sort_stats('calls').print_stats()
# #根据调用总时间排序
# p.sort_stats('cumulative').print_stats()