"""Keep next-day JSON parsing, persistence and TDX waits out of the GUI process."""
import atexit
import logging
import multiprocessing
import os
import threading
import time

logger = logging.getLogger("ATS.NextDayWatch")
_imported_manifests = {}


def compact_sector_snapshot(snapshot):
    """Transport resonance metrics and member codes, without nested quote histories."""
    if not isinstance(snapshot, dict):
        return None
    fields = {'score', 'momentum_score', 'avg_pct', 'avg_pct_diff', 'pct_diff',
        'follow_ratio', 'leader', 'leader_name', 'leader_pct', 'leader_pct_diff',
        'score_diff', 'ts'}
    result = {}
    for name, info in snapshot.items():
        if not isinstance(info, dict):
            continue
        board = {key: value for key, value in info.items()
                 if key in fields and isinstance(value, (str, int, float, bool, type(None)))}
        for key in ('followers', 'race_candidates'):
            members = info.get(key, [])
            if isinstance(members, list):
                board[key] = [member.get('code', '') if isinstance(member, dict) else member
                              for member in members if isinstance(member, (dict, str, int))]
        result[name] = board
    return result


def _accept_manifest(root, manifest):
    if not isinstance(manifest, dict):
        return
    day = str(manifest.get('target_trade_date', ''))
    from datetime import date
    try:
        date.fromisoformat(day)
    except ValueError:
        return
    key = (root, day)
    seen = _imported_manifests.setdefault(key, [])
    if any(previous == manifest for previous in seen):
        return
    from next_day_anomaly_watch import _atomic_json, _read_json
    import copy
    path = os.path.join(root, 'datacsv', 'next_day_anomaly_watch_%s.json' % day)
    current = _read_json(path, {})
    seen.append(copy.deepcopy(manifest))
    del seen[:-8]
    if len(_imported_manifests) > 8:
        _imported_manifests.pop(next(iter(_imported_manifests)))
    if str(current.get('generated_at', '')) > str(manifest.get('generated_at', '')):
        return
    _atomic_json(path, manifest)


def _snapshot(root, target_date=None, eval_only=False, manifest=None, sector_snapshot=None):
    """Return live worker memory; persistence is independent of UI refresh."""
    _accept_manifest(root, manifest)
    from ats.bounded_evaluation_store import evaluation_store
    from next_day_anomaly_watch import _read_json
    data_dir = os.path.join(root, 'datacsv')
    paths = evaluation_store.paths(os.path.join(data_dir, 'next_day_anomaly_watch_*.json'))
    dates = sorted((os.path.basename(path)[23:-5] for path in paths), reverse=True)
    day = target_date or (dates[0] if dates else time.strftime('%Y-%m-%d'))
    from datetime import date
    date.fromisoformat(day)
    result = {'target_date': day, 'eval_only': bool(eval_only),
              'eval': _read_json(os.path.join(data_dir, 'next_day_anomaly_eval_%s.json' % day), {})}
    from next_day_anomaly_watch import get_live_watch_quotes, enrich_manifest_sector_evidence
    quotes = get_live_watch_quotes(data_dir, day)
    if quotes:
        result['eval']['quotes'] = quotes
    if eval_only:
        return result
    result.update(dates=dates, manifest=_read_json(
        os.path.join(data_dir, 'next_day_anomaly_watch_%s.json' % day), {}))
    enrich_manifest_sector_evidence(result['manifest'], result['eval'], sector_snapshot)
    stats, delayed_winners = [], []
    for path in sorted(evaluation_store.paths(
            os.path.join(data_dir, 'next_day_anomaly_stats_*.json')), reverse=True)[:30]:
        item = _read_json(path, {})
        if not item:
            continue
        stats.append(item)
        target = item.get('target_trade_date', '')
        try:
            date.fromisoformat(target)
        except (ValueError, TypeError):
            continue
        evaluation = _read_json(os.path.join(data_dir, 'next_day_anomaly_eval_%s.json' % target), {})
        for entry in evaluation.get('candidates', {}).values():
            candidate = entry.get('candidate', {})
            if candidate.get('status') == 'DELAYED' or any(
                    event.get('type') == 'DELAYED' for event in entry.get('events', [])):
                delayed_winners.append((candidate, target))
    result.update(stats=stats, delayed_winners=delayed_winners)
    return result


