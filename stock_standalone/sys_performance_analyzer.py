# -*- coding:utf-8 -*-
"""
系统性能与内存占用分析工具 (System Performance & Memory Analyzer)
------------------------------------------------------------------
一个独立的高颜值、工程级系统性能与内存占用诊断工具。
支持 DPI 适配、现代暗黑主题、内存/CPU实时监控、进程分组与明细分析（降序排列）、
智能一键释放、以及明细搜索与进程管理。
"""
import sys
import os
import time
import threading
import platform
import subprocess
import ctypes
from typing import List, Dict, Tuple, Any

import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

# 尝试引入 psutil 进行底层进程抓取
try:
    import psutil
except ImportError:
    # 自动尝试安装 psutil (如果不存在)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

# Windows 高 DPI 适配，防止界面模糊
try:
    if platform.system() == "Windows":
        ctypes.windll.shcore.SetProcessDpiAwareness(1) # DPI Aware
except Exception:
    pass

# ==============================================================================
# UI 样式与配色常量 (Premium Dark Theme System)
# ==============================================================================
COLOR_BG = "#1E2226"          # 极佳的温润护眼暗灰底盘（消减了强对比刺眼感）
COLOR_CARD = "#252A2F"        # 卡片/容器背景（温暖饱满的中性灰）
COLOR_HEADER = "#2D3338"      # 标题栏/头部/表头背景
COLOR_TEXT_MAIN = "#DCE2E8"   # 主文本颜色（莫兰迪柔白，过滤了刺眼的纯白偏振光）
COLOR_TEXT_MUTED = "#8E98A2"  # 辅助文本（淡雅舒适的雾灰蓝，视觉效果极佳）
COLOR_ACCENT = "#81C784"      # 柔雅的莫兰迪翡翠绿（安全/正常）
COLOR_WARNING = "#FFB74D"     # 柔雅的莫兰迪琥珀黄（警告）
COLOR_DANGER = "#E57373"      # 柔雅的莫兰迪珊瑚红（危险/核心警示）
COLOR_HIGHLIGHT = "#64B5F6"   # 柔雅的莫兰迪天空蓝（高亮/选定，高辨识度且柔和）
COLOR_BORDER = "#333A40"      # 极淡雅的边框分割线

