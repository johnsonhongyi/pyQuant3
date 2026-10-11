import configparser
import json
import hashlib
import hmac
import http.client
import socket
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import system_linkage_gateway
from system_linkage_gateway import SystemLinkageGateway


def test_custom_bind_ip_accepts_a_local_private_interface():
    config = SimpleNamespace(
        ipc_bind_host="192.168.31.42",
        stock_strategy_base_url="http://10.20.0.8:20081",
    )

    assert system_linkage_gateway._resolve_bind_host(config) == "192.168.31.42"


def test_auto_lan_binding_uses_the_route_selected_local_interface(monkeypatch):
    class RouteSocket:
        destination = None

        def connect(self, address):
            self.destination = address

        def getsockname(self):
            return "192.168.31.42", 51234

        def close(self):
            pass

    route = RouteSocket()
    monkeypatch.setattr(
        system_linkage_gateway.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("10.20.0.8", 20081))],
    )
    monkeypatch.setattr(system_linkage_gateway.socket, "socket", lambda *args, **kwargs: route)
    config = SimpleNamespace(
        ipc_bind_host="auto_lan",
        stock_strategy_base_url="http://stock-strategy.local:20081",
    )

    assert system_linkage_gateway._resolve_bind_host(config) == "192.168.31.42"
    assert route.destination == ("10.20.0.8", 20081)


def test_auto_lan_binding_uses_a_private_interface_before_backend_setup(monkeypatch):
    monkeypatch.setattr(
        system_linkage_gateway.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("192.168.31.42", 0))],
    )
    assert system_linkage_gateway._resolve_bind_host(SimpleNamespace(
        ipc_bind_host="auto_lan", stock_strategy_base_url="",
    )) == "192.168.31.42"


def test_ensure_linkage_config_persists_identity_key_and_private_peer_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(system_linkage_gateway, "get_base_path", lambda: str(tmp_path / "empty_bundle"))
    monkeypatch.setattr(system_linkage_gateway, "get_conf_path", lambda *args, **kwargs: None)
    config_path = tmp_path / "global.ini"
    config_path.write_text("[general]\nlinkage_enabled = True\n", encoding="utf-8")
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")
    config_store = SimpleNamespace(cfg=parser, cfg_file=str(config_path))
    config = SimpleNamespace(
        CFG=config_store, conf_ini=str(config_path), linkage_enabled=True,
        ipc_node_id="", ipc_workspace_id="", ipc_key_file="", ipc_peer_allowlist=[],
        ipc_bind_host="auto_lan", ipc_advertise_host="auto", ipc_linkage_port=26676,
    )

    first = system_linkage_gateway.ensure_linkage_config(config)
    second = system_linkage_gateway.ensure_linkage_config(config)
    saved = configparser.ConfigParser()
    saved.read(config_path, encoding="utf-8")

    assert first["node_id"].startswith("tk-")
    assert first["workspace_id"].startswith("ws-")
    assert second["node_id"] == first["node_id"]
    assert second["workspace_id"] == first["workspace_id"]
    assert len(first["key"]) == 32
    assert saved.get("general", "ipc_node_id") == first["node_id"]
    assert saved.get("general", "ipc_workspace_id") == first["workspace_id"]
    assert saved.get("general", "ipc_peer_allowlist") == "['auto_private']"
    assert saved.get("general", "ipc_key_file") == "system_linkage.key"
    assert first["key_file"] == str(tmp_path / "system_linkage.key")


def test_ensure_linkage_config_releases_packaged_key_before_generating(tmp_path, monkeypatch):
    config_path = tmp_path / "global.ini"
    config_path.write_text("[general]\n", encoding="utf-8")
    packaged_key = b"b" * 32
    package_dir = tmp_path / "bundle"
    package_dir.mkdir()
    (package_dir / "system_linkage.key").write_bytes(packaged_key)
    released_targets = []

    def release_key(name, base_dir):
        assert name == "system_linkage.key"
        target = tmp_path / "system_linkage.key"
        target.write_bytes(packaged_key)
        released_targets.append(target)
        return str(target)

    monkeypatch.setattr(system_linkage_gateway, "get_conf_path", release_key)
    monkeypatch.setattr(system_linkage_gateway, "get_base_path", lambda: str(package_dir))
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")
    config_store = SimpleNamespace(cfg=parser, cfg_file=str(config_path))
    config = SimpleNamespace(
        CFG=config_store, conf_ini=str(config_path), linkage_enabled=True,
        ipc_node_id="tk-existing", ipc_workspace_id="ws-existing", ipc_key_file="",
        ipc_peer_allowlist=["auto_private"], ipc_bind_host="auto_lan",
        ipc_advertise_host="auto", ipc_linkage_port=26676,
    )

    registration = system_linkage_gateway.ensure_linkage_config(config)

    assert released_targets == [tmp_path / "system_linkage.key"]
    assert registration["key"] == packaged_key
    assert (tmp_path / "system_linkage.key").read_bytes() == packaged_key


