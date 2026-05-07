# -*- encoding: utf-8 -*-
"""
全局修补 tkcalendar 的已知缺陷
1. 跨月标记导致的选择错误 bug
2. TooltipWrapper 悬浮提示的 KeyError 崩溃
"""

try:
    import tkcalendar
    from tkcalendar.calendar_ import Calendar
    
    _orig_on_click = Calendar._on_click
    def _patched_on_click(self, event):
        if getattr(self, '_properties', {}).get('state', 'normal') == 'normal':
            label = event.widget
            if "disabled" not in label.state():
                day = label.cget("text")
                style = label.cget("style")
                
                is_other_month = False
                if style in ['normal_om.%s.TLabel' % self._style_prefixe, 'we_om.%s.TLabel' % self._style_prefixe]:
                    is_other_month = True
                elif day:
                    try:
                        # 兜底逻辑：即使 style 被 custom tag 覆盖（如 'has_data'），仍通过所在行与日期的常理推断是否跨月
                        if label in self._calendar[0] and int(day) > 20:
                            is_other_month = True
                        elif int(day) < 15:
                            for row in self._calendar[-2:]:
                                if label in row:
                                    is_other_month = True
                                    break
                    except Exception:
                        pass
                        
                if is_other_month:
                    if label in self._calendar[0]:
                        self._prev_month()
                    else:
                        self._next_month()
                
                if day:
                    day = int(day)
                    year, month = self._date.year, self._date.month
                    self._remove_selection()
                    self._sel_date = self.date(year, month, day)
                    self._display_selection()
                    if self._textvariable is not None:
                        self._textvariable.set(self.format_date(self._sel_date))
                    self.event_generate("<<CalendarSelected>>")
    Calendar._on_click = _patched_on_click

    # 🚀 [FIX] 全局修补 tkcalendar TooltipWrapper 悬浮提示的 KeyError 崩溃
    from tkcalendar.tooltip import TooltipWrapper
    _orig_display_tooltip = TooltipWrapper.display_tooltip
    def _patched_display_tooltip(self):
        if getattr(self, 'current_widget', None) is None:
            return
        try:
            disabled = "disabled" in self.current_widget.state()
        except AttributeError:
            try:
                disabled = self.current_widget.cget('state') == "disabled"
            except Exception:
                disabled = False

        if not disabled:
            w_str = str(self.current_widget)
            if w_str in self.widgets:
                self.tooltip['text'] = self.widgets[w_str]
                self.tooltip.deiconify()
                x = self.current_widget.winfo_pointerx() + 14
                y = self.current_widget.winfo_rooty() + self.current_widget.winfo_height() + 2
                self.tooltip.geometry('+%i+%i' % (x, y))
    TooltipWrapper.display_tooltip = _patched_display_tooltip

except Exception as e:
    print(f"tkcalendar patch failed: {e}")
    pass
