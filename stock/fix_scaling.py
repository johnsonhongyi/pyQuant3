#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 instock_MonitorTK.py 中的缩放逻辑
"""
import re

file_path = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\instock_MonitorTK.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 修复 1: get_scaled_value 函数
print("[修复1] 替换 get_scaled_value 函数...")
old_get_scaled = r'''    def get_scaled_value\(self\):
        sf = self\.scale_factor

        if sf <= 1\.25:
            offset = -0\.25
        elif sf < 1\.5:
            offset = -0\.25
        elif sf < 2:
            offset = -0\.25
        else:
            offset = -0\.25

        return sf - offset'''

new_get_scaled = '''    def get_scaled_value(self):
        """返回当前的缩放因子（用于 TreeView 列宽计算）"""
        # ✅ 直接返回 scale_factor，不要做奇怪的减法
        return self.scale_factor'''

content = re.sub(old_get_scaled, new_get_scaled, content)

# 修复 2: _apply_dpi_scaling 中的 ttk.Style 配置
print("[修复2] 移除 _apply_dpi_scaling 中的 ttk.Style rowheight 配置...")
old_apply_dpi = r'''            logger\.info\(f"✅ Tkinter DPI 自动缩放应用于 \{scale_factor\}x \(\{tk_scaling_value\}\)"\)
            
            # 3\. 💥 关键：配置 Treeview 样式以统一处理行高和字体
            style = ttk\.Style\(self\)
            
            # a\. 设置行高 \(Rowheight\)
            BASE_ROW_HEIGHT = 22  # 基础行高像素
            scaled_row_height = int\(BASE_ROW_HEIGHT \* scale_factor\)
            
            # b\. 获取缩放后的字体 \(可选，但推荐用于清晰度\)
            # Tkinter 的 'tk scaling' 已经缩放了默认字体，但显式配置更稳健。
            # 这里我们使用一个基准字体，通常是 'TkDefaultFont'
            default_font = self\.default_font
            
            # 使用 ttk\.Style 配置所有 Treeview 实例
            # 注意：配置行高必须在 Treeview 元素上完成
            style\.configure\(
                "Treeview", 
                rowheight=scaled_row_height,
                font=default_font  # 保持使用 Tkinter 已经缩放过的默认字体
            \)
            
            # 配置 Heading 字体 \(通常需要单独设置，确保列标题也适配\)
            style\.configure\(
                "Treeview\.Heading",
                font=default_font
            \)
            
            logger\.info\(f"✅ Tkinter DPI 自动缩放应用于 \{scale_factor\}x，Treeview 行高设置为 \{scaled_row_height\}"\)'''

new_apply_dpi = '''            logger.info(f"[初始化缩放] ✅ Tkinter scaling 设置为 {tk_scaling_value:.3f}（对应 {scale_factor}x DPI）")

            # ✅ 不再需要手动设置 ttk.Style rowheight
            # tk.call('tk', 'scaling') 已经自动处理了所有的像素度量和字体
            # 手动设置 rowheight 会导致 scaling 失效或冲突'''

content = re.sub(old_apply_dpi, new_apply_dpi, content)

# 保存修改
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("[完成] 所有修复已应用")
print("修复内容：")
print("  1. get_scaled_value() 不再减去 0.25，直接返回 scale_factor")
print("  2. _apply_dpi_scaling() 移除了 ttk.Style rowheight 配置（避免与 tk.scaling 冲突）")