def test_ensure_linkage_config_migrates_an_absolute_key_path(tmp_path):
    config_path = tmp_path / "release" / "global.ini"
    config_path.parent.mkdir()
    config_path.write_text("[general]\n", encoding="utf-8")
    old_key_path = tmp_path / "development" / "system_linkage.key"
    old_key_path.parent.mkdir()
    old_key_path.write_text("a" * 64 + "\n", encoding="ascii")
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")
    config_store = SimpleNamespace(cfg=parser, cfg_file=str(config_path))
    config = SimpleNamespace(
        CFG=config_store, conf_ini=str(config_path), linkage_enabled=True,
        ipc_node_id="tk-existing", ipc_workspace_id="ws-existing",
        ipc_key_file=str(old_key_path), ipc_peer_allowlist=["auto_private"],
        ipc_bind_host="auto_lan", ipc_advertise_host="auto", ipc_linkage_port=26676,
    )

    registration = system_linkage_gateway.ensure_linkage_config(config)
    saved = configparser.ConfigParser()
    saved.read(config_path, encoding="utf-8")

    assert saved.get("general", "ipc_key_file") == "system_linkage.key"
    assert registration["key_file"] == str(config_path.parent / "system_linkage.key")
    assert (config_path.parent / "system_linkage.key").read_bytes() == old_key_path.read_bytes()


def test_ensure_linkage_config_preserves_existing_identity_and_repairs_blank_allowlist(tmp_path):
    config_path = tmp_path / "global.ini"
    config_path.write_text("[general]\n", encoding="utf-8")
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")
    key_path = tmp_path / "linkage.key"
    key_path.write_bytes(b"k" * 32)
    config_store = SimpleNamespace(cfg=parser, cfg_file=str(config_path))
    config = SimpleNamespace(
        CFG=config_store, conf_ini=str(config_path), linkage_enabled=True,
        ipc_node_id="tk-existing", ipc_workspace_id="", ipc_key_file=str(key_path),
        ipc_peer_allowlist=[""], ipc_bind_host="auto_lan",
        ipc_advertise_host="auto", ipc_linkage_port=26676,
    )

    registration = system_linkage_gateway.ensure_linkage_config(config)
    saved = configparser.ConfigParser()
    saved.read(config_path, encoding="utf-8")

    assert registration["node_id"] == "tk-existing"
    assert registration["workspace_id"].startswith("ws-")
    assert config.ipc_peer_allowlist == ["auto_private"]
    assert saved.get("general", "ipc_peer_allowlist") == "['auto_private']"


def test_gateway_confirms_symbols_from_local_security_directory(tmp_path, monkeypatch):
    app_root = tmp_path / "app"
    catalog = app_root / "JSONData" / "stock_codes.conf"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({"stock": ["600000"]}), encoding="utf-8")
    monkeypatch.setattr(system_linkage_gateway, "get_app_root", lambda: str(app_root))
    gateway = SystemLinkageGateway(
        SimpleNamespace(ipc_node_id="tk-1", ipc_workspace_id="desk"),
        database_path=str(tmp_path / "gateway.sqlite3"),
    )
    now = datetime.now(timezone.utc)
    command = {
        "schema_version": 1, "type": "WATCHLIST_ADD", "request_id": "catalog-req",
        "operation_id": "catalog-op", "workspace_id": "desk", "target_node_ids": ["tk-1"],
        "symbol": "600000.SH", "instrument_type": "stock", "source": "stock-strategy.sbc",
        "reason": "catalog check", "context_refs": [],
        "created_at": now.isoformat(), "expires_at": (now + timedelta(minutes=2)).isoformat(),
    }

    assert gateway.validate_command(command)["code"] == "600000"
    command["symbol"] = "600001.SH"
    with pytest.raises(ValueError, match="unknown_security"):
        gateway.validate_command(command)