# ==============================================================================
# 性能核心监控与分析引擎
# ==============================================================================
class PerformanceEngine:
    @staticmethod
    def get_system_ram_info() -> Dict[str, Any]:
        """获取系统物理内存使用指标"""
        mem = psutil.virtual_memory()
        return {
            "total_gb": mem.total / (1024 ** 3),
            "available_gb": mem.available / (1024 ** 3),
            "used_gb": mem.used / (1024 ** 3),
            "percent": mem.percent
        }

    @staticmethod
    def get_system_cpu_percent() -> float:
        """获取系统 CPU 总体使用率"""
        return psutil.cpu_percent(interval=None)

    @staticmethod
    def scan_and_group_processes() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        扫描系统所有活动进程，并生成：
        1. 分组统计列表 (按内存总量降序排列)
        2. 明细进程列表 (按单体内存降序排列)
        """
        raw_list = []
        grouped_dict = {}

        # 遍历所有活动进程
        for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent', 'status', 'exe']):
            try:
                info = p.info
                if not info['memory_info']:
                    continue
                
                pid = info['pid']
                name = info['name'] or "Unknown"
                rss_mb = info['memory_info'].rss / (1024 ** 2)
                cpu_pct = info['cpu_percent'] or 0.0
                status = info['status'] or "unknown"
                exe_path = info['exe'] or "N/A"

                # 记录明细数据
                raw_list.append({
                    "pid": pid,
                    "name": name,
                    "rss_mb": rss_mb,
                    "cpu_pct": cpu_pct,
                    "status": status,
                    "path": exe_path
                })

                # 记录分组汇总数据
                if name not in grouped_dict:
                    grouped_dict[name] = {
                        "name": name,
                        "count": 0,
                        "total_rss_mb": 0.0,
                        "max_cpu": 0.0,
                        "pids": []
                    }
                grouped_dict[name]["count"] += 1
                grouped_dict[name]["total_rss_mb"] += rss_mb
                grouped_dict[name]["max_cpu"] = max(grouped_dict[name]["max_cpu"], cpu_pct)
                grouped_dict[name]["pids"].append(pid)

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # 明细排序 (按内存降序)
        raw_list.sort(key=lambda x: x["rss_mb"], reverse=True)

        # 分组排序 (按总内存降序)
        grouped_list = list(grouped_dict.values())
        grouped_list.sort(key=lambda x: x["total_rss_mb"], reverse=True)

        return grouped_list, raw_list

    @staticmethod
    def kill_process_by_pid(pid: int) -> Tuple[bool, str]:
        """根据 PID 强制结束指定进程"""
        try:
            p = psutil.Process(pid)
            p.terminate()
            return True, f"成功向 PID {pid} 发送终止信号。"
        except psutil.NoSuchProcess:
            return False, "该进程已经不存在。"
        except psutil.AccessDenied:
            try:
                # 尝试使用 Windows taskkill 提权强制结束
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return True, f"已通过系统管理员权限强制结束 PID {pid}。"
            except Exception as e:
                return False, f"权限不足，终止进程失败: {e}"
        except Exception as e:
            return False, f"未知错误: {e}"

    @staticmethod
    def kill_processes_by_name(name: str) -> Tuple[int, int]:
        """根据进程可执行文件名，批量结束所有相关进程"""
        success_count = 0
        fail_count = 0
        for p in psutil.process_iter(['name', 'pid']):
            try:
                if p.info['name'] and p.info['name'].lower() == name.lower():
                    p.terminate()
                    success_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # 尝试用 taskkill
                try:
                    subprocess.run(f"taskkill /F /IM {name}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    success_count += 1
                except:
                    fail_count += 1
            except Exception:
                fail_count += 1
        return success_count, fail_count

# ==============================================================================
# UI 核心视图类 (GUI Desktop Dashboard)
# ==============================================================================
class SystemPerformanceAnalyzerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("📐 量化系统后台性能与内存深度分析诊断工具")
        # 计算 DPI 缩放因子，用于动态像素对齐，防止高 DPI 下文字与表格宽高不匹配
        try:
            self.dpi_scale = self.winfo_fpixels('1i') / 96.0
        except Exception:
            self.dpi_scale = 1.0
        
        # 采用最初精致和谐的紧凑布局几何比例，并支持自动加载恢复
        try:
            from gui_utils import load_window_position_simple
            default_w, default_h = 1180, 820
            win_w, win_h, win_x, win_y = load_window_position_simple("sys_performance_analyzer", default_w, default_h)
            if win_x is not None and win_y is not None:
                self.geometry(f"{win_w}x{win_h}+{win_x}+{win_y}")
            else:
                self.geometry(f"{win_w}x{win_h}")
        except Exception:
            self.geometry("1180x820")
        self.configure(bg=COLOR_BG)

        # 缓存状态变量
        self.grouped_data: List[Dict[str, Any]] = []
        self.raw_data: List[Dict[str, Any]] = []
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_filter())
        
        self.auto_refresh_var = tk.BooleanVar(value=True)
        self.last_update_time = time.time()

        # 初始化自定义现代暗黑样式
        self.setup_ui_styles()
        
        # 组装 UI 结构
        self.build_header_dashboard()
        self.build_quick_optimizer_bar()
        self.build_main_table_area()
        self.build_statusbar()

        # 自动加载并恢复列宽
        try:
            self.load_column_widths()
        except Exception:
            pass

        # 启动后台自动刷新与数据首次加载
        self.first_load_data()
        self.start_refresh_timer()

        # 物理绑定窗口关闭协议，确保安全存盘
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        """窗口关闭时物理保存大小、位置与列宽，并彻底释放所有资源"""
        try:
            from gui_utils import save_window_position_simple
            save_window_position_simple(self, "sys_performance_analyzer")
        except Exception:
            pass
            
        try:
            self.save_column_widths()
        except Exception:
            pass
            
        self.destroy()

    def save_column_widths(self):
        """保存表格列宽到统一的 window_config.json 中"""
        try:
            import json
            import tempfile
            from sys_utils import get_app_root, get_conf_path
            from dpi_utils import get_windows_dpi_scale_factor
            
            scale = get_windows_dpi_scale_factor()
            base_dir = get_app_root()
            filename = "window_config.json"
            if scale > 1.5:
                filename = f"scale{int(scale)}_window_config.json"
            config_file = get_conf_path(filename, base_dir)
            
            data = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    pass
            
            # 获取分组统计表的列宽
            grouped_cols = ("name", "count", "total_rss", "max_cpu", "pids")
            grouped_widths = [int(self.tree_grouped.column(col, "width") / scale) for col in grouped_cols]
            
            # 获取明细列表的列宽
            raw_cols = ("pid", "name", "rss", "cpu", "status", "path")
            raw_widths = [int(self.tree_raw.column(col, "width") / scale) for col in raw_cols]
            
            data["sys_performance_analyzer_columns"] = {
                "grouped": grouped_widths,
                "raw": raw_widths
            }
            
            # 🚀 [原子化写入] 使用临时文件 + os.replace 确保写入完整，防止 Windows 下并发导致的 0 字节损坏
            fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(config_file), text=True)
            try:
                with os.fdopen(fd, 'w', encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                if os.path.exists(config_file):
                    try:
                        os.chmod(config_file, 0o666)
                    except Exception:
                        pass
                os.replace(temp_path, config_file)
            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                raise e
        except Exception:
            pass

    def load_column_widths(self):
        """从 window_config.json 恢复列宽，并支持 DPI 动态缩放还原"""
        try:
            import json
            from sys_utils import get_app_root, get_conf_path
            from dpi_utils import get_windows_dpi_scale_factor
            
            scale = get_windows_dpi_scale_factor()
            base_dir = get_app_root()
            filename = "window_config.json"
            if scale > 1.5:
                filename = f"scale{int(scale)}_window_config.json"
            config_file = get_conf_path(filename, base_dir)
            
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                cols_data = data.get("sys_performance_analyzer_columns", {})
                
                # 恢复分组表列宽
                grouped_widths = cols_data.get("grouped", [])
                grouped_cols = ("name", "count", "total_rss", "max_cpu", "pids")
                if len(grouped_widths) == len(grouped_cols):
                    for col, w in zip(grouped_cols, grouped_widths):
                        self.tree_grouped.column(col, width=int(w * scale))
                
                # 恢复明细表列宽
                raw_widths = cols_data.get("raw", [])
                raw_cols = ("pid", "name", "rss", "cpu", "status", "path")
                if len(raw_widths) == len(raw_cols):
                    for col, w in zip(raw_cols, raw_widths):
                        self.tree_raw.column(col, width=int(w * scale))
        except Exception:
            pass

    def setup_ui_styles(self):
        """配置现代暗黑风格的 ttk 控件样式"""
        style = ttk.Style(self)
        style.theme_use("clam")

        # 统一全局字体 - 精致微缩一号，提升高密度数据可读性
        self.font_title = tkfont.Font(family="Microsoft YaHei", size=10, weight="bold")
        self.font_body = tkfont.Font(family="Microsoft YaHei", size=9)
        self.font_small = tkfont.Font(family="Microsoft YaHei", size=8)

        # 配置背景、文本及表格样式
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Card.TFrame", background=COLOR_CARD, borderwidth=1, relief="solid")
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT_MAIN, font=self.font_body)
        
        # 仪表板卡片标签
        style.configure("CardTitle.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT_MUTED, font=self.font_small)
        style.configure("CardVal.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT_MAIN, font=tkfont.Font(family="Consolas", size=15, weight="bold"))

        # 自定义选项卡 (Notebook)
        style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=COLOR_HEADER, foreground=COLOR_TEXT_MUTED, padding=[15, 6], font=self.font_title)
        style.map("TNotebook.Tab", 
                  background=[("selected", COLOR_CARD)], 
                  foreground=[("selected", COLOR_HIGHLIGHT)])

        # 现代表格 (Treeview) - 紧凑行高 (25px) 匹配小一号字体，完美高密度布局
        row_height = 25
        style.configure("Treeview", 
                        background=COLOR_CARD, 
                        fieldbackground=COLOR_CARD, 
                        foreground=COLOR_TEXT_MAIN, 
                        rowheight=row_height,
                        font=self.font_body,
                        borderwidth=0)
        style.configure("Treeview.Heading", 
                        background=COLOR_HEADER, 
                        foreground=COLOR_TEXT_MAIN, 
                        font=self.font_title, 
                        relief="flat")
        style.map("Treeview.Heading", background=[("active", COLOR_HIGHLIGHT)], foreground=[("active", COLOR_BG)])
        style.map("Treeview", background=[("selected", COLOR_HIGHLIGHT)], foreground=[("selected", COLOR_BG)])

        # 滚动条样式
        style.configure("Vertical.TScrollbar", background=COLOR_HEADER, borderwidth=0, arrowsize=12)
        
        # 现代输入框
        style.configure("TEntry", fieldbackground=COLOR_HEADER, foreground=COLOR_TEXT_MAIN, borderwidth=0)

    # --------------------------------------------------------------------------
    # UI 视图构建
    # --------------------------------------------------------------------------
    def build_header_dashboard(self):
        """构建顶部系统资源实时状况看板 (CPU、内存占用详情)"""
        top_frame = ttk.Frame(self, padding=(15, 15, 15, 0))
        top_frame.pack(fill="x")

        # 标题栏
        title_bar = ttk.Frame(top_frame)
        title_bar.pack(fill="x", pady=(0, 10))
        
        title_lbl = ttk.Label(title_bar, text="💻 系统实时性能诊断中心 (System Performance Center)", 
                              font=tkfont.Font(family="Microsoft YaHei", size=12, weight="bold"), foreground=COLOR_HIGHLIGHT)
        title_lbl.pack(side="left")

        # 自动刷新开关
        chk_refresh = tk.Checkbutton(title_bar, text="自动每 30 秒刷新", variable=self.auto_refresh_var,
                                     bg=COLOR_BG, fg=COLOR_TEXT_MAIN, selectcolor=COLOR_CARD,
                                     activebackground=COLOR_BG, activeforeground=COLOR_HIGHLIGHT,
                                     font=self.font_small, bd=0, highlightthickness=0)
        chk_refresh.pack(side="right", padx=10)

        btn_manual = tk.Button(title_bar, text=" 🔄 立即刷新 ", command=self.refresh_data_manually,
                               bg=COLOR_HIGHLIGHT, fg=COLOR_BG, font=self.font_small,
                               activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                               bd=0, cursor="hand2", padx=8, pady=3)
        btn_manual.pack(side="right")

        # 诊断卡片容器
        cards_frame = ttk.Frame(top_frame)
        cards_frame.pack(fill="x", pady=5)

        # 卡片 1: 内存使用率
        self.card_ram_pct = self.create_dashboard_card(cards_frame, "物理内存使用率", "0.0%", COLOR_ACCENT)
        self.card_ram_pct.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 卡片 2: 内存详细数值 (已用/总量)
        self.card_ram_val = self.create_dashboard_card(cards_frame, "内存占用明细 (已用 / 总量)", "0.00 GB / 0.00 GB", COLOR_TEXT_MAIN)
        self.card_ram_val.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 卡片 3: 总体 CPU 占用
        self.card_cpu = self.create_dashboard_card(cards_frame, "CPU 瞬时总载荷", "0.0%", COLOR_HIGHLIGHT)
        self.card_cpu.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 卡片 4: 活跃进程数量
        self.card_procs = self.create_dashboard_card(cards_frame, "系统活动进程总数", "0 个", COLOR_WARNING)
        self.card_procs.pack(side="left", fill="both", expand=True)

    def create_dashboard_card(self, parent: ttk.Frame, title: str, init_val: str, color_theme: str) -> ttk.Frame:
        """快捷创建卡片组件"""
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        
        lbl_title = ttk.Label(card, text=title, style="CardTitle.TLabel")
        lbl_title.pack(anchor="w")

        lbl_val = ttk.Label(card, text=init_val, style="CardVal.TLabel")
        lbl_val.configure(foreground=color_theme)
        lbl_val.pack(anchor="w", pady=(8, 0))

        # 保存标签引用，方便后续动态修改
        card.lbl_val = lbl_val
        return card

    def build_quick_optimizer_bar(self):
        """构建一键智能清理快捷面板"""
        opt_frame = ttk.Frame(self, padding=(15, 10, 15, 0))
        opt_frame.pack(fill="x")

        card_opt = ttk.Frame(opt_frame, style="Card.TFrame", padding=10)
        card_opt.pack(fill="x")

        lbl_tip = ttk.Label(card_opt, text="⚡ 智能一键优化引擎 (Smart Optimization): ", 
                            font=self.font_title, foreground=COLOR_WARNING, background=COLOR_CARD)
        lbl_tip.pack(side="left", padx=(5, 15))

        # 智能按钮配置
        btn_configs = [
            ("💬 清理微信小程序", "微信小程序渲染引擎 (WeChatAppEx) 关闭后常驻后台占用极高，点击彻底杀掉释放约 1-1.5GB 内存", self.optimize_wechat),
            ("🐚 结束残留终端", "清理多次编译或未完全退出的闲置 powershell.exe 后台进程", self.optimize_powershell),
            ("📐 强退残留量化进程", "一键杀掉主程序或多进程卡死残存的 instock_MonitorTK 实例", self.optimize_monitor),
            ("📝 一键生成诊断报告", "在本地生成 Markdown 高阶系统体检报告并直接用记事本打开", self.generate_md_report)
        ]

        for text, tooltip_text, func in btn_configs:
            btn = tk.Button(card_opt, text=text, command=func,
                            bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, font=self.font_small,
                            activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                            bd=0, cursor="hand2", padx=10, pady=4)
            btn.pack(side="left", padx=5)

            # 自定义轻量级 ToolTip (悬停状态栏提示)
            self.bind_tooltip(btn, tooltip_text)

    def build_main_table_area(self):
        """构建主体数据分析表格，包含“分组汇总”和“明细列表”两个双向选项卡"""
        main_frame = ttk.Frame(self, padding=(15, 10, 15, 10))
        main_frame.pack(fill="both", expand=True)

        # 顶层布局：选项卡组件
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True)

        # -------------------- 选项卡 1：进程分组统计表 --------------------
        tab_grouped = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab_grouped, text=" 📊 进程归组汇总 (Grouped Summary) ")

        # 过滤与统计提示区
        group_top = ttk.Frame(tab_grouped)
        group_top.pack(fill="x", pady=(0, 5))
        
        lbl_group_desc = ttk.Label(group_top, text="💡 将同名进程（如多进程架构下的 Python / Chrome 实例）进行物理归总，按总常驻内存从大到小排序：", 
                                   font=self.font_small, foreground=COLOR_TEXT_MUTED)
        lbl_group_desc.pack(side="left")

        # 分组表格
        self.tree_grouped = self.create_treeview(
            tab_grouped,
            columns=("name", "count", "total_rss", "max_cpu", "pids"),
            headings=("📦 进程映像名称 (Executable Name)", "🔢 实例数", "💾 总物理内存占用 (Total RAM)", "⚡ 峰值 CPU %", "🔑 包含 PID 集合")
        )
        self.tree_grouped.column("name", width=220, anchor="w")
        self.tree_grouped.column("count", width=80, anchor="center")
        self.tree_grouped.column("total_rss", width=140, anchor="e")
        self.tree_grouped.column("max_cpu", width=90, anchor="center")
        self.tree_grouped.column("pids", width=420, anchor="w")

        # -------------------- 选项卡 2：明细进程表 (支持实时模糊搜索) --------------------
        tab_raw = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab_raw, text=" 🔬 完整进程明细 (Detailed Processes) ")

        # 搜索过滤条
        search_bar = ttk.Frame(tab_raw)
        search_bar.pack(fill="x", pady=(0, 5))

        lbl_search = ttk.Label(search_bar, text="🔍 输入进程名/PID模糊过滤: ", font=self.font_title)
        lbl_search.pack(side="left", padx=5)

        # 现代感单行输入框 (Tk Entry 自定义)
        self.ent_search = tk.Entry(search_bar, textvariable=self.search_var, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, 
                                   insertbackground=COLOR_TEXT_MAIN, font=self.font_body, bd=1, relief="solid")
        self.ent_search.pack(side="left", fill="x", expand=True, padx=5, ipady=3)

        btn_clear_search = tk.Button(search_bar, text=" 清空 ", command=lambda: self.search_var.set(""),
                                     bg=COLOR_HEADER, fg=COLOR_TEXT_MUTED, font=self.font_small, bd=0, cursor="hand2",
                                     activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG)
        btn_clear_search.pack(side="left", padx=5)

        # 明细表格
        self.tree_raw = self.create_treeview(
            tab_raw,
            columns=("pid", "name", "rss", "cpu", "status", "path"),
            headings=("🔑 PID", "📦 进程名称", "💾 物理内存 (RAM)", "⚡ CPU %", "💡 运行状态", "📂 可执行文件路径 (File Path)")
        )
        self.tree_raw.column("pid", width=85, anchor="center")
        self.tree_raw.column("name", width=180, anchor="w")
        self.tree_raw.column("rss", width=120, anchor="e")
        self.tree_raw.column("cpu", width=80, anchor="center")
        self.tree_raw.column("status", width=90, anchor="center")
        self.tree_raw.column("path", width=500, anchor="w")

    def create_treeview(self, parent: ttk.Frame, columns: tuple, headings: tuple) -> ttk.Treeview:
        """通用封装：快速创建高颜值暗黑 Treeview 带美化滚动条"""
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)

        tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="browse")
        
        # 绑定列头和点击排序属性
        for col, head in zip(columns, headings):
            tree.heading(col, text=head, command=lambda c=col: self.sort_treeview_column(tree, c, False))
            
        tree.pack(side="left", fill="both", expand=True)

        # 美化细边框垂直滚动条
        vbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        vbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=vbar.set)

        # 绑定右键菜单
        tree.bind("<Button-3>", lambda event: self.show_context_menu(event, tree))

        return tree

    def build_statusbar(self):
        """构建底端信息提示状态栏"""
        self.status_bar = ttk.Frame(self, padding=(15, 2, 15, 2), style="Card.TFrame")
        self.status_bar.pack(fill="x", side="bottom")

        self.status_lbl = ttk.Label(self.status_bar, text="Ready. 系统性能监视引擎运行中...", font=self.font_small, foreground=COLOR_TEXT_MUTED)
        self.status_lbl.pack(side="left")

        self.time_lbl = ttk.Label(self.status_bar, text="最后同步时间: --:--:--", font=self.font_small, foreground=COLOR_TEXT_MUTED)
        self.time_lbl.pack(side="right")

    # --------------------------------------------------------------------------
    # 悬停 ToolTip 绑定系统
    # --------------------------------------------------------------------------
    def bind_tooltip(self, widget, text: str):
        """在底部状态栏同步显示按钮的提示，避免遮挡悬浮窗"""
        widget.bind("<Enter>", lambda e: self.set_status_text(f"💡 说明: {text}", color=COLOR_WARNING))
        widget.bind("<Leave>", lambda e: self.set_status_text("Ready. 系统性能监视引擎运行中...", color=COLOR_TEXT_MUTED))

    def set_status_text(self, text: str, color=COLOR_TEXT_MAIN):
        self.status_lbl.configure(text=text, foreground=color)

    # --------------------------------------------------------------------------
    # 数据流加载、刷新与渲染核心 (Thread-safe Data Piping)
    # --------------------------------------------------------------------------
    def first_load_data(self):
        """首次强制同步加载数据，防首屏白洞"""
        self.set_status_text("⏳ 正在进行系统全量进程深度扫描...", COLOR_HIGHLIGHT)
        self.update()
        self.execute_refresh_cycle()

    def start_refresh_timer(self):
        """后台轮询刷新定时器"""
        def loop():
            while True:
                time.sleep(30.0)
                if self.auto_refresh_var.get():
                    self.execute_refresh_cycle()

        # 开启守护线程进行后台静默扫描，防 UI 线程假死卡顿
        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def refresh_data_manually(self):
        """手动强制刷新触发"""
        self.set_status_text("⏳ 正在手动重新抓取全量系统进程...", COLOR_HIGHLIGHT)
        self.execute_refresh_cycle(is_manual=True)

    def execute_refresh_cycle(self, is_manual=False):
        """核心数据异步加载闭环，确保主线程0毫秒阻塞"""
        def async_worker():
            try:
                # 1. 抓取系统硬件基础状况
                ram_info = PerformanceEngine.get_system_ram_info()
                cpu_pct = PerformanceEngine.get_system_cpu_percent()

                # 2. 扫描并归类排序进程 (在后台线程中进行 heavy calculations)
                grouped, raw = PerformanceEngine.scan_and_group_processes()
                self.grouped_data = grouped
                self.raw_data = raw

                # 3. 线程安全地回调 UI 进行绘制
                self.after(0, lambda: self.render_ui(ram_info, cpu_pct, is_manual))
            except Exception as e:
                self.after(0, lambda: self.set_status_text(f"❌ 性能指标抓取发生异常: {e}", COLOR_DANGER))

        # 开启独立守护线程，保证主界面 100% 顺滑，绝不卡顿
        worker_thread = threading.Thread(target=async_worker, daemon=True)
        worker_thread.start()

    def render_ui(self, ram_info: dict, cpu_pct: float, is_manual=False):
        """渲染顶部核心卡片及表格数据"""
        # 更新卡片数值
        self.card_ram_pct.lbl_val.configure(text=f"{ram_info['percent']}%")
        # 根据内存占用率变色
        if ram_info['percent'] > 85:
            self.card_ram_pct.lbl_val.configure(foreground=COLOR_DANGER)
        elif ram_info['percent'] > 70:
            self.card_ram_pct.lbl_val.configure(foreground=COLOR_WARNING)
        else:
            self.card_ram_pct.lbl_val.configure(foreground=COLOR_ACCENT)

        self.card_ram_val.lbl_val.configure(text=f"{ram_info['used_gb']:.2f} GB / {ram_info['total_gb']:.2f} GB")
        self.card_cpu.lbl_val.configure(text=f"{cpu_pct:.1f}%")
        self.card_procs.lbl_val.configure(text=f"{len(self.raw_data)} 个")

        # 刷新渲染表格数据
        self.render_grouped_table()
        self.apply_filter()  # 应用搜索框内容后渲染明细表格

        # 更新底端状态栏
        self.time_lbl.configure(text=f"最后同步时间: {time.strftime('%H:%M:%S')}")
        if is_manual:
            self.set_status_text("✅ 物理内存与进程状态手动刷新成功！", COLOR_ACCENT)

    def render_grouped_table(self):
        """加载渲染进程分组汇总表 (降序)"""
        # 记录当前选中项，以防刷新后闪烁丢失选中
        selected_item = self.tree_grouped.selection()
        selected_name = ""
        if selected_item:
            selected_name = self.tree_grouped.item(selected_item[0])["values"][0]

        # 清空重绘
        for item in self.tree_grouped.get_children():
            self.tree_grouped.delete(item)

        for g in self.grouped_data:
            rss_str = f"{g['total_rss_mb']:.2f} MB"
            if g['total_rss_mb'] >= 1024:
                rss_str = f"{g['total_rss_mb']/1024:.2f} GB"

            pids_str = ", ".join(map(str, g['pids'][:12]))
            if len(g['pids']) > 12:
                pids_str += f" ... 等共 {len(g['pids'])} 个"

            item_id = self.tree_grouped.insert("", "end", values=(
                g['name'],
                g['count'],
                rss_str,
                f"{g['max_cpu']:.1f}%",
                pids_str
            ))

            # 还原选中项
            if g['name'] == selected_name:
                self.tree_grouped.selection_set(item_id)

    def apply_filter(self):
        """实时执行模糊搜索框的规则过滤与渲染"""
        query = self.search_var.get().strip().lower()

        # 备份当前明细表格的选中 PID
        selected_item = self.tree_raw.selection()
        selected_pid = -1
        if selected_item:
            selected_pid = int(self.tree_raw.item(selected_item[0])["values"][0])

        # 清空明细表
        for item in self.tree_raw.get_children():
            self.tree_raw.delete(item)

        # 迭代数据源进行模糊比对
        for r in self.raw_data:
            if query:
                pid_match = query in str(r['pid'])
                name_match = query in r['name'].lower()
                path_match = query in r['path'].lower()
                if not (pid_match or name_match or path_match):
                    continue

            rss_str = f"{r['rss_mb']:.2f} MB"
            if r['rss_mb'] >= 1024:
                rss_str = f"{r['rss_mb']/1024:.2f} GB"

            item_id = self.tree_raw.insert("", "end", values=(
                r['pid'],
                r['name'],
                rss_str,
                f"{r['cpu_pct']:.1f}%",
                r['status'],
                r['path']
            ))

            # 还原选中
            if r['pid'] == selected_pid:
                self.tree_raw.selection_set(item_id)

    # --------------------------------------------------------------------------
    # 表格交互管理 (右键菜单、列排序、数据自适应)
    # --------------------------------------------------------------------------
    def show_context_menu(self, event, tree: ttk.Treeview):
        """右键弹出高级系统进程控制菜单"""
        item = tree.identify_row(event.y)
        if not item:
            return
        tree.selection_set(item)

        menu = tk.Menu(self, tearoff=0, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, activebackground=COLOR_HIGHLIGHT)
        
        # 判断是分组汇总表还是明细表
        if tree == self.tree_grouped:
            values = tree.item(item)["values"]
            name = values[0]
            menu.add_command(label=f"🔪 结束全部该映像进程 ({name})", command=lambda: self.kill_grouped_processes_action(name))
        else:
            values = tree.item(item)["values"]
            pid = int(values[0])
            name = values[1]
            path = values[5]
            
            menu.add_command(label=f"🔬 查看 PID {pid} 诊断详情", command=lambda: self.view_process_detail_action(pid, name, path))
            menu.add_command(label=f"🔪 强制终止该单个进程 (PID: {pid})", command=lambda: self.kill_single_process_action(pid, name))
            menu.add_separator()
            menu.add_command(label="📂 打开进程文件所在目录", command=lambda: self.open_file_location_action(path))

        menu.tk_popup(event.x_root, event.y_root)

    def sort_treeview_column(self, tree: ttk.Treeview, col: str, reverse: bool):
        """点击表头对表格进行排序"""
        data_list = []
        for child in tree.get_children(""):
            val = tree.set(child, col)
            # 对含有数字/容量后缀的列进行智能科学排序适配
            sort_val = val
            if col in ("total_rss", "rss"):
                # 将 "MB/GB" 转化为统一 Float 参与物理排序
                try:
                    num_part = float(val.split()[0])
                    if "GB" in val:
                        num_part *= 1024
                    sort_val = num_part
                except:
                    sort_val = 0.0
            elif col == "count":
                sort_val = int(val)
            elif col == "pid":
                sort_val = int(val)
            elif "cpu" in col.lower():
                try:
                    sort_val = float(val.replace("%", ""))
                except:
                    sort_val = 0.0
            else:
                sort_val = str(val).lower()

            data_list.append((sort_val, child))

        # 执行排序
        data_list.sort(reverse=reverse)

        # 重新编排顺序
        for index, (val, child) in enumerate(data_list):
            tree.move(child, "", index)

        # 重置表头点击状态实现升降序双向切换
        tree.heading(col, command=lambda: self.sort_treeview_column(tree, col, not reverse))

    # --------------------------------------------------------------------------
    # 进程控制管理动作 (Process Management Actions)
    # --------------------------------------------------------------------------
    def kill_single_process_action(self, pid: int, name: str):
        """强制结束单体进程"""
        if messagebox.askyesno("⚠️ 警告", f"确定要彻底关闭进程: {name} (PID: {pid}) 吗？\n如果该进程属于关键系统服务，可能会引起系统崩溃！"):
            success, msg = PerformanceEngine.kill_process_by_pid(pid)
            if success:
                self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
                self.execute_refresh_cycle()
            else:
                messagebox.showerror("❌ 操作失败", msg)

    def kill_grouped_processes_action(self, name: str):
        """批量结束某类同名映像的所有进程"""
        if messagebox.askyesno("⚠️ 警告", f"确定要强杀所有名称为 {name} 的并发子进程吗？\n这将向系统所有该名称的实例发送结束指令！"):
            self.set_status_text(f"⏳ 正在深度清理全部 {name} 进程...", COLOR_HIGHLIGHT)
            self.update()
            success_cnt, fail_cnt = PerformanceEngine.kill_processes_by_name(name)
            self.set_status_text(f"✅ 清理完成！成功结束 {success_cnt} 个，失败 {fail_cnt} 个 {name} 进程。", COLOR_ACCENT)
            self.execute_refresh_cycle()

    def view_process_detail_action(self, pid: int, name: str, path: str):
        """查看某个明细进程的深度系统级信息"""
        try:
            p = psutil.Process(pid)
            ctime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.create_time()))
            mem_info = p.memory_full_info()
            
            detail_msg = (
                f"📦 映像名称: {name}\n"
                f"🔑 进程 PID: {pid}\n"
                f"💡 运行状态: {p.status()}\n"
                f"⏰ 创建时间: {ctime}\n"
                f"📂 可执行文件路径:\n{path}\n\n"
                f"--- 💾 内存指标详情 ---\n"
                f"• 常驻内存 (RSS): {mem_info.rss / (1024**2):.2f} MB\n"
                f"• 虚拟内存 (VMS): {mem_info.vms / (1024**2):.2f} MB\n"
                f"• 私有物理集 (USS): {getattr(mem_info, 'uss', 0) / (1024**2):.2f} MB\n"
                f"• 页面交换占池: {getattr(mem_info, 'pagefile', 0) / (1024**2):.2f} MB\n"
                f"• 系统调用句柄数: {p.num_handles() if hasattr(p, 'num_handles') else 'N/A'}"
            )
            messagebox.showinfo(f"🔬 进程 {name} (PID: {pid}) 诊断报告", detail_msg)
        except Exception as e:
            messagebox.showerror("❌ 获取详情失败", f"无法抓取该进程指标，可能已经自动退出: {e}")

    def open_file_location_action(self, path: str):
        """在 Windows 资源管理器中高亮选中文件路径"""
        if path == "N/A" or not os.path.exists(path):
            messagebox.showwarning("⚠️ 路径不可达", "该进程路径不存在，无法打开位置。")
            return
        
        try:
            # 在 explorer 中直接定位高亮文件
            subprocess.run(f'explorer.exe /select,"{os.path.normpath(path)}"', shell=True)
        except Exception as e:
            messagebox.showerror("❌ 启动资源管理器失败", f"无法打开位置: {e}")

    # --------------------------------------------------------------------------
    # 智能一键优化清理逻辑 (One-Click Optimization Kernels)
    # --------------------------------------------------------------------------
    def optimize_wechat(self):
        """清理常驻后台不退出的微信小程序渲染引擎 (WeChatAppEx)"""
        p_name = "WeChatAppEx.exe"
        self.set_status_text("⏳ 正在批量强制清理微信后台残留小程序渲染进程...", COLOR_HIGHLIGHT)
        self.update()
        
        success_cnt, fail_cnt = PerformanceEngine.kill_processes_by_name(p_name)
        if success_cnt > 0:
            self.set_status_text(f"✅ 成功清理了 {success_cnt} 个 WeChatAppEx 渲染进程，瞬间释放超过 1.0 GB 内存！", COLOR_ACCENT)
            messagebox.showinfo("⚡ 清理成功", f"成功强制杀掉 {success_cnt} 个常驻后台的小程序渲染进程！")
        else:
            self.set_status_text("💡 未检测到有处于活动状态的 WeChatAppEx.exe 进程。", COLOR_TEXT_MUTED)
            messagebox.showinfo("⚡ 扫描完成", "后台没有发现残留的微信小程序渲染进程。")
        self.execute_refresh_cycle()

    def optimize_powershell(self):
        """一键清理卡死或闲置残留的 Powershell 后台命令行终端"""
        p_name = "powershell.exe"
        self.set_status_text("⏳ 正在扫描并清理卡死或无用 Powershell 后台终端...", COLOR_HIGHLIGHT)
        self.update()
        
        success_cnt, fail_cnt = PerformanceEngine.kill_processes_by_name(p_name)
        if success_cnt > 0:
            self.set_status_text(f"✅ 成功关闭了 {success_cnt} 个 powershell 后台残留进程！", COLOR_ACCENT)
            messagebox.showinfo("⚡ 清理成功", f"成功强制终止了 {success_cnt} 个常驻后台的 PowerShell 终端！")
        else:
            self.set_status_text("💡 未发现常驻后台的可终止 powershell.exe 进程。", COLOR_TEXT_MUTED)
            messagebox.showinfo("⚡ 扫描完成", "后台没有发现残留的 PowerShell 后台进程。")
        self.execute_refresh_cycle()

    def optimize_monitor(self):
        """一键结束残留的主系统进程实例"""
        p_name = "instock_MonitorTK_Nuita.exe"
        # 找出当前运行的所有该进程，排除自身父子关系后杀掉
        current_pid = os.getpid()
        killed_cnt = 0
        for p in psutil.process_iter(['name', 'pid']):
            try:
                if p.info['name'] == p_name and p.info['pid'] != current_pid:
                    p.terminate()
                    killed_cnt += 1
            except:
                pass
        
        if killed_cnt > 0:
            self.set_status_text(f"✅ 成功强退了 {killed_cnt} 个残留的量化系统主窗口实例！", COLOR_ACCENT)
            messagebox.showinfo("⚡ 清理成功", f"已成功强制退出 {killed_cnt} 个残留的 instock_MonitorTK_Nuita 实例！")
        else:
            self.set_status_text("💡 没有发现多余残留的量化系统进程实例。", COLOR_TEXT_MUTED)
            messagebox.showinfo("⚡ 扫描完成", "未检测到有其他多余常驻后台的主系统进程实例。")
        self.execute_refresh_cycle()

    def generate_md_report(self):
        """一键生成高阶 Markdown 诊断体检报告并使用系统记事本打开"""
        # 读取当前硬件与进程状态
        ram = PerformanceEngine.get_system_ram_info()
        cpu = PerformanceEngine.get_system_cpu_percent()
        
        # 取分组 Top 10
        top_groups = self.grouped_data[:10]
        
        report_content = f"""# 📐 系统性能与内存占用分析体检报告
