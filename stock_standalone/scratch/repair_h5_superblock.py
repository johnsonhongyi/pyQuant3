# -*- coding: utf-8 -*-
"""
HDF5 superblock 二进制修复：
- HDF5 superblock version 0 在偏移 8 存储 stored_eof (8 bytes, little-endian)
- 将 stored_eof 修正为实际文件大小，让 HDF5 可以重新打开
"""
import struct
import os
import shutil

BAK  = r'g:\sina_MultiIndex_data.h5.corrupt_1783314017.bak'
COPY = r'g:\sina_MultiIndex_data_bak_repair.h5'

# 复制一份用于修复
shutil.copy2(BAK, COPY)
print(f"已复制到: {COPY}")

actual_eof = os.path.getsize(COPY)
print(f"实际文件大小 (actual eof): {actual_eof} bytes")

# HDF5 superblock v0 signature + version info:
# Offset 0: 8 bytes  - HDF5 signature '\x89HDF\r\n\x1a\n'
# Offset 8: 1 byte   - superblock version
# Offset 9: 1 byte   - free-space storage version  
# Offset 10: 1 byte  - root group symbol table version
# Offset 11: 1 byte  - reserved
# Offset 12: 1 byte  - shared header message version
# Offset 13: 1 byte  - size of offsets
# Offset 14: 1 byte  - size of lengths
# ...
# For superblock v0 with 8-byte offsets:
# Offset of end-of-file address = 8 + (superblock content based on offset_size)
# 
# Actual layout for v0, offset_size=8:
# 0-7:   signature
# 8:     sb_version
# 9:     free_space_version
# 10:    root_group_version
# 11:    reserved
# 12:    shared_hdr_version
# 13:    size_of_offsets (=8)
# 14:    size_of_lengths (=8)
# 15:    reserved
# 16-17: group_leaf_node_k, group_internal_node_k
# 18-21: file_consistency_flags
# 22-29: base_address (=0)
# 30-37: free_space_address (=HADDR_UNDEF)
# 38-45: end_of_file_address  <--- 这里存 stored_eof
# 46-53: driver_info_address (=HADDR_UNDEF)
# 54-61: root_group_address

EOF_OFFSET = 38   # HDF5 superblock v0, 8-byte offsets

with open(COPY, 'r+b') as f:
    # 验证签名
    sig = f.read(8)
    expected_sig = b'\x89HDF\r\n\x1a\n'
    print(f"HDF5 签名: {sig} {'OK' if sig == expected_sig else 'INVALID!'}")
    
    # 读取 size_of_offsets
    f.seek(13)
    offset_size = struct.unpack('B', f.read(1))[0]
    print(f"size_of_offsets: {offset_size}")
    
    # 调整 EOF_OFFSET 根据 offset_size
    if offset_size == 8:
        eof_offset = 38
    elif offset_size == 4:
        eof_offset = 26
    else:
        eof_offset = 38
    
    # 读当前 stored_eof
    f.seek(eof_offset)
    stored_eof_bytes = f.read(offset_size)
    stored_eof = struct.unpack('<Q', stored_eof_bytes)[0]
    print(f"stored_eof (offset={eof_offset}): {stored_eof} bytes")
    print(f"actual_eof:                        {actual_eof} bytes")
    print(f"差值: {stored_eof - actual_eof} bytes")
    
    if stored_eof == actual_eof:
        print("文件未被截断，无需修复")
    else:
        # 将 stored_eof 修正为 actual_eof
        f.seek(eof_offset)
        f.write(struct.pack('<Q', actual_eof))
        print(f"已将 stored_eof 修正为: {actual_eof}")

# 验证修复结果
print("\n验证修复后的文件...")
try:
    import pandas as pd
    with pd.HDFStore(COPY, mode='r') as store:
        print(f"  成功打开! Keys: {store.keys()}")
        for key in store.keys():
            nrows = store.get_storer(key).nrows
            print(f"  {key}: {nrows} 行")
            try:
                sample = store.select(key, columns=[])
                times = pd.to_datetime(sample.index.get_level_values('ticktime'))
                print(f"    日期范围: {times.min().date()} ~ {times.max().date()}")
                print(f"    codes: {sample.index.get_level_values('code').unique().__len__()} 个")
            except Exception as e:
                print(f"    统计失败: {e}")
    print("\n修复成功! 可以继续合并操作。")
except Exception as e:
    print(f"  修复后仍无法打开: {e}")
    print("  superblock 损坏超出二进制修复范围，需要从其他途径恢复。")
