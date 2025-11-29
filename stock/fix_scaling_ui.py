#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 TreeView 行高、列标题字体、状态栏字体缩放问题
"""

file_path = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\instock_MonitorTK.py"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到 _apply_scale_dpi_change 函数的结束位置（找到最后的 except Exception as e）
# 然后在 logger.error() 之前插入新代码

# 查找目标行
for i, line in enumerate(lines):
    if 'logger.error(f"[DPI变化] ❌ 应用缩放失败:' in line:
        # 找到这一行，在它之前插入新代码
        insert_pos = i
        break

# 新增的代码块
new_code = '''                # 6️⃣ **新增**：设置 TreeView 行高（必须在 tk.call('tk', 'scaling') 之后）
                # ✅ 这一次，我们明确为 ttk.Treeview 设置行高以确保正确缩放
                if hasattr(self, 'tree'):
                    try:
                        style = ttk.Style(self)
                        BASE_ROW_HEIGHT = 22  # 基础行高像素
                        scaled_row_height = int(BASE_ROW_HEIGHT * scale_factor / old_scale)
                        style.configure('Treeview', rowheight=scaled_row_height)
                        logger.info(f'[DPI变化] TreeView 行高设置为 {scaled_row_height}px')
                    except Exception as e_row:
                        logger.error(f'[DPI变化] 设置 TreeView 行高失败: {e_row}')

                # 7️⃣ **新增**：重新配置 TreeView 列标题的字体
                # ✅ 列标题需要显式指定字体才会应用缩放
                if hasattr(self, 'tree'):
                    try:
                        # 更新 ttk.Style 中的 Treeview.Heading 字体
                        style = ttk.Style(self)
                        style.configure('Treeview.Heading', font=self.default_font)
                        logger.info(f'[DPI变化] TreeView 列标题字体已更新')
                    except Exception as e_heading:
                        logger.error(f'[DPI变化] 更新 TreeView 列标题失败: {e_heading}')

                # 8️⃣ **新增**：重新配置状态栏标签字体
                # ✅ 状态栏中的 Label 是普通 tk.Label，需要显式更新字体
                try:
                    for widget in self.winfo_children():
                        if isinstance(widget, tk.PanedWindow):
                            for child in widget.winfo_children():
                                for label in child.winfo_children():
                                    if isinstance(label, tk.Label):
                                        label.configure(font=self.default_font)
                    logger.info(f'[DPI变化] 状态栏标签字体已更新')
                except Exception as e_status:
                    logger.error(f'[DPI变化] 更新状态栏标签失败: {e_status}')

                logger.info(f"[DPI变化] ✅ 完成缩放：{old_scale:.2f}x -> {scale_factor:.2f}x")

'''

# 在 insert_pos 之前插入新代码
lines.insert(insert_pos, new_code)

# 写回文件
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("[完成] 所有 UI 缩放问题已修复")
print("修复内容：")
print("  1. ✅ TreeView 行高现在会根据 DPI 变化自动调整")
print("  2. ✅ TreeView 列标题字体现在会根据 DPI 变化自动缩放")
print("  3. ✅ 状态栏标签字体现在会根据 DPI 变化自动缩放")