def test_gateway_fails_closed_when_security_directory_is_unavailable(tmp_path, monkeypatch):
    import sys_utils

    monkeypatch.setattr(sys_utils, "get_base_path", lambda: str(tmp_path / "missing_bundle"))
    monkeypatch.setattr(system_linkage_gateway, "get_app_root", lambda: str(tmp_path))
    gateway = SystemLinkageGateway(
        SimpleNamespace(ipc_node_id="tk-1", ipc_workspace_id="desk"),
        database_path=str(tmp_path / "gateway.sqlite3"),
    )
    now = datetime.now(timezone.utc)
    command = {
        "schema_version": 1, "type": "WATCHLIST_ADD", "request_id": "missing-req",
        "operation_id": "missing-op", "workspace_id": "desk", "target_node_ids": ["tk-1"],
        "symbol": "600000.SH", "instrument_type": "stock", "source": "stock-strategy.sbc",
        "reason": "catalog unavailable", "context_refs": [],
        "created_at": now.isoformat(), "expires_at": (now + timedelta(minutes=2)).isoformat(),
    }

    with pytest.raises(ValueError, match="security_directory_unavailable"):
        gateway.validate_command(command)


def test_http_gateway_verifies_hmac_and_rejects_nonce_replay(tmp_path):
    key = b"k" * 32
    key_path = tmp_path / "peer.key"
    key_path.write_bytes(key)
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    class Manager:
        def list_linkage_operations(self):
            return {}

        def ensure_linkage_favorite(self, code, operation_id, metadata):
            return {"status": "applied", "persisted": True, "favorites_revision": 1}

    config = SimpleNamespace(
        linkage_enabled=True, ipc_node_id="tk-1", ipc_workspace_id="desk",
        ipc_peer_allowlist=["127.0.0.1"], ipc_linkage_port=port,
        ipc_bind_host="127.0.0.1", ipc_advertise_host="127.0.0.1",
        ipc_key_file=str(key_path),
    )
    gateway = SystemLinkageGateway(
        config, manager_factory=Manager,
        database_path=str(tmp_path / "gateway.sqlite3"),
    )
    gateway.start()
    try:
        now = datetime.now(timezone.utc)
        command = {
            "schema_version": 1, "type": "WATCHLIST_ADD", "request_id": "http-req-1",
            "operation_id": "http-op-1", "workspace_id": "desk", "target_node_ids": ["tk-1"],
            "symbol": "000001.SZ", "instrument_type": "stock", "source": "stock-strategy.sbc",
            "reason": "security regression", "context_refs": [],
            "created_at": now.isoformat(), "expires_at": (now + timedelta(minutes=2)).isoformat(),
        }
        body = json.dumps(command, separators=(",", ":")).encode("utf-8")
        path = "/bridge/v1/commands"
        timestamp = str(int(time.time()))
        nonce = "nonce-http-abcdefghijklmnop"
        canonical = "\n".join(("POST", path, hashlib.sha256(body).hexdigest(), timestamp,
                                nonce, "tk-1", "desk")).encode("utf-8")
        signature = hmac.new(key, canonical, hashlib.sha256).hexdigest()

        def post(request_nonce, request_signature):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            connection.request("POST", path, body=body, headers={
                "Content-Type": "application/json", "Content-Length": str(len(body)),
                "X-Linkage-Node-ID": "tk-1", "X-Linkage-Workspace-ID": "desk",
                "X-Linkage-Timestamp": timestamp, "X-Linkage-Nonce": request_nonce,
                "X-Linkage-Signature": request_signature,
            })
            response = connection.getresponse()
            response_body = response.read()
            connection.close()
            return response.status, json.loads(response_body.decode("utf-8"))

        accepted_status, accepted = post(nonce, signature)
        replay_status, _ = post(nonce, signature)
        bad_signature_status, _ = post("nonce-http-bad-signature", "0" * 64)

        assert accepted_status == 202
        assert accepted["operation_id"] == "http-op-1"
        assert replay_status == 401
        assert bad_signature_status == 401
        with gateway._db() as connection:
            assert connection.execute("SELECT COUNT(*) FROM linkage_operations").fetchone()[0] == 1
    finally:
        gateway.stop()


