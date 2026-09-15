# -*- coding: utf-8 -*-
import os, sys, time, tempfile, pytest, pandas as pd
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
from JSONData import tdx_hdf5_api as h5a

@pytest.fixture
def temp_test_h5():
    fd, path = tempfile.mkstemp(suffix='.h5')
    os.close(fd)
    df = pd.DataFrame({'code': ['600000', '000001'], 'close': [10.5, 12.3], 'volume': [1000, 2000]}).set_index('code')
    with pd.HDFStore(path, mode='w') as store:
        store.put('test_table', df, format='table')
    lock_file = path + '.lock'
    yield path
    for f in [path, lock_file, path + '_tmp']:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass

def test_read_mode_does_not_release_lock(temp_test_h5):
    lock_file = temp_test_h5 + '.lock'
    
    # 1. 读者打开文件 (此时无锁)
    reader = h5a.SafeHDFStore(temp_test_h5, mode='r')
    assert '/test_table' in reader.keys()
    
    # 2. 模拟外部写者创建了排他锁
    with open(lock_file, 'w') as f:
        f.write(f'{os.getpid()}|{time.time()}')
    assert os.path.exists(lock_file)
    
    # 3. 读者退出并调用 close()，验证读者绝对不会误删写者的排他锁！
    reader.close()
    assert os.path.exists(lock_file), '读者 close() 绝不能释放写者持有的 .lock！'
    
    # 4. 读者的 with 块退出，验证同样不删写者的排他锁！
    # 临时删除锁以便读者以 with 打开
    os.remove(lock_file)
    with h5a.SafeHDFStore(temp_test_h5, mode='r') as r:
        # 在 with 块内部写入写者锁
        with open(lock_file, 'w') as f:
            f.write(f'{os.getpid()}|{time.time()}')
    # 退出 with 块后，锁依然必须存在！
    assert os.path.exists(lock_file), '读者退出 with 块绝不能释放写者的 .lock！'
    os.remove(lock_file)

def test_read_mode_exit_instant_no_sleep(temp_test_h5):
    t0 = time.time()
    with h5a.SafeHDFStore(temp_test_h5, mode='r') as store:
        _ = store.keys()
    elapsed = time.time() - t0
    assert elapsed < 0.08, f'too slow: {elapsed:.3f}s'

def test_reentrant_lock_same_process(temp_test_h5):
    lock_file = temp_test_h5 + '.lock'
    s1 = h5a.SafeHDFStore(temp_test_h5, mode='a')
    assert os.path.exists(lock_file)
    with open(lock_file, 'r') as f:
        content1 = f.read().strip()
    time.sleep(0.05)
    s2 = h5a.SafeHDFStore(temp_test_h5, mode='a')
    assert os.path.exists(lock_file)
    with open(lock_file, 'r') as f:
        content2 = f.read().strip()
    ts1 = float(content1.split('|')[1])
    ts2 = float(content2.split('|')[1])
    assert ts2 >= ts1
    s2.close(release_lock=False)
    s1.close(release_lock=True)
    assert not os.path.exists(lock_file)

def test_wait_for_lock_dead_pid_auto_cleanup(temp_test_h5):
    lock_file = temp_test_h5 + '.lock'
    dead_pid = 99999999
    with open(lock_file, 'w') as f:
        f.write(f'{dead_pid}|{time.time()}')
    assert os.path.exists(lock_file)
    t0 = time.time()
    with h5a.SafeHDFStore(temp_test_h5, mode='r') as store:
        _ = store.keys()
    elapsed = time.time() - t0
    assert elapsed < 1.0, f'too slow: {elapsed:.2f}s'
    assert not os.path.exists(lock_file)

def test_release_lock_winerror_retry(temp_test_h5):
    lock_file = temp_test_h5 + '.lock'
    s = h5a.SafeHDFStore(temp_test_h5, mode='a')
    assert os.path.exists(lock_file)
    s._release_lock()
    assert not os.path.exists(lock_file)

def test_write_hdf_db_replace_lifecycle(temp_test_h5):
    df_new = pd.DataFrame({'code': ['600000', '000001', '300750'], 'close': [11.0, 12.5, 200.0], 'volume': [1500, 2500, 3500]}).set_index('code')
    res = h5a.write_hdf_db(temp_test_h5, df_new, table='test_table', append=False, rewrite=True)
    assert res is not False
    lock_file = temp_test_h5 + '.lock'
    assert not os.path.exists(lock_file)
    with h5a.SafeHDFStore(temp_test_h5, mode='r') as store:
        df_read = store['test_table']
        assert '300750' in df_read.index
        assert df_read.loc['300750', 'close'] == 200.0

def test_parse_lock_info_empty_file_not_stale(temp_test_h5):
    """测试刚创建的空锁文件（<3秒）绝不会被判定为僵尸锁，绝不溢出17.89亿秒"""
    store = h5a.SafeHDFStore(temp_test_h5, mode='r')
    lock_file = temp_test_h5 + '.lock'
    # 模拟进程刚刚 open('x') 产生 0 字节文件
    with open(lock_file, 'w') as f:
        pass
    assert os.path.getsize(lock_file) == 0

    info = store._parse_lock_info()
    store.close()

    assert info['exists'] is True
    assert info['is_busy'] is True
    assert info['is_stale'] is False
    assert info['elapsed'] < 2.0  # 绝不能是 17.89 亿秒！
    # 验证文件仍然安全留存，没有被瞬间撕毁
    assert os.path.exists(lock_file)
    os.remove(lock_file)

def test_release_lock_never_deletes_other_alive_pid(temp_test_h5):
    """测试当前进程绝不能越权释放其他存活进程持有的锁"""
    store = h5a.SafeHDFStore(temp_test_h5, mode='r')
    lock_file = temp_test_h5 + '.lock'
    # 使用当前 Python 进程的真实父进程 PID（保证存活）
    import psutil
    parent_pid = psutil.Process().ppid()
    with open(lock_file, 'w') as f:
        f.write(f'{parent_pid}|{time.time()}\n')
    assert os.path.exists(lock_file)

    # 当前进程尝试释放该锁，由于锁持有者是 parent_pid 而非当前进程，绝不释放！
    store._release_lock()
    store.close()

    # 验证属于父进程的锁绝对没有被误删！
    assert os.path.exists(lock_file)
    os.remove(lock_file)

def test_init_exception_cleans_exclusive_lock(temp_test_h5):
    """测试写模式在 __init__ 抛出异常时，排他锁 100% 被清理释放，不留下孤儿锁"""
    lock_file = temp_test_h5 + '.lock'
    # 传入无效参数促使底层抛出异常
    with pytest.raises(Exception):
        _ = h5a.SafeHDFStore(temp_test_h5, mode='a', complevel='INVALID_COMPLEVEL')
    
    # 验证异常抛出后，排他锁已被自动清理，不留残余！
    assert not os.path.exists(lock_file)

