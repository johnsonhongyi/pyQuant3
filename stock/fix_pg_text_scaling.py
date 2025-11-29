#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 PG 窗口（概念分析）在 DPI 变化后文字不缩放的问题
"""

import re

# 读取文件
with open(r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\instock_MonitorTK.py", "r", encoding="utf-8") as f:
    content = f.read()

# 找到 _apply_scale_dpi_change 函数并在其末尾（catch 块之前）添加 PG 文字缩放代码
old_pattern = r'''(                # 8️⃣ 🔑 重新配置状态栏标签字体（使其自动缩放）
                try:
                    for widget in self\.winfo_children\(\):
                        if isinstance\(widget, tk\.PanedWindow\):
                            for child in widget\.winfo_children\(\):
                                for label in child\.winfo_children\(\):
                                    if isinstance\(label, tk\.Label\):
                                        label\.configure\(font=self\.default_font\)
                    logger\.info\(f'\[DPI变化\] 状态栏标签字体已更新'\)
                except Exception as e_status:
                    logger\.warning\(f'\[DPI变化\] 更新状态栏标签失败: \{e_status\}'\))
            except Exception as e:
                logger\.error\(f'\[DPI变化\] 应用缩放失败: \{e\}'\)'''

new_text = r'''                # 8️⃣ 🔑 重新配置状态栏标签字体（使其自动缩放）
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

                # 9️⃣ 🔑 重新配置 PG 窗口（概念分析）中的文字字体（PyQt TextItem）
                if hasattr(self, '_pg_windows'):
                    try:
                        for unique_code, w_dict in list(self._pg_windows.items()):
                            texts = w_dict.get("texts", [])
                            # 获取当前应用字体大小（已在步骤 2 中更新）
                            app_font = QtWidgets.QApplication.font()
                            font_size = app_font.pointSize()
                            
                            # 更新每个 TextItem 的字体
                            for text in texts:
                                try:
                                    text.setFont(QtGui.QFont("Microsoft YaHei", font_size))
                                except Exception as e_text:
                                    logger.warning(f'[DPI变化] 更新 PG 文字字体失败: {e_text}')
                        logger.info(f'[DPI变化] PG 窗口文字字体已更新（{len(self._pg_windows)} 个窗口）')
                    except Exception as e_pg:
                        logger.warning(f'[DPI变化] 更新 PG 窗口失败: {e_pg}')

            except Exception as e:
                logger.error(f'[DPI变化] 应用缩放失败: {e}')'''

# 执行替换
content = re.sub(old_pattern, new_text, content, flags=re.DOTALL)

# 写回文件
with open(r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\instock_MonitorTK.py", "w", encoding="utf-8") as f:
    f.write(content)

print("[完成] PG 窗口文字缩放已添加到 _apply_scale_dpi_change 函数")
print("✅ 步骤 9️⃣: 更新 PG 窗口（概念分析总览）中的文字字体")
