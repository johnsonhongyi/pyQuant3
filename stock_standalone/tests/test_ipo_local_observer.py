"""Local IPO commentary reads only a frozen observation and stays read-only."""

import hashlib
import json
import sqlite3

from ats.llm import ipo_local_observer as observer


def test_local_observer_uses_persisted_fields_only(tmp_path, monkeypatch):
    database = tmp_path / observer._DB
    database.parent.mkdir(parents=True)
    payload = json.dumps({
        "ticker": "301716", "cutoff": "2026-09-29T05:00:00+00:00",
        "fields": {"advance_decline_ratio": {"value": 0.5,
                                             "available_at": "2026-09-29T04:59:00+00:00"}},
    }, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE shadow_observations (observation_hash TEXT, payload_json TEXT, cutoff TEXT)"
        )
        connection.execute("INSERT INTO shadow_observations VALUES (?, ?, ?)",
                           (digest, payload, "2026-09-29T05:00:00+00:00"))
    sent = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({"response": "数据不足，无法判断。", "done": True,
                               "done_reason": "stop"}).encode()

    monkeypatch.setattr(observer, "_ensure_local_model", lambda _model: True)

    def fake_urlopen(request, timeout):
        sent.append((request.full_url, json.loads(request.data), timeout))
        return Response()

    monkeypatch.setattr(observer.urllib.request, "urlopen", fake_urlopen)
    result = observer.analyze_latest_observation(tmp_path)
    assert result["state"] == "INSUFFICIENT_DATA"
    assert result["model_executed"] is True
    assert result["order_submitted"] is False
    assert sent[0][0] == "http://127.0.0.1:11434/api/generate"
    assert "advance_decline_ratio" in sent[0][1]["prompt"]
    assert "买卖" in sent[0][1]["prompt"]