def _poll(root, manifest=None, sector_snapshot=None):
    now = time.localtime()
    today = time.strftime("%Y-%m-%d", now)
    try:
        from sys_utils import get_app_root
        from next_day_anomaly_watch import (_pending_confirmation_events, _read_json,
            get_followup_candidates)
        # The parent supplies the physical deployment directory.
        data_dir = os.path.join(root, "datacsv")
        if isinstance(manifest, dict) and manifest.get('target_trade_date') == today:
            _accept_manifest(root, manifest)
        pending_events = _pending_confirmation_events(
            data_dir, today, _read_json(os.path.join(data_dir, "next_day_anomaly_eval_%s.json" % today), {}))
    except Exception as exc:
        logger.debug("[NextDayWatch][ATS_TDX] manifest check skipped: %s", exc)
        return {"events": []}

    candidates, followup_candidates, watch = [], [], {}
    can_evaluate = (now.tm_wday < 5 and
        93000 <= now.tm_hour * 10000 + now.tm_min * 100 + now.tm_sec <= 150500)
    if can_evaluate:
        from ats.tdx_realtime_fetcher import TDXGlobalCachePool
        can_evaluate = TDXGlobalCachePool.is_trading_day(today)
    if can_evaluate:
        try:
            from sys_utils import get_conf_path
            from ats.strategy.next_day_watch_config_manager import NextDayWatchConfigManager
            config_path = get_conf_path("next_day_watch_strategies.json", root)
            _, config, _ = NextDayWatchConfigManager.load_config(config_path)
            if config.get("enabled"):
                watch = _read_json(os.path.join(data_dir, "next_day_anomaly_watch_%s.json" % today), {})
                candidates = watch.get("candidates", [])
                followup_candidates = get_followup_candidates(data_dir, today)
        except Exception as exc:
            logger.debug("[NextDayWatch][ATS_TDX] evaluation config unavailable: %s", exc)
    if not candidates and not followup_candidates and not pending_events:
        return {"events": []}

    all_candidates = candidates + followup_candidates
    meta = {str(item.get("code", "")).zfill(6): item for item in all_candidates if item.get("code")}
    codes = sorted(meta)
    quote_count = 0
    quote_gap_count = 0
    if codes:
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
        fetcher = TDXRealtimeFetcher.get_instance()
        quotes = fetcher.get_security_quotes_safe(codes, force=False)
        quote_count = len(quotes) if quotes is not None else 0
        frame = fetcher.convert_quotes_to_df(quotes)
        import pandas as pd
        if frame is None:
            frame = pd.DataFrame()
        frame_codes = {str(code).strip().zfill(6) for code in frame.index}
        quote_gap_count = len(set(codes) - frame_codes)
        endpoint = getattr(fetcher, "current_host", None) or ("TDX", "?", "?")
        for code in frame.index:
            candidate = meta.get(str(code).zfill(6), {})
            frame.loc[code, "name"] = candidate.get("name", str(code))
            frame.loc[code, "category"] = candidate.get('raw_category') or candidate.get("category", "")
        frame["percent"] = frame.get("change_pct")
        from datetime import datetime
        observed_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
        from next_day_anomaly_watch import run_cycle
        result = run_cycle(frame, config_path=config_path, data_dir=data_dir,
            asof_date=str(watch.get("source_asof_trade_date", today)), target_date=today,
            observed_at=observed_at, vwap_field="vwap", sector_snapshot=sector_snapshot)
        events_to_dispatch = result.get("events", [])
    else:
        endpoint = ("OUTBOX", "local", "")
        events_to_dispatch = pending_events
    return {"events": events_to_dispatch, "endpoint": endpoint,
            "candidate_count": len(codes), "quote_count": quote_count,
            "quote_gap_count": quote_gap_count}


def _worker_entry(connection, root):
    try:
        while True:
            request = connection.recv()
            if request is None:
                break
            try:
                if request["action"] == "poll":
                    result = _poll(root, request.get('manifest'), request.get('sector_snapshot'))
                elif request['action'] == 'snapshot':
                    result = _snapshot(root, request.get('target_date'),
                                       request.get('eval_only', False), request.get('manifest'),
                                       request.get('sector_snapshot'))
                elif request["action"] == "ack":
                    from next_day_anomaly_watch import mark_events_delivered
                    result = {"acknowledged": mark_events_delivered(
                        os.path.join(root, "datacsv"), request["target_date"], request["event_ids"])}
                else:
                    result = {"pid": os.getpid()}
                connection.send(result)
            except Exception as exc:
                connection.send({"events": [], "error": str(exc)})
    except (EOFError, OSError):
        pass
    finally:
        try:
            from next_day_anomaly_watch import flush_pending_evaluations
            flush_pending_evaluations()
        except Exception:
            logger.exception("Next-day final persistence failed")
        connection.close()


class NextDayWatchProcess:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._process = None
        self._connection = None
        atexit.register(self.close)

    def request(self, action, timeout=120.0, **payload):
        # Called only by background threads; at most one request can be in flight.
        with self._lock:
            if self._closed.is_set():
                return {"events": [], "error": "worker_closed"}
            try:
                if self._process is None or not self._process.is_alive():
                    if self._connection is not None:
                        self._connection.close()
                    if self._process is not None:
                        self._process.join(0)
                        self._process.close()
                    context = multiprocessing.get_context("spawn")
                    parent, child = context.Pipe()
                    process = context.Process(target=_worker_entry, args=(child, self.root),
                                              name="ATS-NextDayWatch", daemon=True)
                    try:
                        process.start()
                    except Exception:
                        parent.close()
                        child.close()
                        raise
                    child.close()
                    self._connection, self._process = parent, process
                if 'sector_snapshot' in payload:
                    payload['sector_snapshot'] = compact_sector_snapshot(payload['sector_snapshot'])
                self._connection.send(dict(payload, action=action))
                deadline = time.monotonic() + timeout
                while not self._closed.is_set():
                    if self._connection.poll(min(0.25, max(0.0, deadline - time.monotonic()))):
                        return self._connection.recv()
                    if not self._process.is_alive():
                        raise RuntimeError("next-day worker exited")
                    if time.monotonic() >= deadline:
                        self._process.terminate()
                        self._process.join(1)
                        raise TimeoutError("next-day worker timeout")
                return {"events": [], "error": "worker_closed"}
            except Exception as exc:
                return {"events": [], "error": str(exc)}

    def close(self):
        self._closed.set()
        with self._lock:
            if self._process is None:
                return
            try:
                if self._process.is_alive():
                    self._connection.send(None)
                    self._process.join(5)
                if self._process.is_alive():
                    self._process.terminate()
                    self._process.join(1)
                if not self._process.is_alive():
                    self._process.close()
                    self._process = None
            except (OSError, ValueError):
                pass
            finally:
                if self._connection is not None:
                    self._connection.close()
                    self._connection = None