def test_http_gateway_accepts_authenticated_client_configuration(tmp_path):
    key = b"c" * 32
    key_path = tmp_path / "peer.key"
    key_path.write_text(key.hex(), encoding="ascii")
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    config = SimpleNamespace(
        linkage_enabled=True, ipc_node_id="tk-setup", ipc_workspace_id="ws-setup",
        ipc_peer_allowlist=["auto_private"], ipc_linkage_port=port,
        ipc_bind_host="127.0.0.1", ipc_advertise_host="127.0.0.1",
        ipc_key_file=str(key_path), stock_strategy_base_url="",
    )
    gateway = SystemLinkageGateway(config, database_path=str(tmp_path / "gateway.sqlite3"))
    gateway.start()
    try:
        path = "/bridge/v1/configure"
        body = json.dumps({
            "schema_version": 1, "stock_strategy_base_url": "http://192.168.31.5:20081",
        }, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        nonce = "nonce-setup-abcdefghijklmnop"
        canonical = "\n".join(("POST", path, hashlib.sha256(body).hexdigest(), timestamp,
                                nonce, "tk-setup", "ws-setup")).encode("utf-8")
        signature = hmac.new(key, canonical, hashlib.sha256).hexdigest()
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        connection.request("POST", path, body=body, headers={
            "Content-Type": "application/json", "Content-Length": str(len(body)),
            "X-Linkage-Node-ID": "tk-setup", "X-Linkage-Workspace-ID": "ws-setup",
            "X-Linkage-Timestamp": timestamp, "X-Linkage-Nonce": nonce,
            "X-Linkage-Signature": signature,
        })
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()

        assert response.status == 200
        assert payload["connection_test"] == "hmac_verified"
        assert config.stock_strategy_base_url == "http://192.168.31.5:20081"
        assert config.ipc_peer_allowlist == ["auto_private"]
    finally:
        gateway.stop()


def test_gateway_releases_slots_after_idle_clients_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(system_linkage_gateway, "_CLIENT_READ_TIMEOUT_SEC", 0.1)
    key_path = tmp_path / "peer.key"
    key_path.write_bytes(b"k" * 32)
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    config = SimpleNamespace(
        linkage_enabled=True, ipc_node_id="tk-timeout", ipc_workspace_id="desk",
        ipc_peer_allowlist=["127.0.0.1"], ipc_linkage_port=port,
        ipc_bind_host="127.0.0.1", ipc_advertise_host="127.0.0.1",
        ipc_key_file=str(key_path),
    )
    gateway = SystemLinkageGateway(
        config, database_path=str(tmp_path / "gateway.sqlite3"),
    )
    gateway.start()
    idle_clients = []
    try:
        for _ in range(8):
            client = socket.create_connection(("127.0.0.1", port), timeout=1)
            client.settimeout(1)
            idle_clients.append(client)

        deadline = time.monotonic() + 2
        while gateway._server._client_slots._value != 8 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert gateway._server._client_slots._value == 8

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("GET", "/bridge/v1/health")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read().decode("utf-8"))["status"] == "ok"
        connection.close()
    finally:
        for client in idle_clients:
            client.close()
        gateway.stop()


def test_desktop_inbox_acceptance_is_idempotent_and_rejects_operation_reuse(tmp_path):
    gateway = SystemLinkageGateway(
        SimpleNamespace(ipc_node_id="tk-1", ipc_workspace_id="desk", ipc_linkage_port=26676),
        database_path=str(tmp_path / "gateway.sqlite3"),
    )
    command = {
        "operation_id": "op-idempotent", "request_id": "req-idempotent", "symbol": "600000.SH",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
    }

    status, first = gateway.accept_command(command, "stable-body-hash")
    replay_status, replay = gateway.accept_command(command, "stable-body-hash")

    assert status == replay_status == 202
    assert first["status"] == replay["status"] == "accepted"
    assert first["operation_id"] == replay["operation_id"] == "op-idempotent"
    try:
        gateway.accept_command(command, "changed-body-hash")
    except ValueError as error:
        assert str(error) == "operation_id_conflict"
    else:
        raise AssertionError("reused operation id with a different body was accepted")


