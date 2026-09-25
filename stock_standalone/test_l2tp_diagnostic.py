import subprocess
import socket
import ssl
import time
import sys
import re
import atexit

sys.stdout.reconfigure(encoding='utf-8')

def disconnect_vpn():
    """Ask whether to keep the VPN briefly; timeout defaults to disconnect."""
    try:
        import msvcrt

        deadline = time.monotonic() + 10
        print("\n测试结束。是否断开 VPN？10 秒内按 N 保持连接；按其他键或超时则断开。")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            print(f"\r默认断开，剩余 {int(remaining) + 1} 秒... ", end="", flush=True)
            if msvcrt.kbhit():
                if msvcrt.getwch().lower() == "n":
                    print("\n已按 N 保留 VPN 连接。")
                    return
                break
            time.sleep(min(0.1, remaining))
    except (ImportError, OSError):
        pass

    print("\n正在断开测试用 VPN 连接...", flush=True)
    subprocess.run(
        ["rasdial", "gmq.x3322.net", "/DISCONNECT"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

atexit.register(disconnect_vpn)

def get_source_ip(target, port):
    """Return the source address Windows routes to target (UDP connect sends no data)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((target, port))
        return probe.getsockname()[0]
    finally:
        probe.close()

print("=" * 65)
print("     L2TP 纯默认拨号网络与服务端口连通性诊断 (零手动路由)")
print("=" * 65)

# 1. 确保断开并重新以纯默认设置拨号
print("\n[1] 正在以纯默认设置重新拨号 L2TP VPN (gmq.x3322.net)...")
subprocess.run(["rasdial", "gmq.x3322.net", "/DISCONNECT"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(1)

dial_res = subprocess.run(["rasdial", "gmq.x3322.net", "SIP", "Sip@GMQ"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
dial_out = dial_res.stdout.decode('gbk', errors='ignore')
print("  -> 拨号状态码:", dial_res.returncode)
if dial_res.returncode != 0:
    print("  [ERROR] L2TP 拨号失败:", dial_out.strip())
    sys.exit(1)
else:
    print("  [OK] L2TP 纯默认拨号成功！")

time.sleep(2)

# 2. 获取 VPN 分配的 IP 与自动下发的默认路由
print("\n[2] 查看拨号自动下发的 IP 地址与默认路由 (未做任何手动修改)...")
r_ip = subprocess.run(["powershell", "-Command", 'Get-NetIPAddress | Where-Object { $_.InterfaceAlias -eq "gmq.x3322.net" } | Select-Object IPAddress, InterfaceIndex, InterfaceAlias'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print("  -> VPN 接口地址:\n" + r_ip.stdout.decode('gbk', errors='ignore').strip())

r_rt = subprocess.run(["powershell", "-Command", 'Get-NetRoute -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -eq "gmq.x3322.net" -and $_.DestinationPrefix -notin @("224.0.0.0/4", "255.255.255.255/32") } | Select-Object DestinationPrefix, NextHop, InterfaceAlias, InterfaceIndex, RouteMetric'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print("\n  -> VPN 接口自动下发的路由表:\n" + r_rt.stdout.decode('gbk', errors='ignore').strip())
print("  -> 仅列出 gmq.x3322.net VPN 接口的单播路由；0.0.0.0/0 表示该 VPN 下发了默认路由。")

# 3. 测试 10.10.11.1 (VPN 服务端网关)
print("\n[3] 测试 VPN 服务端网关 10.10.11.1 连通性...")
p_gw = subprocess.run(["ping", "-n", "3", "-w", "1000", "10.10.11.1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
for l in p_gw.stdout.decode('gbk', errors='ignore').splitlines():
    if any(k in l for k in ["来自", "Reply from", "TTL=", "超时", "Timed out", "100%"]):
        print("  ", l.strip())

# 4. 测试 192.168.10.1 (内网爱快网关) 网络与 80 端口
print("\n[4] 测试内网网关 192.168.10.1 连通性与端口...")
p_lan = subprocess.run(["ping", "-n", "2", "-w", "1000", "192.168.10.1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
for l in p_lan.stdout.decode('gbk', errors='ignore').splitlines():
    if any(k in l for k in ["来自", "Reply from", "TTL=", "超时", "Timed out"]):
        print("   Ping 192.168.10.1:", l.strip())

# 测试常用 Web 端口 (80, 8080, 443)
for port in [80, 8080, 443]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.0)
    try:
        s.connect(("192.168.10.1", port))
        print(f"  [SUCCESS] 192.168.10.1:{port} 端口连通成功！")
        # 尝试发 HTTP GET
        s.sendall(b"GET / HTTP/1.1\r\nHost: 192.168.10.1\r\nConnection: close\r\n\r\n")
        resp = s.recv(512).decode('latin1', errors='ignore')
        print(f"     -> 收到响应: {resp.splitlines()[0] if resp else 'None'}")
        s.close()
    except Exception as e:
        print(f"  [FAILED] 192.168.10.1:{port} 无法连接: {e}")

# 5. 先测试内网服务器 192.168.10.6 的常见 Web 端口
print("\n[5] 测试内网服务器 192.168.10.6 的 Web 服务 (80/443/8000/8080/8081/8088/8443)...")
for port in [80, 443, 8000, 8080, 8081, 8088, 8443]:
    s_web = None
    try:
        s_web = socket.create_connection(("192.168.10.6", port), timeout=2.5)
        if port in [443, 8443]:
            tls_context = ssl._create_unverified_context()
            s_web = tls_context.wrap_socket(s_web, server_hostname="192.168.10.6")
        s_web.settimeout(2.5)
        print(f"  [SUCCESS] 192.168.10.6:{port} TCP 连接成功")
        s_web.sendall(
            b"GET / HTTP/1.1\r\nHost: 192.168.10.6\r\nConnection: close\r\n\r\n"
        )
        response = s_web.recv(512).decode("latin1", errors="replace")
        status = response.splitlines()[0] if response else "未收到 HTTP 响应"
        print(f"     -> Web 响应: {status}")
    except Exception as e:
        print(f"  [FAILED] 192.168.10.6:{port} Web 探测失败: {e}")
    finally:
        if s_web:
            s_web.close()

# 6. 用 TCP 和 UDP 协议分别测试内网服务器 192.168.10.6:5566；不以 ICMP ping 判断端口状态。
print("\n[6] 使用 TCP/UDP 测试内网服务器 192.168.10.6:5566（端口测试不使用 ping）...")
try:
    vpn_source_ip = get_source_ip("192.168.10.6", 5566)
    print(f"  -> Windows 为目标选择的本机源地址: {vpn_source_ip}")
except OSError as e:
    vpn_source_ip = None
    print(f"  -> 无法确定目标路由的本机源地址: {e}")

# 测试 TCP 5566
s_5566 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s_5566.settimeout(2.5)
try:
    s_5566.connect(("192.168.10.6", 5566))
    print("  [SUCCESS] TCP 192.168.10.6:5566 连接成功 (三次握手建立完成)！")
except Exception as e:
    print(f"  [FAILED] TCP 192.168.10.6:5566 连接失败: {e}")
finally:
    s_5566.close()

# 使用独立 UDP 套接字发送 SIP OPTIONS；Via 的地址和端口必须与实际回包套接字一致。
u_5566 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
u_5566.settimeout(2.5)
try:
    if not vpn_source_ip:
        raise OSError("未能确定本机路由源地址，跳过 SIP/UDP 探测")
    u_5566.bind((vpn_source_ip, 0))
    udp_local_ip, udp_local_port = u_5566.getsockname()
    print(f"  -> SIP/UDP 本地回包套接字: {udp_local_ip}:{udp_local_port}")
    sip_req = (
        f"OPTIONS sip:192.168.10.6:5566 SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {udp_local_ip}:{udp_local_port};branch=z9hG4bKtest;rport\r\n"
        f"From: <sip:test@{vpn_source_ip}>;tag=123\r\n"
        "To: <sip:192.168.10.6:5566>\r\n"
        "Call-ID: test12345\r\nCSeq: 1 OPTIONS\r\nContent-Length: 0\r\n\r\n"
    ).encode("ascii")
    u_5566.sendto(sip_req, ("192.168.10.6", 5566))
    data, addr = u_5566.recvfrom(2048)
    first_line = data.splitlines()[0].decode("latin1", errors="replace") if data else "空响应"
    if first_line.startswith("SIP/2.0 "):
        print(f"  [SUCCESS] UDP SIP 服务响应 ({addr[0]}:{addr[1]}): {first_line}")
    else:
        print(f"  [RECEIVED] UDP 收到数据但不是 SIP 响应 ({addr[0]}:{addr[1]}): {first_line}")
except Exception as e:
    print(f"  [NO RESPONSE] UDP 192.168.10.6:5566 未收到 SIP 响应: {e}")
    print("     -> UDP 无响应不能单独证明端口关闭；服务也可能不响应 OPTIONS 或回包被过滤。")
finally:
    u_5566.close()

# 路由路径参考（tracert 使用 ICMP，仅辅助查看路由，不作为 TCP/UDP 端口判定）。
print("  -> 到目标的路由跟踪（仅作路径参考，不用于判断 TCP/UDP 端口）:")
trace = subprocess.run(["tracert", "-d", "-h", "6", "-w", "1000", "192.168.10.6"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
for line in trace.stdout.decode('gbk', errors='ignore').splitlines():
    if re.search(r"^\s*(Tracing|\d+\s|Trace complete)", line, re.IGNORECASE):
        print("   ", line.strip())

print("\n" + "=" * 65)
print("本测试脚本保留在: D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock_standalone\\test_l2tp_diagnostic.py")
print("=" * 65)
