import re

def parse_variable(file_path, var_name):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 匹配变量名块，如 [054] "Setup" 到下一个 [ 或者结束
    # 改进正则表达式以适应换行和缩进的轻微变化
    pattern = r'\[[0-9A-F]+\]\s+"' + re.escape(var_name) + r'"\s*\n\s*GUID:.*?\n\s*Attributes:.*?\n\s*DataSize:\s*(0x[0-9A-F]+|[0-9]+)\s*\n\s*Data:\s*\n(.*?)(?=\n\s*\[|\Z)'
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if not match:
        # 如果第一次没匹配上，尝试一种更宽泛的匹配
        pattern_fallback = r'\[[0-9A-F]+\]\s+"' + re.escape(var_name) + r'"\s*\n.*?DataSize:\s*(0x[0-9A-F]+|[0-9]+)\s*\n\s*Data:\s*\n(.*?)(?=\n\s*\[|\Z)'
        match = re.search(pattern_fallback, content, re.DOTALL | re.IGNORECASE)
        
    if not match:
        print(f"Variable {var_name} not found.")
        return None
    
    datasize_str = match.group(1)
    if datasize_str.lower().startswith('0x'):
        datasize = int(datasize_str, 16)
    else:
        datasize = int(datasize_str)
        
    data_lines = match.group(2)
    
    # 解析 Hex 字节
    bytes_list = []
    for line in data_lines.split('\n'):
        parts = line.strip().split(':')
        if len(parts) < 2:
            continue
        hex_part = parts[1].strip()
        hex_bytes = hex_part.split()
        for b in hex_bytes:
            if len(b) == 2: # 确保是合法的 hex 字节
                try:
                    bytes_list.append(int(b, 16))
                except ValueError:
                    break
    
    print(f"Parsed {var_name}: datasize={datasize}, parsed_size={len(bytes_list)}")
    return bytes_list

# 执行分析
file_path = r'E:\BackupD\Document\Downloads\Triton500\UEFITool\triton500Bios\fpt-all\Johnson2008-Triton500-unlocked-Bios\var-2933-19-20-20-43cr1-io50-sa0-dptf-OK.txt'

setup_bytes = parse_variable(file_path, 'Setup')
pch_bytes = parse_variable(file_path, 'PchSetup')

if setup_bytes:
    # 打印特定偏移量
    try:
        print(f"Setup 0x11D (USB Wake from S4 Support): {setup_bytes[0x11D]:02X} (offset {hex(0x11D)})")
        print(f"Setup 0x104 (Wake on USB while lid closed): {setup_bytes[0x104]:02X} (offset {hex(0x104)})")
        print(f"Setup 0x103 (Lid Open Resume): {setup_bytes[0x103]:02X}")
    except IndexError as e:
        print(f"Error accessing Setup offsets: {e}")

if pch_bytes:
    # PchSetup 0xE, 0xF, 0x4
    try:
        print(f"PchSetup 0x0E (Wake on WLAN and BT Enable): {pch_bytes[0x0E]:02X}")
        print(f"PchSetup 0x0F (DeepSx Wake on WLAN and BT Enable): {pch_bytes[0x0F]:02X}")
        print(f"PchSetup 0x04 (DeepSx Power Policies): {pch_bytes[0x04]:02X}")
    except IndexError as e:
        print(f"Error accessing PchSetup offsets: {e}")