def test_desktop_inbox_queue_capacity_is_bounded(tmp_path):
    gateway = SystemLinkageGateway(
        SimpleNamespace(ipc_node_id="tk-1", ipc_workspace_id="desk", ipc_linkage_port=26676),
        database_path=str(tmp_path / "gateway.sqlite3"),
    )
    created_at = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    for index in range(128):
        status, _ = gateway.accept_command(
            {
                "operation_id": f"op-{index}", "request_id": f"req-{index}",
                "created_at": created_at, "expires_at": expires_at,
            }, f"body-{index}"
        )
        assert status == 202

    status, result = gateway.accept_command(
        {
            "operation_id": "op-overflow", "request_id": "req-overflow",
            "created_at": created_at, "expires_at": expires_at,
        }, "body-overflow"
    )
    assert status == 429
    assert result["code"] == "queue_full"
    with gateway._db() as connection:
        assert connection.execute("SELECT COUNT(*) FROM linkage_operations").fetchone()[0] == 128


def test_favorite_write_failure_is_durably_retried(tmp_path):
    calls = []

    def manager_factory():
        class Manager:
            def ensure_linkage_favorite(self, code, operation_id, metadata):
                calls.append(operation_id)
                if len(calls) == 1:
                    raise OSError("temporary favorite file lock")
                return {"status": "applied", "persisted": True, "favorites_revision": 4}

        return Manager()

    gateway = SystemLinkageGateway(
        SimpleNamespace(ipc_node_id="tk-1", ipc_workspace_id="desk", ipc_linkage_port=26676),
        manager_factory=manager_factory,
        database_path=str(tmp_path / "gateway.sqlite3"),
    )
    command = {
        "operation_id": "op-1", "request_id": "req-1", "code": "600000",
        "source": "stock-strategy.sbc", "reason": "test", "context_refs": [],
        "observed_trade_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
    }
    gateway.accept_command(command, "body-hash")

    gateway._apply_operation("op-1", json.dumps(command), command["expires_at"])
    with gateway._db() as connection:
        retry = connection.execute(
            "SELECT status,attempts,next_attempt,result FROM linkage_operations WHERE operation_id='op-1'"
        ).fetchone()
        connection.execute("UPDATE linkage_operations SET next_attempt=0 WHERE operation_id='op-1'")
    assert retry["status"] == "retry"
    assert retry["attempts"] == 1
    assert retry["next_attempt"] > time.time()
    assert json.loads(retry["result"])["retryable"] is True

    gateway._apply_operation("op-1", json.dumps(command), command["expires_at"])
    result = gateway.get_operation("op-1")
    assert result["status"] == "applied"
    assert result["result"]["saved"]["persisted"] is True
    assert calls == ["op-1", "op-1"]


def test_expired_command_recovers_a_favorite_saved_before_process_exit(tmp_path):
    calls = []

    def manager_factory():
        class Manager:
            def list_linkage_operations(self):
                return {"op-expired": {"code": "600000", "action": "add"}}

            def ensure_linkage_favorite(self, code, operation_id, metadata):
                calls.append(operation_id)
                return {"status": "already_present", "already_applied": True,
                        "persisted": True, "favorites_revision": 5}

        return Manager()

    gateway = SystemLinkageGateway(
        SimpleNamespace(ipc_node_id="tk-1", ipc_workspace_id="desk", ipc_linkage_port=26676),
        manager_factory=manager_factory,
        database_path=str(tmp_path / "gateway.sqlite3"),
    )
    command = {
        "operation_id": "op-expired", "request_id": "req-expired", "code": "600000",
        "source": "stock-strategy.sbc", "reason": "test", "context_refs": [],
        "observed_trade_date": None,
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
    }
    gateway.accept_command(command, "expired-body-hash")

    gateway._apply_operation("op-expired", json.dumps(command), command["expires_at"])

    result = gateway.get_operation("op-expired")
    assert result["status"] == "already_present"
    assert result["result"]["saved"]["persisted"] is True
    assert calls == ["op-expired"]

