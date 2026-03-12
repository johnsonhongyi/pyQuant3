import codecs
import sys

def main():
    try:
        with codecs.open(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\stock_visual_utils.py', 'r', 'utf-8') as f:
            lines = f.readlines()

        in_init = False
        init_end_idx = -1
        start_idx = -1

        for i, line in enumerate(lines):
            if line.startswith('class StandaloneKlineChart(QMainWindow, WindowMixin):'):
                start_idx = i
                in_init = True
            if in_init and line.strip().startswith('def closeEvent(self, event):'):
                init_end_idx = i
                break

        if start_idx == -1 or init_end_idx == -1:
            print("Failed to find class markers")
            return

        original_init = lines[start_idx:init_end_idx]

        axis_setup_idx = -1
        for i, L in enumerate(original_init):
            if 'Setup Axis if time labels' in L:
                axis_setup_idx = i
                break

        part1 = original_init[:axis_setup_idx]
        part2 = original_init[axis_setup_idx:]

        placement_idx = -1
        for i, L in enumerate(part2):
            if '# 🚀 [NEW] Smart Placement' in L:
                placement_idx = i
                break

        plot_body = part2[:placement_idx]
        plot_body_clean = []
        for L in plot_body:
            if 'load_window_position_qt' in L:
                continue
            plot_body_clean.append(L)

        end_placement = part2[placement_idx:]

        part1_str = ''.join(part1).replace('layout = QVBoxLayout(central_widget)', 'self.layout_widget = QVBoxLayout(central_widget)')
        part1_str = part1_str.replace('layout.setContentsMargins', 'self.layout_widget.setContentsMargins')
        part1_str = part1_str.replace('layout.setSpacing', 'self.layout_widget.setSpacing')
        part1_str = part1_str.replace('layout.addWidget', 'self.layout_widget.addWidget')

        new_class = part1_str + '''        self.pw = None
        self.update_plot(df, signals, title, avg_series, time_labels, use_line, extra_lines, init=True)

        width, height, x, y = self.load_window_position_qt(self, f"StandaloneKlineChart", default_width=1000, default_height=600)
''' + ''.join(end_placement) + '''
    def update_plot(self, df, signals=None, title="SBC Pattern Chart", avg_series=None, time_labels=None, use_line=False, extra_lines=None, init=False):
        if signals is not None and "SBC" not in title:
            title = f"SBC Pattern - {title}"
        self.setWindowTitle(title)
        
        if self.pw is not None:
            self.layout_widget.removeWidget(self.pw)
            self.pw.deleteLater()
            self.pw = None

''' + ''.join(plot_body_clean).replace('layout.addWidget', 'self.layout_widget.addWidget')

        with codecs.open(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\refactored_chart.py', 'w', 'utf-8') as f:
            f.write(''.join(lines[:start_idx]))
            f.write(new_class)
            f.write(''.join(lines[init_end_idx:]))

        print('Refactored StandaloneKlineChart!')
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
