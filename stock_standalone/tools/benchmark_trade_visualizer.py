"""Reproducible offscreen microbenchmarks; optional comparison with Git HEAD."""
import argparse
import json
import logging
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg
from visualizer_test_support import load_visualizer, make_harness, candle_data, market_frame, TimerQueue


def measure(action, repeats):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        action()
        samples.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(samples), 3)


def render_image(item):
    image = QImage(1200, 600, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.translate(30, 300)
    painter.scale(7, -60)
    painter.translate(0, -10)
    painter.setClipRect(QRectF(0, 5, 150, 10))
    item.paint(painter, SimpleNamespace(exposedRect=QRectF(0, 5, 150, 10)))
    painter.end()
    data = image.constBits()
    data.setsize(image.sizeInBytes())
    return bytes(data)


def benchmark(source, repeats):
    namespace = load_visualizer(source)
    namespace['logger'].setLevel(logging.ERROR)
    metrics = {}
    for size in (4096, 20000):
        values = candle_data(size)
        item = namespace['CandlestickItem'](values)
        same = measure(lambda: item.setData(values), repeats)
        def update_last():
            values[-1, 2] += .001
            item.setData(values)
        tail = measure(update_last, repeats)
        canvas = QImage(1000, 600, QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.white)
        painter = QPainter(canvas)
        painter.scale(1000 / 150, 100)
        option = SimpleNamespace(exposedRect=QRectF(0, 8, 150, 5))
        paint = measure(lambda: item.paint(painter, option), repeats)
        painter.end()
        metrics[f'candle_{size}'] = {'identical_ms': same, 'tail_ms': tail, 'paint_150_ms': paint}
    queue = TimerQueue()
    namespace['QtCore'] = SimpleNamespace(QTimer=queue)
    window = make_harness(namespace, table=True)
    frame = market_frame(5000)
    window.update_stock_table(frame, force_full=True)
    queue.drain()
    changed = ['000010', '000100', '000900', '002000', '004000']
    def update_table():
        frame.loc[changed, 'close'] += .001
        window.update_stock_table(frame, changed_codes=set(changed))
        queue.drain()
    metrics['table_5000_changed_5_ms'] = measure(update_table, repeats)
    window._closing = True
    window.deleteLater()
    metrics.update(benchmark_refresh_and_colors(namespace))
    sample = namespace['CandlestickItem'](candle_data(4096))
    return metrics, render_image(sample), namespace


def benchmark_refresh_and_colors(namespace):
    saved_time, saved_qt = namespace['time'], namespace['QtCore']
    window = make_harness(namespace, table=True)
    callbacks, table_flushes = [], []
    namespace['time'] = SimpleNamespace(time=lambda: 10., monotonic=lambda: 10.)
    namespace['QtCore'] = SimpleNamespace(QTimer=SimpleNamespace(
        singleShot=lambda delay, callback: callbacks.append(callback)))
    try:
        window.df_all = market_frame(20)
        window._table_item_map = {'000010': 10}
        window.main_splitter = SimpleNamespace(sizes=lambda: [100, 100, 100])
        window.filter_panel = object()
        window.load_history_filters = lambda: None
        window.update_stock_table = lambda *args, **kwargs: table_flushes.append(None)
        for _ in range(1000):
            window.request_table_update({'000010'})
        candle = namespace['CandlestickItem']()
        previous, hot_creations = None, 0
        for value in range(1024):
            pen, _ = candle._get_cached_pen_brush('#ff0000')
            hot_creations += pen is not previous
            previous = pen
            candle._get_cached_pen_brush(f'#{value:06x}')
        return {'filter_tasks_after_1000_requests': len(callbacks) + int(window._filter_refresh_timer.isActive()),
                'table_flushes_after_1000_requests': len(table_flushes),
                'hot_pen_creations_under_1024_cold_colors': hot_creations}
    finally:
        window._closing = True
        for timer in window.findChildren(namespace['QTimer']):
            timer.stop()
        window.deleteLater()
        namespace['time'], namespace['QtCore'] = saved_time, saved_qt


def main():
    parser = argparse.ArgumentParser()
    baseline_group = parser.add_mutually_exclusive_group()
    baseline_group.add_argument('--compare-head', action='store_true')
    baseline_group.add_argument('--compare-index', action='store_true', help='Compare the staged source before this review')
    parser.add_argument('--repeats', type=int, default=9)
    parser.add_argument('--output', type=Path, help='Save the benchmark report as UTF-8 JSON')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    current_source = (ROOT / 'trade_visualizer_qt6.py').read_text(encoding='utf-8-sig')
    current, current_image, current_namespace = benchmark(current_source, args.repeats)
    report = {'python': sys.version.split()[0], 'pyqtgraph': pg.__version__,
              'repeats': args.repeats, 'current': current}
    if args.compare_head or args.compare_index:
        git_root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=ROOT,
                                                text=True).strip())
        relative = (ROOT / 'trade_visualizer_qt6.py').relative_to(git_root).as_posix()
        baseline_ref = f'HEAD:{relative}' if args.compare_head else f':{relative}'
        baseline_source = subprocess.check_output(['git', 'show', baseline_ref], cwd=ROOT).decode('utf-8-sig')
        baseline, baseline_image, baseline_namespace = benchmark(baseline_source, args.repeats)
        report['baseline_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                                            text=True).strip()
        report['baseline_blob'] = subprocess.check_output(['git', 'rev-parse', baseline_ref], cwd=ROOT,
                                                          text=True).strip()
        report['baseline_head' if args.compare_head else 'baseline_index'] = baseline
        report['same_candle_pixels'] = baseline_image == current_image
        matches = []
        for theme in ('dark', 'light'):
            data = candle_data(4096)
            data[1::2, 2] = data[1::2, 1] - .1
            data[5::11, 2] = data[5::11, 1]
            colors = ['#00ffff' if i % 3 == 0 else None for i in range(len(data))]
            for colored in (False, True):
                old = baseline_namespace['CandlestickItem'](data, theme)
                new = current_namespace['CandlestickItem'](data, theme)
                if colored:
                    old.setData(data, colors)
                    new.setData(data, colors)
                matches.append(render_image(old) == render_image(new))
        report['same_theme_and_color_pixels'] = all(matches)
    formatted = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(formatted + '\n', encoding='utf-8')
    print(formatted)


if __name__ == '__main__':
    main()