@pytest.mark.parametrize("mode", ["development", "nuitka", "pyinstaller"])
def test_security_directory_uses_shared_resolver_and_reloads_updates(tmp_path, monkeypatch, mode):
    import os
    import sys_utils

    app = tmp_path / "app"
    bundle = tmp_path / "bundle"
    app.mkdir()
    bundle.mkdir()
    monkeypatch.setattr(sys_utils, "get_base_path", lambda: str(bundle))
    monkeypatch.setattr(sys_utils, "is_packaged_env", lambda: mode != "development")
    monkeypatch.setattr(system_linkage_gateway, "get_app_root", lambda: str(app))
    monkeypatch.setattr(system_linkage_gateway, "_SECURITY_DIRECTORY_CACHE", {})
    monkeypatch.delenv("NUITKA_ONEFILE_DIRECTORY", raising=False)
    monkeypatch.delattr(sys_utils.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys_utils.sys, "frozen", mode == "pyinstaller", raising=False)
    if mode == "nuitka":
        monkeypatch.setenv("NUITKA_ONEFILE_DIRECTORY", str(bundle))
    elif mode == "pyinstaller":
        monkeypatch.setattr(sys_utils.sys, "_MEIPASS", str(bundle), raising=False)

    catalog = app / ("JSONData/stock_codes.conf" if mode == "development" else "stock_codes.conf")
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(json.dumps({"stock": ["600000"]}), encoding="utf-8")
    if mode != "development":
        # A bundled/development copy must not shadow the updated runtime catalog.
        stale = app / "JSONData" / "stock_codes.conf"
        stale.parent.mkdir()
        stale.write_text(json.dumps({"stock": ["600099"]}), encoding="utf-8")
    assert system_linkage_gateway._load_security_directory() == frozenset({"600000"})
    assert os.path.normpath(sys_utils.get_conf_path("stock_codes.conf", base_dir=str(app))) == str(catalog)

    old_mtime = catalog.stat().st_mtime_ns
    replacement = catalog.with_suffix(".tmp")
    replacement.write_text(json.dumps({"stock": ["600001"]}), encoding="utf-8")
    replacement.replace(catalog)
    os.utime(catalog, ns=(old_mtime + 1_000_000_000, old_mtime + 1_000_000_000))
    assert system_linkage_gateway._load_security_directory() == frozenset({"600001"})
    catalog.write_text('{"stock": []}', encoding="utf-8")
    assert system_linkage_gateway._load_security_directory() is None


@pytest.mark.parametrize("mode", ["development", "nuitka", "pyinstaller"])
def test_security_directory_releases_missing_resource_through_shared_resolver(tmp_path, monkeypatch, mode):
    import sys_utils

    app = tmp_path / "app"
    bundle = tmp_path / "bundle"
    app.mkdir()
    resource = bundle / "JSONData" / "stock_codes.conf"
    resource.parent.mkdir(parents=True)
    resource.write_text(json.dumps({"stock": ["600000"]}), encoding="utf-8")
    monkeypatch.setattr(sys_utils, "get_base_path", lambda: str(bundle))
    monkeypatch.setattr(sys_utils, "is_packaged_env", lambda: mode != "development")
    monkeypatch.setattr(system_linkage_gateway, "get_app_root", lambda: str(app))
    monkeypatch.setattr(system_linkage_gateway, "_SECURITY_DIRECTORY_CACHE", {})
    monkeypatch.delenv("NUITKA_ONEFILE_DIRECTORY", raising=False)
    monkeypatch.delattr(sys_utils.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys_utils.sys, "frozen", mode == "pyinstaller", raising=False)
    if mode == "nuitka":
        monkeypatch.setenv("NUITKA_ONEFILE_DIRECTORY", str(bundle))
    elif mode == "pyinstaller":
        monkeypatch.setattr(sys_utils.sys, "_MEIPASS", str(bundle), raising=False)
    assert system_linkage_gateway._load_security_directory() == frozenset({"600000"})
    catalog = app / ("JSONData/stock_codes.conf" if mode == "development" else "stock_codes.conf")
    assert catalog.read_bytes() == resource.read_bytes()
    if mode != "development":
        assert not (app / "JSONData").exists()


