#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完全重写 _apply_scale_dpi_change 函数，修复所有缩放问题
"""

file_path = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\instock_MonitorTK.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 找到完整的 _apply_scale_dpi_change 函数并替换
old_func_start = 'def _apply_scale_dpi_change(self, scale_factor):'
old_func_pattern = r'def _apply_scale_dpi_change\(self, scale_factor\):.*?(?=\n    def |\nclass |\Z)'

import re

# 新的完整函数
new_func = '''def _apply_scale_dpi_change(self, scale_factor):
            """当检测到 DPI 变化时，自动放大/缩小主窗口及所有 UI 元素"""
            try:
                # 1️⃣ 调整窗口大小
                width = self.winfo_width()
                height = self.winfo_height()
                new_w = int(width * scale_factor / self.scale_factor)
                new_h = int(height * scale_factor / self.scale_factor)
                logger.info(f'[DPI变化] scale_factor: {scale_factor:.2f} old_scale: {self.scale_factor:.2f} window_size: {width}x{height} -> {new_w}x{new_h}')
                self.geometry(f"{new_w}x{new_h}")

                # 2️⃣ 调整字体大小
                old_size = self.default_font.cget("size")
                new_size = int(old_size * scale_factor / self.scale_factor)
                new_size = max(6, min(new_size, 16))  # 最小6 最大16
                self.default_font.configure(size=new_size)
                self.default_font_bold.configure(size=new_size)
                logger.info(f'[DPI变化] 字体大小: {old_size}pt -> {new_size}pt')

                # 3️⃣ 更新缩放因子
                old_scale = self.scale_factor
                self.scale_factor = scale_factor

                # 4️⃣ 触发 TreeView 列宽重新计算
                if hasattr(self, 'current_cols') and hasattr(self, 'tree'):
                    logger.info(f'[DPI变化] 重新计算 TreeView 列宽')
                    self._setup_tree_columns(
                        self.tree,
                        tuple(self.current_cols),
                        sort_callback=self.sort_by_column,
                        other={}
                    )

                # 5️⃣ 应用全局 Tkinter 缩放（字体和像素度量）
                tk_scaling_value = (scale_factor * DEFAULT_DPI) / 72.0
                self.tk.call('tk', 'scaling', tk_scaling_value)
                logger.info(f'[DPI变化] Tkinter scaling 设置为 {tk_scaling_value:.3f}（对应 {scale_factor:.2f}x DPI）')

                # 6️⃣ 🔑 设置 TreeView 行高（显式设置，确保正确缩放）
                if hasattr(self, 'tree'):
                    try:
                        style = ttk.Style(self)
                        BASE_ROW_HEIGHT = 22  # 基础行高像素
                        scaled_row_height = int(BASE_ROW_HEIGHT * scale_factor)
                        style.configure('Treeview', rowheight=scaled_row_height)
                        logger.info(f'[DPI变化] TreeView 行高设置为 {scaled_row_height}px')
                    except Exception as e_row:
                        logger.warning(f'[DPI变化] 设置 TreeView 行高失败: {e_row}')

                # 7️⃣ 🔑 重新配置 TreeView 列标题的字体（使其自动缩放）
                if hasattr(self, 'tree'):
                    try:
                        style = ttk.Style(self)
                        style.configure('Treeview.Heading', font=self.default_font)
                        logger.info(f'[DPI变化] TreeView 列标题字体已更新')
                    except Exception as e_heading:
                        logger.warning(f'[DPI变化] 更新 TreeView 列标题失败: {e_heading}')

                # 8️⃣ 🔑 重新配置状态栏标签字体（使其自动缩放）
                try:
                    for widget in self.winfo_children():
                        if isinstance(widget, tk.PanedWindow):
                            for child in widget.winfo_children():
                                for label in child.winfo_children():
                                    if isinstance(label, tk.Label):
                                        label.configure(font=self.default_font)
                    logger.info(f'[DPI变化] 状态栏标签字体已更新')
                except Exception as e_status:
                    logger.warning(f'[DPI变化] 更新状态栏标签失败: {e_status}')

                logger.info(f"[DPI变化] ✅ 完成全部缩放：{old_scale:.2f}x -> {scale_factor:.2f}x (窗口/字体/TreeView/状态栏)")

            except Exception as e:
                logger.error(f"[DPI变化] ❌ 应用缩放失败: {e}", exc_info=True)'''

# 使用 re.DOTALL 使 . 匹配换行符
pattern = r'    def _apply_scale_dpi_change\(self, scale_factor\):.*?(?=\n    def [a-z_]|\nclass |\Z)'
content = re.sub(pattern, '    ' + new_func, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("[完成] _apply_scale_dpi_change 函数已完全重写")
print("修复内容：")
print("  ✅ 1. TreeView 行高现在会根据 DPI 变化自动调整")
print("  ✅ 2. TreeView 列标题字体现在会根据 DPI 变化自动缩放")
print("  ✅ 3. 状态栏标签字体现在会根据 DPI 变化自动缩放")
print("  ✅ 4. 所有代码都在 try 块内，异常处理正确")