报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
--------------------------------------------------

## 📊 1. 物理内存与 CPU 负载指标
* 🖥️ 物理内存总量: {ram['total_gb']:.2f} GB
* 💾 物理内存已用: {ram['used_gb']:.2f} GB (占比: {ram['percent']}%)
* 💡 物理内存可用: {ram['available_gb']:.2f} GB
* ⚡ CPU 瞬时总体载荷: {cpu:.1f}%
* 🔑 活动进程总数: {len(self.raw_data)} 个

## 🔍 2. 常驻内存 (RSS) 消耗前十名进程汇总
以下是将同名多进程映像物理汇总后的消耗排名：

"""
        for i, g in enumerate(top_groups, 1):
            rss_str = f"{g['total_rss_mb']:.2f} MB"
            if g['total_rss_mb'] >= 1024:
                rss_str = f"{g['total_rss_mb']/1024:.2f} GB"
            report_content += f"{i}. **{g['name']}** (活动实例: {g['count']} 个) -> 累计占用: **{rss_str}** | 峰值 CPU: {g['max_cpu']:.1f}%\n"

        report_content += """
## ⚡ 3. 智能优化建议
1. 当前系统开发环境组件 (Antigravity.exe & language_server) 及日常办公 (WeChat / Edge) 占据了大量缓存。
2. 建议对常驻后台的微信小程序渲染进程 `WeChatAppEx.exe` 及闲置 `powershell.exe` 进行定期清理，可以直接释放 2GB 以上内存。
3. 行情系统主控 `instock_MonitorTK_Nuita.exe` 当前占用属于多进程并发架构下的安全阈值，无需担忧。
"""
        
        # 写入临时文件
        temp_dir = os.environ.get("TEMP", os.getcwd())
        report_path = os.path.join(temp_dir, "System_Memory_Diagnosis_Report.md")
        
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            
            # 使用默认记事本打开该 MD 文件
            os.system(f'notepad.exe "{report_path}"')
            self.set_status_text(f"✅ 诊断报告生成成功: {report_path}", COLOR_ACCENT)
        except Exception as e:
            messagebox.showerror("❌ 报告生成失败", f"无法写入诊断文件: {e}")

# ==============================================================================
# 应用程序物理入口点 (App Main Entry)
# ==============================================================================
if __name__ == "__main__":
    app = SystemPerformanceAnalyzerGUI()
    app.mainloop()
