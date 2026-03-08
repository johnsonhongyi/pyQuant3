# -*- coding: utf-8 -*-
"""
DataHubService 单元测试与性能验证
"""

import os
import sys
import time
import unittest
import numpy as np
import pandas as pd
import multiprocessing as mp

# 确保能引入同目录的包
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from data_hub_service import DataHubService

# 测试数据生成
def generate_mock_df(size=5000):
    """生成模拟的 A股 全市场预处理数据"""
    codes = [f"{str(i).zfill(6)}" for i in range(1, size+1)]
    return pd.DataFrame({
        'code': codes,
        'name': [f"Stock_{c}" for c in codes],
        'price': np.random.uniform(5, 100, size=size),
        'percent': np.random.uniform(-10, 10, size=size),
        'volume': np.random.uniform(1000, 1000000, size=size),
        'structure_base_score': np.random.uniform(50, 100, size=size),
        'high4': np.random.uniform(5, 100, size=size),
        'ma5': np.random.uniform(5, 100, size=size),
        'lastl': np.random.uniform(5, 100, size=size),
    }).set_index('code')


# 子进程任务：持续高频读取测试
def consumer_task(worker_id, test_duration, base_dir, out_queue):
    import logging
    logging.basicConfig(level=logging.ERROR)
    
    hub = DataHubService.get_instance(base_dir=base_dir)
    reads_count = 0
    errors = 0
    start_time = time.time()
    
    while time.time() - start_time < test_duration:
        try:
            # 强制每次绕过 cache 读取硬盘（测试高并发文件读取安全性）
            df = hub.get_df_all(force_reload=True, max_wait_sec=1.0)
            if df is not None and not df.empty:
                reads_count += 1
            else:
                errors += 1
                
            tick_df = hub.get_tick_cache(force_reload=True, max_wait_sec=1.0)
            if tick_df is not None and not tick_df.empty:
                reads_count += 1
        except Exception as e:
            errors += 1
        
        # 极高频休眠，创造数据竞争条件
        time.sleep(0.01)
        
    out_queue.put({'worker_id': worker_id, 'reads': reads_count, 'errors': errors})


class TestDataHubService(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.test_dir = os.path.join(os.path.dirname(__file__), "test_data_hub")
        cls.hub = DataHubService.get_instance(base_dir=cls.test_dir)
        cls.mock_df = generate_mock_df(5000)
    
    def test_01_publish_and_get(self):
        """测试基础的数据发布与获取"""
        # Publish
        success = self.hub.publish_df_all(self.mock_df)
        self.assertTrue(success, "发布返回 True")
        self.assertTrue(os.path.exists(self.hub.df_all_path), "HDF5文件应当创建")
        
        # Get
        df_loaded = self.hub.get_df_all(force_reload=True)
        self.assertIsNotNone(df_loaded, "加载数据不应为空")
        self.assertEqual(len(df_loaded), 5000, "加载数据行数匹配")
        self.assertIn('structure_base_score', df_loaded.columns, "核心列存在")

    def test_02_atomic_multiprocessing(self):
        """测试多进程极高频的并发读取时，服务端的反复写（覆盖）是否安全"""
        duration = 5.0 # 测试5秒
        workers = 4
        out_queue = mp.Queue()
        processes = []
        
        # 启动多个消费者疯狂读取
        for i in range(workers):
            p = mp.Process(target=consumer_task, args=(i, duration, self.test_dir, out_queue))
            processes.append(p)
            p.start()
            
        # 主进程疯狂覆盖写入新的df_all (模拟行情更新/重新发布)
        writes_count = 0
        write_errors = 0
        write_start = time.time()
        
        while time.time() - write_start < duration:
            # 变更一些内容模拟更新
            df_new = generate_mock_df(100+writes_count)
            success_a = self.hub.publish_df_all(df_new)
            
            tick_df_new = pd.DataFrame({'code': [f"{i:06d}" for i in range(100+writes_count)], 'trade': np.random.rand(100+writes_count)})
            success_b = self.hub.publish_tick_cache(tick_df_new)
            
            if success_a and success_b:
                writes_count += 1
            else:
                write_errors += 1
            time.sleep(0.2) # 1秒写5次左右
            
        for p in processes:
            p.join()
            
        total_reads = 0
        total_read_errors = 0
        
        while not out_queue.empty():
            res = out_queue.get()
            total_reads += res['reads']
            total_read_errors += res['errors']
            
        print(f"\n[性能测试] 并发测试结果:")
        print(f"主进程写入成功次数: {writes_count}, 写冲突/失败: {write_errors}")
        print(f"[{workers}个子进程] 读盘成功次数: {total_reads}, 读冲突/失败: {total_read_errors}")
        
        self.assertGreater(writes_count, 0, "主进程至少应有1次写入成功")
        self.assertGreater(total_reads, 0, "子进程至少应有1次读取成功")
        self.assertEqual(total_read_errors, 0, "Windows的原子替换与重试机制下，不应抛出完全失败的并发冲突")

    def test_03_cache_performance(self):
        """测试内存级缓存是否有大幅提速"""
        iterations = 100
        
        # 强制读盘
        start = time.time()
        for _ in range(iterations):
            self.hub.get_df_all(force_reload=True)
        disk_time = time.time() - start
        
        # 带缓存读取
        start = time.time()
        for _ in range(iterations):
            self.hub.get_df_all(force_reload=False)
        cache_time = time.time() - start
        
        print(f"\n[性能测试] 读取 {iterations} 次 5000行大表:")
        print(f"强制冷读盘(force_reload=True): {disk_time:.4f} 秒, 平均：{(disk_time/iterations)*1000:.2f} 毫秒/次")
        print(f"单例热缓存(force_reload=False): {cache_time:.4f} 秒, 平均：{(cache_time/iterations)*1000:.2f} 毫秒/次")
        
        self.assertLess(cache_time, disk_time, "带有MTime缓存的读取应显著快于盲目读盘")


if __name__ == '__main__':
    unittest.main()
