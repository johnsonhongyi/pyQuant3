"""Bounded production bridge probes; never submits a trading instruction."""
import argparse
import json
import math
import time
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', default='http://192.168.50.60:20073')
    parser.add_argument('--samples', type=int, default=1)
    parser.add_argument('--effort', default='low')
    parser.add_argument('--research-level', choices=['quantitative', 'quick', 'standard', 'deep'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.samples <= 31:
        parser.error('samples must be between 1 and 31')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, body=None, method=None):
        req = urllib.request.Request(args.backend + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'}, method=method)
        return opener.open(req, timeout=45)

    def get(path):
        with request(path) as response:
            return json.load(response)

    cfg = get('/api/v1/ai/runtime')['data']['config']
    report = {'started_unix': time.time(), 'configuration': cfg, 'samples': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    for index in range(args.samples):
        research = args.research_level
        if research:
            path = '/api/v1/stocks/research'
            body = {'symbol': '002307.SZ', 'purpose': 'observe', 'horizon': 'swing',
                'analysis_level': research, 'ai_provider': 'codex_desktop',
                'model': cfg['model'], 'reasoning_effort': args.effort,
                'desktop_node_id': cfg['node_id'], 'desktop_workspace_id': cfg['workspace_id']}
        else:
            path = '/api/v1/ai/desktop/jobs'
            body = {'bridge_test': True, 'node_id': cfg['node_id'],
                'workspace_id': cfg['workspace_id'], 'model': cfg['model'],
                'reasoning_effort': args.effort}
        started = time.monotonic()
        with request(path, body) as response:
            job = json.load(response)['data']
        sample = {'index': index, 'id': job['id'], 'request': body,
            'submit_ms': round((time.monotonic()-started)*1000, 3), 'events': []}
        report['samples'].append(sample)
        save()
        terminal = None
        event_path = path + '/' + job['id'] + '/events'
        with request(event_path) as response:
            if 'text/event-stream' not in response.headers.get('Content-Type', ''):
                raise RuntimeError('SSE was not negotiated')
            while time.monotonic()-started < (1200 if research else 180):
                line = response.readline(2*1024*1024+1)
                if not line:
                    break
                if len(line) > 2*1024*1024:
                    raise RuntimeError('SSE snapshot exceeds limit')
                if not line.startswith(b'data: '):
                    continue
                current = json.loads(line[6:])['data']
                elapsed = round((time.monotonic()-started)*1000, 3)
                result = current.get('result') or {}
                if result.get('content'):
                    sample.setdefault('visible_first_content_ms', elapsed)
                marker = {'status': current['status'], 'stage': current.get('stage'), 'elapsed_ms': elapsed}
                if not sample['events'] or marker['status'] != sample['events'][-1]['status'] or marker['stage'] != sample['events'][-1]['stage']:
                    sample['events'].append(marker)
                    print(json.dumps({'id': job['id'], **marker}), flush=True)
                    save()
                if current['status'] not in ('queued', 'running'):
                    terminal = current
                    break
        if terminal is None:
            raise RuntimeError('stream ended before terminal state')
        sample['total_ms'] = round((time.monotonic()-started)*1000, 3)
        sample['status'] = terminal['status']
        if research:
            analysis = terminal.get('analysis') or {}
            research_report = analysis.get('research_report') or {}
            sample.update({'ai': analysis.get('ai'), 'error': terminal.get('error'),
                'message': terminal.get('message'), 'attempts': research_report.get('attempts'),
                'validation': research_report.get('validation'),
                'data_quality': analysis.get('data_quality'),
                'benchmark_quality': analysis.get('benchmark_quality')})
        else:
            result = terminal.get('result') or {}
            sample.update({'marker_ok': result.get('content', '').strip() == 'CODEX_BRIDGE_OK',
                'timings': result.get('timings'), 'error': result.get('error')})
            with request(path+'/'+job['id'], method='DELETE') as response:
                json.load(response)
        save()
        print(json.dumps({k:v for k,v in sample.items() if k not in ('request','events')}, ensure_ascii=True), flush=True)
        if terminal['status'] != ('succeeded' if research else 'completed') or (not research and not sample['marker_ok']):
            break
    good = [s for s in report['samples'] if s.get('status') == ('succeeded' if args.research_level else 'completed')
        and (args.research_level or s.get('marker_ok'))]
    metrics = {}
    for key in ('total_ms', 'visible_first_content_ms'):
        values = sorted(s[key] for s in good if key in s)
        if values:
            metrics[key] = {f'p{p}': values[max(0, math.ceil(len(values)*p/100)-1)] for p in (50,95)}
    report['summary'] = {'count': len(report['samples']), 'successful': len(good), **metrics}
    save()
    print(json.dumps(report['summary']), flush=True)
    if len(good) != args.samples:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