def _seed_consumer_operation(gateway):
    with gateway._db() as connection:
        connection.execute(
            "INSERT INTO linkage_operations(operation_id,request_id,body_hash,payload,status,result,created_at,expires_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("ack-op", "ack-req", "hash", "{}", "applied", json.dumps({
                "saved": {"persisted": True, "favorites_revision": 1},
                "consumers": {"TK": {"status": "pending"}, "ATS": {"status": "pending"}},
            }), "now", "later", "now"),
        )


def test_concurrent_consumer_acks_preserve_both_results(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    gateway = SystemLinkageGateway(SimpleNamespace(), database_path=str(tmp_path / "ack.sqlite3"))
    _seed_consumer_operation(gateway)
    first_read, release, second_done = threading.Event(), threading.Event(), threading.Event()
    original = gateway._connect
    class PausedConnection:
        def __init__(self, connection):
            self.connection = connection
        def execute(self, sql, *args):
            cursor = self.connection.execute(sql, *args)
            if sql.startswith("SELECT result FROM") and threading.current_thread().name.endswith("_0"):
                first_read.set()
                assert release.wait(3)
            return cursor
        def __getattr__(self, name):
            return getattr(self.connection, name)
    monkeypatch.setattr(gateway, "_connect", lambda: PausedConnection(original()))
    def second_ack():
        try:
            return gateway.report_consumer("ack-op", "ATS", "synced", 1, "market_closed")
        finally:
            second_done.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(gateway.report_consumer, "ack-op", "TK", "synced", 1, "market_closed")
        assert first_read.wait(3)
        second = pool.submit(second_ack)
        try:
            second_done.wait(0.2)
        finally:
            release.set()
        assert first.result(timeout=3) and second.result(timeout=3)
    monkeypatch.setattr(gateway, "_connect", original)
    consumers = gateway.get_operation("ack-op")["result"]["consumers"]
    assert consumers["TK"]["status"] == consumers["ATS"]["status"] == "synced"


def test_consumer_retries_and_old_revisions_cannot_regress_ack(tmp_path):
    gateway = SystemLinkageGateway(SimpleNamespace(), database_path=str(tmp_path / "ack.sqlite3"))
    _seed_consumer_operation(gateway)
    assert not gateway.report_consumer("ack-op", "TK", "synced", 0)
    assert gateway.report_consumer("ack-op", "TK", "synced", 2, "market_closed")
    assert gateway.report_consumer("ack-op", "TK", "pending", 2)
    assert gateway.report_consumer("ack-op", "TK", "synced", 1, "pending_fetch")
    assert not gateway.report_consumer("ack-op", "TK", "synced", "invalid")
    consumer = gateway.get_operation("ack-op")["result"]["consumers"]["TK"]
    assert consumer == {"status": "synced", "favorites_revision": 2, "quote_status": "market_closed"}


def test_finish_and_notification_preserve_early_consumer_ack(tmp_path):
    gateway = SystemLinkageGateway(SimpleNamespace(), dispatch_to_ui=lambda _command: True,
                                   database_path=str(tmp_path / "ack.sqlite3"))
    _seed_consumer_operation(gateway)
    assert gateway.report_consumer("ack-op", "TK", "synced", 1, "market_closed")
    assert gateway.report_consumer("ack-op", "ATS", "synced", 1, "market_closed")
    result = {"saved": {"persisted": True, "favorites_revision": 1},
              "consumers": {"TK": {"status": "pending"}, "ATS": {"status": "not_running"}}}
    gateway._finish("ack-op", "applied", result)
    gateway._dispatch_pending_notification("ack-op", {"code": "600000"}, result)
    gateway.report_consumer_heartbeat("ATS", 2, "market_closed")
    gateway.report_consumer_heartbeat("ATS", 1, "pending_fetch")
    consumers = gateway.get_operation("ack-op")["result"]["consumers"]
    assert all(consumers[name]["status"] == "synced" for name in ("TK", "ATS"))
    with gateway._db() as connection:
        row = connection.execute("SELECT favorites_revision,quote_status FROM linkage_consumer_health WHERE consumer='ATS'").fetchone()
    assert tuple(row) == (2, "market_closed")
