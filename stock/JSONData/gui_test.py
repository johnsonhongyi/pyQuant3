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

'''
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
'''


# from multiprocessing.pool import ThreadPool # 线程池：使用方法和Pool一样
from multiprocessing.dummy import Pool as ThreadPool # 两种线程池都可以
from multiprocessing import Pool # 创建进程池
import numpy as np
import time
from tqdm import tqdm
# Python官网说明：
# https://docs.python.org/zh-cn/3/library/multiprocessing.html#using-a-pool-of-workers
 
# 几点总结：
# 1. 进程必须要在__main__函数中才能运行，线程不用
# 2. 正常使用直接map，想看速度imap;
# 3. map结果直接用，imap结果不好拿出来，写进文件就没事了
 
# def fun1(x):
#     time.sleep(0.005)  # 假设函数的运行时间为0.005s
#     return x
# '''
# if __name__ == '__main__':
#     a = np.arange(100)
#     # res = [fun1(i) for i in a]
 
#     ''' 多进程 '''
#     # 法一
#     with Pool(12) as p:
#         res2 = p.map(fun1,a) 
#     # 法二
#     res = Pool(12).map(fun1,a)
#     print(res) # [0,1,2...99]
#     # 法三
#     res = Pool(12).imap(fun1,a) # 顺序不变
#     for i in tqdm(res):
#         pass
#     # 法四
#     res = Pool(12).imap_unordered(fun1,a) # 顺序打乱
 
#     ''' 多线程 '''
#     with ThreadPool(12) as p:
#         res = p.map(fun1,a)
#     res = ThreadPool(12).map(fun1,a)
#     res = ThreadPool(12).imap(fun1,a)
#     for _ in tqdm(res):
#         pass
#     res = ThreadPool(12).imap_unordered(fun1,a)
# '''



# from tqdm import tqdm
# import multiprocessing

# def worker(num):
#     for i in tqdm(range(1000), desc=f'Worker {num}'):
#         time.sleep(0.002)

# if __name__ == '__main__':
#     with multiprocessing.Pool(4) as p:
#         p.map(worker, [1, 2, 3, 4])


"""
Run `pip install tqdm` before running the script.

The function `foo` is going to be executed 100 times across
`MAX_WORKERS=5` processes. In a single pass, each process will
get an iterable of size `CHUNK_SIZE=5`. So 5 processes each consuming
5 elements of an iterable will require (100 / (5*5)) 4 passes to finish
consuming the entire iterable of 100 elements.

Tqdm progress bar will be updated after every `MAX_WORKERS*CHUNK_SIZE` iterations.
"""
# src.py


# from __future__ import annotations

import multiprocessing as mp

from tqdm import tqdm
import time

import random
from dataclasses import dataclass

MAX_WORKERS = 5
CHUNK_SIZE = 5


@dataclass
class StartEnd:
    start: int
    end: int


def foo(start_end: StartEnd) -> int:
    time.sleep(0.2)
    return random.randint(start_end.start, start_end.end)


def main() -> None:
    inputs = [
        StartEnd(start, end)
        for start, end in zip(
            range(0, 100),
            range(100, 200),
        )
    ]

    with mp.Pool(processes=MAX_WORKERS) as pool:
        results = tqdm(
            pool.imap_unordered(foo, inputs, chunksize=CHUNK_SIZE),
            total=len(inputs),
        )  # 'total' is redundant here but can be useful
        # when the size of the iterable is unobvious

        for result in results:
            print(result)


from multiprocessing import Pool
import time
from tqdm import *

def imap_unordered_bar(func, args, n_processes = 2):
    p = Pool(n_processes)
    res_list = []
    with tqdm(total = len(args)) as pbar:
        for i, res in tqdm(enumerate(p.imap_unordered(func, args))):
            pbar.update()
            res_list.append(res)
    pbar.close()
    p.close()
    p.join()
    return res_list

def _foo(my_number):
    square = my_number * my_number
    time.sleep(0.02)
    return square 

# if __name__ == '__main__':
#     result = imap_unordered_bar(_foo, range(500))

from multiprocessing import Pool
from functools import partial
from tqdm import tqdm


def imap_tqdm(function, iterable, processes, chunksize=1, desc=None, disable=False, **kwargs):
    """
    Run a function in parallel with a tqdm progress bar and an arbitrary number of arguments.
    Results are always ordered and the performance should be the same as of Pool.map.
    :param function: The function that should be parallelized.
    :param iterable: The iterable passed to the function.
    :param processes: The number of processes used for the parallelization.
    :param chunksize: The iterable is based on the chunk size chopped into chunks and submitted to the process pool as separate tasks.
    :param desc: The description displayed by tqdm in the progress bar.
    :param disable: Disables the tqdm progress bar.
    :param kwargs: Any additional arguments that should be passed to the function.
    """
    if kwargs:
        function_wrapper = partial(_wrapper, function=function, **kwargs)
    else:
        function_wrapper = partial(_wrapper, function=function)

    results = [None] * len(iterable)
    with Pool(processes=processes) as p:
        with tqdm(desc=desc, total=len(iterable), disable=disable) as pbar:
            for i, result in p.imap_unordered(function_wrapper, enumerate(iterable), chunksize=chunksize):
                results[i] = result
                pbar.update()
    return results


def _wrapper(enum_iterable, function, **kwargs):
    i = enum_iterable[0]
    result = function(enum_iterable[1], **kwargs)
    return i, result


if __name__ == '__main__':
    result = imap_tqdm(_foo, range(500),processes=6)