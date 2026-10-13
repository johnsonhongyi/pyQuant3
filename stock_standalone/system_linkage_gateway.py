"""Authenticated, bounded JSON bridge for cross-machine watchlist commands."""

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import contextlib
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from linkage_storage import (runtime_database, database_access,
                             configure as configure_linkage_database, trim as trim_linkage_database)
from sys_utils import get_app_root, get_base_path, get_conf_path

logger = logging.getLogger("system_linkage_gateway")
_MAX_BODY_BYTES = 64 * 1024
_CLIENT_READ_TIMEOUT_SEC = 5.0
_SIGNATURE_WINDOW_SEC = 60
_MAX_COMMAND_AGE_SEC = 5 * 60
_PRIVATE_IPV4 = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
_NODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SYMBOL_RE = re.compile(r"^(\d{6})\.(SH|SZ)$", re.IGNORECASE)
_ASHARE_PREFIXES = {
    "SH": ("600", "601", "603", "605", "688", "689"),
    "SZ": ("000", "001", "002", "003", "300", "301"),
}
_SECURITY_DIRECTORY_CACHE = {}
_SECURITY_DIRECTORY_LOCK = threading.Lock()
_CONFIG_WRITE_LOCK = threading.Lock()


def _utc_timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("invalid_timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc).timestamp()


def _is_private_ip(value):
    try:
        address = ipaddress.ip_address(value)
        return address.version == 4 and any(address in network for network in _PRIVATE_IPV4)
    except ValueError:
        return False


def _resolve_bind_host(config):
    configured = str(getattr(config, "ipc_bind_host", "auto_lan") or "auto_lan").strip()
    remote = str(getattr(config, "stock_strategy_base_url", "") or "").strip()
    if configured.lower() not in ("auto", "auto_lan"):
        try:
            address = ipaddress.ip_address(configured)
        except ValueError as error:
            raise ValueError("ipc_bind_host must be a literal IP or auto_lan") from error
        if address.is_unspecified or address.version != 4:
            raise ValueError("linkage gateway requires a specific IPv4 bind address")
        if not address.is_loopback and not _is_private_ip(configured):
            raise ValueError("linkage gateway bind address must be private or loopback")
        return configured
    if not remote:
        return _discover_private_bind_host()
    parsed = urlsplit(remote)
    if not parsed.hostname:
        raise ValueError("stock_strategy_base_url is invalid")
    try:
        remote_address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        records = socket.getaddrinfo(parsed.hostname, parsed.port or 80, socket.AF_INET, socket.SOCK_DGRAM)
        if not records:
            raise ValueError("stock_strategy_base_url host did not resolve")
        remote_address = ipaddress.ip_address(records[0][4][0])
    if remote_address.is_loopback:
        return "127.0.0.1"
    if remote_address.version != 4 or not _is_private_ip(str(remote_address)):
        raise ValueError("auto_lan only supports a configured private IPv4 Go address")
    route = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        route.connect((str(remote_address), parsed.port or 80))
        local_address = route.getsockname()[0]
    finally:
        route.close()
    if not _is_private_ip(local_address):
        raise ValueError("no private LAN route to stock-strategy was found")
    return local_address


def _discover_private_bind_host():
    addresses = []
    try:
        records = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM)
        addresses.extend(record[4][0] for record in records)
    except OSError:
        pass
    for address in addresses:
        if _is_private_ip(address):
            return address
    for destination in ("192.0.2.1", "198.51.100.1", "203.0.113.1"):
        route = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            route.connect((destination, 9))
            local_address = route.getsockname()[0]
        except OSError:
            continue
        finally:
            route.close()
        if _is_private_ip(local_address):
            return local_address
    raise ValueError("no private LAN interface is available for the linkage gateway")


def _config_target(config):
    target = getattr(config, "CFG", None) or config
    parser = getattr(target, "cfg", None)
    path = getattr(target, "cfg_file", None) or getattr(config, "conf_ini", None)
    return target, parser, path


def _linkage_config_dir(config):
    _, _, config_path = _config_target(config)
    if config_path:
        return os.path.dirname(os.path.abspath(os.path.expandvars(
            os.path.expanduser(str(config_path)))))
    return get_app_root()


def _resolve_key_file(config, key_path):
    key_path = os.path.expandvars(os.path.expanduser(str(key_path or "").strip()))
    if not key_path:
        return ""
    if not os.path.isabs(key_path):
        key_path = os.path.join(_linkage_config_dir(config), key_path)
    return os.path.abspath(key_path)


def _copy_key_file(source_path, target_path):
    with open(source_path, "rb") as source:
        key_data = source.read(4096)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".linkage-key-", dir=os.path.dirname(target_path))
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(key_data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, target_path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def _persist_config_values(config, values):
    target, parser, config_path = _config_target(config)
    if parser is not None and config_path:
        config_path = os.path.abspath(os.path.expandvars(os.path.expanduser(str(config_path))))
        parent = os.path.dirname(config_path)
        os.makedirs(parent, exist_ok=True)
        with _CONFIG_WRITE_LOCK:
            if not parser.has_section("general"):
                parser.add_section("general")
            for key, value in values.items():
                parser.set("general", key, str(value))
            descriptor, temporary_path = tempfile.mkstemp(prefix=".linkage-", suffix=".ini", dir=parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
                    parser.write(output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary_path, config_path)
            except Exception:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
                raise
    for key, value in values.items():
        setattr(target, key, value)
        if target is not config:
            setattr(config, key, value)


def ensure_linkage_config(config):
    """Persist missing desktop identity and HMAC settings before gateway startup."""
    updates = {}
    node_id = str(getattr(config, "ipc_node_id", "") or "").strip()
    workspace_id = str(getattr(config, "ipc_workspace_id", "") or "").strip()
    if not node_id:
        updates["ipc_node_id"] = "tk-" + uuid.uuid4().hex[:24]
    elif not _NODE_RE.fullmatch(node_id):
        raise ValueError("configured linkage node identity is invalid; preserve it and resolve manually")
    if not workspace_id:
        updates["ipc_workspace_id"] = "ws-" + uuid.uuid4().hex[:24]
    elif not _NODE_RE.fullmatch(workspace_id):
        raise ValueError("configured linkage identity is invalid; preserve it and resolve manually")

    configured_key_path = str(getattr(config, "ipc_key_file", "") or "").strip()
    configured_key_file = _resolve_key_file(config, configured_key_path)
    key_path = _resolve_key_file(config, "system_linkage.key")
    if (not os.path.exists(key_path)
            and configured_key_file and os.path.isfile(configured_key_file)
            and os.path.normcase(configured_key_file) != os.path.normcase(key_path)):
        _copy_key_file(configured_key_file, key_path)
    if configured_key_path != "system_linkage.key":
        updates["ipc_key_file"] = "system_linkage.key"
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    if not os.path.exists(key_path):
        # Restore the packaged key first so TK uses the same key included by
        # the build, then generate one only when no packaged key is available.
        bundled_key = os.path.join(get_base_path(), "system_linkage.key")
        has_bundled_key = os.path.isfile(bundled_key) and os.path.getsize(bundled_key) > 0
        get_conf_path("system_linkage.key", base_dir=_linkage_config_dir(config))
        if has_bundled_key and not os.path.isfile(key_path):
            raise OSError("packaged system_linkage.key could not be released to the configuration directory")
    if not os.path.exists(key_path):
        encoded_key = secrets.token_hex(32) + "\n"
        try:
            descriptor = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w", encoding="ascii", newline="") as key_file:
                key_file.write(encoded_key)
                key_file.flush()
                os.fsync(key_file.fileno())
    with open(key_path, "rb") as key_file:
        raw_key = key_file.read(4096).strip()
    try:
        key_text = raw_key.decode("ascii")
        key = bytes.fromhex(key_text) if len(key_text) == 64 and re.fullmatch(r"[0-9a-fA-F]{64}", key_text) else raw_key
    except (UnicodeDecodeError, ValueError):
        key = raw_key
    if len(key) < 32:
        raise ValueError("configured ipc_key_file must contain at least 32 bytes")

    allowlist = getattr(config, "ipc_peer_allowlist", None)
    if not isinstance(allowlist, (list, tuple)):
        allowlist = []
    normalized_allowlist = [str(item).strip() for item in allowlist if str(item).strip()]
    if not normalized_allowlist:
        updates["ipc_peer_allowlist"] = ["auto_private"]
    elif len(normalized_allowlist) != len(allowlist):
        updates["ipc_peer_allowlist"] = normalized_allowlist
    if not getattr(config, "ipc_bind_host", None):
        updates["ipc_bind_host"] = "auto_lan"
    if not getattr(config, "ipc_advertise_host", None):
        updates["ipc_advertise_host"] = "auto"
    if not getattr(config, "ipc_linkage_port", None):
        updates["ipc_linkage_port"] = 26676
    if updates:
        _persist_config_values(config, updates)
    return {"node_id": updates.get("ipc_node_id", node_id),
            "workspace_id": updates.get("ipc_workspace_id", workspace_id),
            "key": key, "key_file": key_path}


def build_setup_package(registration, key):
    return {
        "schema_version": 1,
        "kind": "stock-standalone.system-linkage",
        "node_id": registration["node_id"],
        "workspace_id": registration["workspace_id"],
        "label": socket.gethostname()[:96],
        "address": registration["address"],
        "port": registration["port"],
        "hmac_key": key.hex(),
    }


def _normalize_backend_url(value):
    parsed = urlsplit(str(value or "").strip())
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("invalid_stock_strategy_base_url")
    try:
        addresses = {ipaddress.ip_address(parsed.hostname)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in
                         socket.getaddrinfo(parsed.hostname, parsed.port or 80, socket.AF_INET, socket.SOCK_STREAM)}
        except OSError as error:
            raise ValueError("stock_strategy_base_url_did_not_resolve") from error
    if not addresses or any(address.version != 4 or not (address.is_private or address.is_loopback)
                            for address in addresses):
        raise ValueError("stock_strategy_base_url_must_resolve_to_private_ipv4")
    return parsed.geturl().rstrip("/")


def _load_security_directory():
    """Read the local stock directory without importing its network-refresh path."""
    try:
        # Share the release/update path used by StockCode in dev and packaged apps.
        path = get_conf_path("stock_codes.conf", base_dir=get_app_root())
        if not path:
            return None
        info = os.stat(path)
        if info.st_size <= 0 or info.st_size > 2 * 1024 * 1024:
            return None
        cache_key = (info.st_mtime_ns, info.st_size)
        with _SECURITY_DIRECTORY_LOCK:
            cached = _SECURITY_DIRECTORY_CACHE.get(path)
            if cached and cached[0] == cache_key:
                return cached[1]
            with open(path, "r", encoding="utf-8-sig") as source:
                payload = json.load(source)
            raw_codes = payload.get("stock") if isinstance(payload, dict) else None
            if not isinstance(raw_codes, list):
                return None
            codes = frozenset(
                value for value in raw_codes
                if isinstance(value, str) and re.fullmatch(r"\d{6}", value)
            )
            if not codes:
                return None
            _SECURITY_DIRECTORY_CACHE[path] = (cache_key, codes)
            return codes
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        logger.warning("Security directory unavailable (%s)", type(error).__name__)
        return None


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, handler, max_clients=8):
        self._client_slots = threading.BoundedSemaphore(max_clients)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._client_slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._client_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._client_slots.release()


class SystemLinkageGateway:
    """Owns the desktop inbox, HMAC verification and serial favorite writer."""

    def __init__(self, config, dispatch_to_ui=None, manager_factory=None, database_path=None, on_configured=None):
        self.config = config
        self.dispatch_to_ui = dispatch_to_ui
        self.manager_factory = manager_factory
        self.on_configured = on_configured
        self.database_path = database_path or runtime_database(os.path.join(get_app_root(), "system_linkage.sqlite3"))
        self.node_id = str(getattr(config, "ipc_node_id", "") or "").strip()
        self.workspace_id = str(getattr(config, "ipc_workspace_id", "") or "").strip()
        self._allowlist = list(getattr(config, "ipc_peer_allowlist", []) or [])
        self._stop_event = threading.Event()
        self._inbox_wakeup = threading.Event()
        self._worker = None
        self._server = None
        self._server_thread = None
        self._key = None
        self._bound_host = None
        self._port = int(getattr(config, "ipc_linkage_port", 26676) or 26676)
        self._notification_lock = threading.Lock()
        self._notification_retry_after = {}
        self._consumer_heartbeat_lock = threading.Lock()
        self._consumer_recovery_pending = set()
        self._consumer_recovery_retry_after = {}
        self._init_database()

    def _connect(self, read_only=False):
        connection = sqlite3.connect(self.database_path, timeout=3.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=3000")
        if read_only:
            connection.execute("PRAGMA query_only=ON")
        else:
            configure_linkage_database(connection)
        return connection

    @contextlib.contextmanager
    def _db(self, read_only=False):
        operation = 'gateway.' + sys._getframe(2).f_code.co_name
        with database_access(self.database_path, operation, read_only=read_only):
            connection = self._connect(read_only=read_only)
            try:
                yield connection
                if not read_only:
                    connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _init_database(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.database_path)), exist_ok=True)
        with self._db() as connection:
            connection.execute("PRAGMA journal_mode=DELETE")
            configure_linkage_database(connection)
            connection.execute("PRAGMA busy_timeout=3000")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS linkage_operations (
                    operation_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    body_hash TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '{}',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS linkage_nonces (
                    nonce_key TEXT PRIMARY KEY,
                    timestamp INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS linkage_consumer_health (
                    consumer TEXT PRIMARY KEY,
                    last_seen REAL NOT NULL,
                    favorites_revision INTEGER NOT NULL DEFAULT 0,
                    quote_status TEXT NOT NULL DEFAULT 'unknown'
                );
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(linkage_operations)")}
            if "attempts" not in columns:
                connection.execute("ALTER TABLE linkage_operations ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
            if "next_attempt" not in columns:
                connection.execute("ALTER TABLE linkage_operations ADD COLUMN next_attempt REAL NOT NULL DEFAULT 0")

    def _load_key(self):
        key_file = str(getattr(self.config, "ipc_key_file", "") or "").strip()
        if not key_file:
            raise ValueError("ipc_key_file is required")
        key_file = _resolve_key_file(self.config, key_file)
        with open(key_file, "rb") as file_obj:
            raw_key = file_obj.read(4096)
        try:
            key_text = raw_key.decode("ascii").strip()
            if len(key_text) >= 64 and len(key_text) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", key_text):
                key = bytes.fromhex(key_text)
            else:
                key = raw_key
        except UnicodeDecodeError:
            key = raw_key
        if len(key) < 32:
            raise ValueError("ipc_key_file must contain at least 32 bytes")
        return key

    def _validate_config(self):
        if not _NODE_RE.fullmatch(self.node_id) or not _NODE_RE.fullmatch(self.workspace_id):
            raise ValueError("ipc_node_id and ipc_workspace_id must be configured")
        if not isinstance(self._allowlist, (list, tuple)) or not self._allowlist:
            raise ValueError("ipc_peer_allowlist must contain the Go peer IP or CIDR")
        if not 1 <= self._port <= 65535:
            raise ValueError("ipc_linkage_port is outside the valid range")
        for entry in self._allowlist:
            if str(entry).strip().lower() == "auto_private":
                continue
            network = ipaddress.ip_network(str(entry).strip(), strict=False)
            if not (network.is_private or network.is_loopback):
                raise ValueError("ipc_peer_allowlist must only contain private peer ranges")
        advertise_host = str(getattr(self.config, "ipc_advertise_host", "auto") or "auto").strip()
        if advertise_host.lower() != "auto":
            try:
                advertise_ip = ipaddress.ip_address(advertise_host)
            except ValueError as error:
                raise ValueError("ipc_advertise_host must be a private IPv4 address or auto") from error
            if advertise_ip.version != 4 or not (advertise_ip.is_loopback or _is_private_ip(advertise_host)):
                raise ValueError("ipc_advertise_host must be a private IPv4 address or auto")
        self._key = self._load_key()
        self._bound_host = _resolve_bind_host(self.config)

    def _configure_from_peer(self, payload, peer_address):
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("invalid_setup_configuration")
        backend_url = _normalize_backend_url(payload.get("stock_strategy_base_url"))
        try:
            peer = ipaddress.ip_address(peer_address)
        except ValueError as error:
            raise ValueError("invalid_peer_address") from error
        if peer.version != 4 or not (_is_private_ip(str(peer)) or peer.is_loopback):
            raise ValueError("peer_address_must_be_private_ipv4")
        _persist_config_values(self.config, {
            "stock_strategy_base_url": backend_url,
        })
        self.config.stock_strategy_base_url = backend_url
        if self.on_configured is not None:
            try:
                self.on_configured()
            except Exception:
                logger.exception("System-linkage context restart callback failed")
        return {"status": "configured", "node_id": self.node_id,
                "workspace_id": self.workspace_id, "connection_test": "hmac_verified"}

    def start(self):
        if not bool(getattr(self.config, "linkage_enabled", False)):
            return None
        if self._server is not None:
            return self.registration()
        self._validate_config()
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "LinkageBridge/1"
            sys_version = ""
            timeout = _CLIENT_READ_TIMEOUT_SEC

            def log_message(self, format_string, *args):
                logger.info("linkage peer=%s %s", self.client_address[0], format_string % args)

            def _reply(self, status, value):
                content = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Linkage-Schema-Version", "1")
                self.end_headers()
                self.wfile.write(content)

            def _body(self):
                try:
                    length = int(self.headers.get("Content-Length", "-1"))
                except ValueError:
                    length = -1
                if length < 0 or length > _MAX_BODY_BYTES:
                    raise ValueError("invalid_content_length")
                return self.rfile.read(length)

            def _auth(self, body):
                try:
                    peer = ipaddress.ip_address(self.client_address[0])
                    peer_allowed = any(
                        (str(item).strip().lower() == "auto_private" and
                         (peer.is_private or peer.is_loopback)) or
                        (str(item).strip().lower() != "auto_private" and
                         peer in ipaddress.ip_network(str(item).strip(), strict=False))
                        for item in gateway._allowlist
                    )
                    if not peer_allowed:
                        return False
                    node = self.headers.get("X-Linkage-Node-ID", "")
                    workspace = self.headers.get("X-Linkage-Workspace-ID", "")
                    timestamp_text = self.headers.get("X-Linkage-Timestamp", "")
                    nonce = self.headers.get("X-Linkage-Nonce", "")
                    signature = self.headers.get("X-Linkage-Signature", "")
                    timestamp = int(timestamp_text)
                    if (node != gateway.node_id or workspace != gateway.workspace_id
                            or str(timestamp) != timestamp_text or abs(time.time() - timestamp) > _SIGNATURE_WINDOW_SEC
                            or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce)
                            or not re.fullmatch(r"[0-9a-fA-F]{64}", signature)):
                        return False
                    path = urlsplit(self.path).path
                    if urlsplit(self.path).query:
                        path += "?" + urlsplit(self.path).query
                    canonical = "\n".join((self.command, path, hashlib.sha256(body).hexdigest(),
                                            timestamp_text, nonce, node, workspace)).encode("utf-8")
                    expected = hmac.new(gateway._key, canonical, hashlib.sha256).hexdigest()
                    if not hmac.compare_digest(expected, signature.lower()):
                        return False
                    nonce_key = f"{node}:{workspace}:{nonce}"
                    with gateway._db() as connection:
                        connection.execute("DELETE FROM linkage_nonces WHERE timestamp < ?", (int(time.time()) - 600,))
                        connection.execute("INSERT INTO linkage_nonces(nonce_key,timestamp) VALUES(?,?)",
                                           (nonce_key, timestamp))
                    return True
                except sqlite3.IntegrityError:
                    return False
                except Exception:
                    return False

            def do_GET(self):
                if self.path == "/bridge/v1/health":
                    return self._reply(200, {"status": "ok", "schema_version": 1})
                body = b""
                if not self._auth(body):
                    return self._reply(401, {"code": "unauthorized", "error": "authentication failed"})
                prefix = "/bridge/v1/operations/"
                if self.path.startswith(prefix):
                    operation_id = self.path[len(prefix):]
                    if not _ID_RE.fullmatch(operation_id):
                        return self._reply(400, {"code": "invalid_operation_id", "error": "invalid operation id"})
                    result = gateway.get_operation(operation_id)
                    if result is None:
                        return self._reply(404, {"code": "not_found", "error": "operation not found"})
                    return self._reply(200, result)
                return self._reply(404, {"code": "not_found", "error": "route not found"})

            def do_POST(self):
                path = urlsplit(self.path).path
                if path not in ("/bridge/v1/commands", "/bridge/v1/configure"):
                    return self._reply(404, {"code": "not_found", "error": "route not found"})
                try:
                    body = self._body()
                except ValueError:
                    return self._reply(413, {"code": "invalid_content_length", "error": "request body exceeds limit"})
                if not self._auth(body):
                    return self._reply(401, {"code": "unauthorized", "error": "authentication failed"})
                try:
                    payload = json.loads(body.decode("utf-8"))
                    if path == "/bridge/v1/configure":
                        return self._reply(200, gateway._configure_from_peer(payload, self.client_address[0]))
                    command = gateway.validate_command(payload)
                    status, result = gateway.accept_command(command, hashlib.sha256(body).hexdigest())
                    return self._reply(status, result)
                except ValueError as error:
                    code = str(error)
                    status = 409 if code.endswith("_conflict") else 400
                    return self._reply(status, {"code": code, "error": "invalid linkage command"})
                except sqlite3.OperationalError:
                    return self._reply(503, {"code": "storage_unavailable", "error": "command could not be persisted"})
                except OSError:
                    logger.exception("System-linkage configuration could not be persisted")
                    return self._reply(503, {"code": "configuration_unavailable", "error": "configuration could not be persisted"})

        self._server = _BoundedThreadingHTTPServer((self._bound_host, self._port), Handler, max_clients=8)
        self._server_thread = threading.Thread(target=self._server.serve_forever,
                                               name="SystemLinkageHTTP", daemon=True)
        self._worker = threading.Thread(target=self._worker_loop, name="SystemLinkageWorker", daemon=True)
        self._inbox_wakeup.set()
        self._server_thread.start()
        self._worker.start()
        return self.registration()

    def registration(self):
        host = str(getattr(self.config, "ipc_advertise_host", "auto") or "auto").strip()
        if host.lower() == "auto":
            host = self._bound_host or ""
        return {"node_id": self.node_id, "workspace_id": self.workspace_id,
                "protocol_version": 1, "address": host, "port": self._port,
                "capabilities": ["WATCHLIST_ADD"], "status": "online" if self._server else "stopped"}

    def stop(self):
        server = self._server
        self._server = None
        self._stop_event.set()
        self._inbox_wakeup.set()
        if server is not None:
            server.shutdown()
            server.server_close()
        for thread in (self._server_thread, self._worker):
            if thread and thread.is_alive():
                thread.join(timeout=3.0)
        self._server_thread = None
        self._worker = None

    def validate_command(self, command):
        if not isinstance(command, dict) or command.get("schema_version") != 1:
            raise ValueError("unsupported_schema")
        if command.get("type") != "WATCHLIST_ADD" or command.get("instrument_type") != "stock":
            raise ValueError("unsupported_command")
        request_id = str(command.get("request_id", ""))
        operation_id = str(command.get("operation_id", ""))
        if not _ID_RE.fullmatch(request_id) or not _ID_RE.fullmatch(operation_id):
            raise ValueError("invalid_request_id")
        if command.get("workspace_id") != self.workspace_id:
            raise ValueError("wrong_workspace")
        target_nodes = command.get("target_node_ids")
        if not isinstance(target_nodes, list) or self.node_id not in target_nodes or len(target_nodes) > 10:
            raise ValueError("wrong_target")
        symbol_match = _SYMBOL_RE.fullmatch(str(command.get("symbol", "")).upper())
        if not symbol_match:
            raise ValueError("unsupported_symbol")
        code, exchange = symbol_match.groups()
        if not code.startswith(_ASHARE_PREFIXES[exchange]):
            raise ValueError("unsupported_instrument")
        security_codes = _load_security_directory()
        if security_codes is None:
            raise ValueError("security_directory_unavailable")
        if code not in security_codes:
            raise ValueError("unknown_security")
        created_at = str(command.get("created_at", ""))
        expires_at = str(command.get("expires_at", ""))
        created = _utc_timestamp(created_at)
        expires = _utc_timestamp(expires_at)
        now = time.time()
        if created > now + 60 or expires <= now or expires <= created or expires - created > _MAX_COMMAND_AGE_SEC:
            raise ValueError("command_expired")
        observed_date = command.get("observed_trade_date")
        if observed_date:
            try:
                datetime.strptime(str(observed_date), "%Y-%m-%d")
            except ValueError as error:
                raise ValueError("invalid_observed_trade_date") from error
        reason = str(command.get("reason", ""))
        source = str(command.get("source", ""))
        if len(reason) > 280 or len(source) > 80 or not source.startswith("stock-strategy."):
            raise ValueError("invalid_context")
        refs = command.get("context_refs") or []
        if not isinstance(refs, list) or len(refs) > 10 or any(not isinstance(item, str) or len(item) > 256 for item in refs):
            raise ValueError("invalid_context_refs")
        return {
            "schema_version": 1, "type": "WATCHLIST_ADD", "request_id": request_id,
            "operation_id": operation_id, "node_id": self.node_id,
            "workspace_id": self.workspace_id, "target_node_ids": [self.node_id],
            "symbol": f"{code}.{exchange}", "code": code, "exchange": exchange,
            "instrument_type": "stock", "source": source, "reason": reason,
            "context_refs": refs, "observed_trade_date": observed_date or None,
            "created_at": created_at, "expires_at": expires_at,
        }

    def accept_command(self, command, body_hash):
        now_text = datetime.now(timezone.utc).isoformat()
        payload_text = json.dumps(command, ensure_ascii=False, separators=(",", ":"))
        with self._db() as connection:
            existing = connection.execute(
                "SELECT operation_id,request_id,body_hash,status,result FROM linkage_operations "
                "WHERE operation_id=? OR request_id=?", (command["operation_id"], command["request_id"])
            ).fetchone()
            if existing:
                if existing["body_hash"] != body_hash or existing["operation_id"] != command["operation_id"]:
                    raise ValueError("operation_id_conflict")
                return 202, {"operation_id": existing["operation_id"], "request_id": existing["request_id"],
                             "status": existing["status"], "result": json.loads(existing["result"])}
            pending = connection.execute(
                "SELECT COUNT(*) FROM linkage_operations WHERE status IN ('accepted','processing','retry')"
            ).fetchone()[0]
            if pending >= 128:
                return 429, {"code": "queue_full", "error": "desktop command queue is full"}
            connection.execute(
                "INSERT INTO linkage_operations(operation_id,request_id,body_hash,payload,status,result,created_at,expires_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (command["operation_id"], command["request_id"], body_hash, payload_text,
                 "accepted", "{}", command["created_at"], command["expires_at"], now_text),
            )
        self._stop_event.clear()
        self._inbox_wakeup.set()
        return 202, {"operation_id": command["operation_id"], "request_id": command["request_id"],
                     "status": "accepted"}

    def _worker_loop(self):
        while not self._stop_event.is_set():
            self._inbox_wakeup.wait(1.0)
            self._inbox_wakeup.clear()
            if self._stop_event.is_set():
                break
            try:
                with self._db(read_only=True) as connection:
                    rows = connection.execute(
                        "SELECT operation_id,payload,expires_at FROM linkage_operations "
                        "WHERE status IN ('accepted','processing','retry') AND next_attempt<=? "
                        "ORDER BY created_at LIMIT 8", (time.time(),)
                    ).fetchall()
                    completed = connection.execute(
                        "SELECT operation_id,payload,result FROM linkage_operations "
                        "WHERE status IN ('applied','already_present') AND result LIKE '%\"status\":\"pending\"%' "
                        "ORDER BY updated_at ASC LIMIT 128"
                    ).fetchall()
                for row in rows:
                    if self._stop_event.is_set():
                        break
                    self._apply_operation(row["operation_id"], row["payload"], row["expires_at"])
                for row in completed:
                    if self._stop_event.is_set():
                        break
                    try:
                        result = json.loads(row["result"])
                        consumer = result.get("consumers", {}).get("TK", {})
                        if consumer.get("status") == "pending":
                            command = json.loads(row["payload"])
                            self._dispatch_pending_notification(row["operation_id"], command, result)
                    except Exception:
                        logger.exception("Linkage notification recovery failed")
                # Pending UI receipts are retried on the next timed pass;
                # a full batch must not spin while the consumer is unavailable.
                if len(rows) >= 8:
                    self._inbox_wakeup.set()
            except Exception:
                logger.exception("Linkage worker could not read its inbox")

    def _apply_operation(self, operation_id, payload_text, expires_at):
        try:
            with self._db() as connection:
                connection.execute(
                    "UPDATE linkage_operations SET status='processing',attempts=attempts+1,next_attempt=0 "
                    "WHERE operation_id=?", (operation_id,),
                )
            command = json.loads(payload_text)
            manager = self.manager_factory() if self.manager_factory else None
            if manager is None:
                from global_favorites import GlobalFavoriteManager
                manager = GlobalFavoriteManager()
            if _utc_timestamp(expires_at) <= time.time():
                try:
                    persisted = manager.list_linkage_operations()
                except Exception:
                    # The save may have completed before a crash even when its result
                    # was not recorded. Keep checking instead of reporting a false expiry.
                    self._schedule_retry(operation_id, expires_at, recovery_check=True)
                    return
                if operation_id not in persisted:
                    self._finish(operation_id, "expired", {"code": "command_expired"})
                    return
            result = manager.ensure_linkage_favorite(
                command["code"], operation_id, metadata={
                    "source": command["source"], "reason": command["reason"],
                    "context_refs": command["context_refs"],
                    "observed_trade_date": command["observed_trade_date"],
                    "request_id": command["request_id"],
                },
            )
            consumers = {
                "TK": {"status": "pending", "favorites_revision": result["favorites_revision"],
                       "quote_status": "pending_fetch"},
                "ATS": self._consumer_initial_status("ATS", result["favorites_revision"]),
            }
            output = {"saved": result, "consumers": consumers}
            self._finish(operation_id, result["status"], output)
            self._dispatch_pending_notification(operation_id, command, output)
        except ValueError as error:
            code = str(error)
            self._finish(operation_id, "rejected", {"code": code})
        except Exception:
            logger.exception("Linkage favorite operation failed: %s", operation_id)
            self._schedule_retry(operation_id, expires_at)

    def _schedule_retry(self, operation_id, expires_at, recovery_check=False):
        now = time.time()
        try:
            expires = _utc_timestamp(expires_at)
            with self._db() as connection:
                row = connection.execute(
                    "SELECT attempts FROM linkage_operations WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if row is None:
                    return
                if expires <= now and not recovery_check:
                    connection.execute(
                        "UPDATE linkage_operations SET status='expired',result=?,next_attempt=0,updated_at=? "
                        "WHERE operation_id=?",
                        (json.dumps({"code": "command_expired"}, separators=(",", ":")),
                         datetime.now(timezone.utc).isoformat(), operation_id),
                    )
                    return
                attempts = int(row["attempts"] or 0)
                delay = min(30, 2 ** min(attempts, 5))
                next_attempt = now + delay if recovery_check else min(expires, now + delay)
                result_code = "favorite_state_check_retryable" if recovery_check else "favorite_persistence_failed"
                result = json.dumps({"code": result_code, "retryable": True},
                                    separators=(",", ":"))
                connection.execute(
                    "UPDATE linkage_operations SET status='retry',result=?,next_attempt=?,updated_at=? "
                    "WHERE operation_id=?",
                    (result, next_attempt, datetime.now(timezone.utc).isoformat(), operation_id),
                )
        except Exception:
            # Keep an uncommitted inbox row recoverable; after restart it is retried from processing.
            logger.exception("Could not persist favorite retry state: %s", operation_id)

    def _consumer_initial_status(self, consumer, revision):
        with self._db(read_only=True) as connection:
            row = connection.execute(
                "SELECT last_seen,favorites_revision,quote_status FROM linkage_consumer_health WHERE consumer=?",
                (consumer,),
            ).fetchone()
        online = bool(row and time.time() - row["last_seen"] <= 15)
        return {"status": "pending" if online else "not_running",
                "favorites_revision": int(row["favorites_revision"] or 0) if online else 0,
                "desired_revision": revision, "quote_status": "pending_fetch"}

    def _dispatch_pending_notification(self, operation_id, command, result):
        now = time.monotonic()
        with self._notification_lock:
            if now < self._notification_retry_after.get(operation_id, 0.0):
                return
            self._notification_retry_after[operation_id] = now + 5.0
        saved = result.get("saved", {})
        revision = int(saved.get("favorites_revision", 0) or 0)
        dispatched = False
        if self.dispatch_to_ui:
            dispatched = bool(self.dispatch_to_ui({"operation_id": operation_id,
                                                   "code": command["code"],
                                                   "favorites_revision": revision}))
        # Enqueueing on the UI thread is not proof that the monitor consumed it.
        status = "pending" if dispatched else "not_running"
        self.report_consumer(operation_id, "TK", status, revision, "pending_fetch")

    def _finish(self, operation_id, status, result):
        now_text = datetime.now(timezone.utc).isoformat()
        with self._db() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if status in ("applied", "already_present"):
                row = connection.execute("SELECT result FROM linkage_operations WHERE operation_id=?", (operation_id,)).fetchone()
                previous = json.loads(row["result"]) if row else {}
                consumers = result.setdefault("consumers", {})
                for consumer, ack in previous.get("consumers", {}).items():
                    if ack.get("status") == "synced" and int(ack.get("favorites_revision", 0) or 0) >= int(
                        result.get("saved", {}).get("favorites_revision", 0) or 0
                    ):
                        consumers[consumer] = ack
            connection.execute(
                "UPDATE linkage_operations SET status=?,result=?,updated_at=? WHERE operation_id=?",
                (status, json.dumps(result, ensure_ascii=False, separators=(",", ":")), now_text, operation_id),
            )

    def get_operation(self, operation_id):
        with self._db(read_only=True) as connection:
            row = connection.execute(
                "SELECT operation_id,request_id,status,result,updated_at FROM linkage_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        return {"operation_id": row["operation_id"], "request_id": row["request_id"],
                "status": row["status"], "result": json.loads(row["result"]), "updated_at": row["updated_at"]}

    def report_consumer(self, operation_id, consumer, status, favorites_revision=0, quote_status="unknown"):
        if consumer not in ("TK", "ATS") or status not in ("synced", "pending", "not_running", "error"):
            return False
        if quote_status not in ("ready", "pending_fetch", "unknown", "market_closed", "stale", "quota_limited"):
            quote_status = "unknown"
        try:
            revision = int(favorites_revision or 0)
        except (TypeError, ValueError, OverflowError):
            return False
        if revision < 0:
            return False
        with self._db() as connection:
            # Acquire the writer before reading the shared JSON (also across processes).
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT result FROM linkage_operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None:
                return False
            result = json.loads(row["result"])
            consumers = result.setdefault("consumers", {})
            existing = consumers.get(consumer, {})
            previous_revision = int(existing.get("favorites_revision", 0) or 0)
            if revision < previous_revision or (
                revision == previous_revision and existing.get("status") == "synced" and status != "synced"
            ):
                return True
            if status == "synced" and revision < int(result.get("saved", {}).get("favorites_revision", 0) or 0):
                return False
            consumers[consumer] = {"status": status, "favorites_revision": revision,
                                   "quote_status": quote_status}
            connection.execute("UPDATE linkage_operations SET result=?,updated_at=? WHERE operation_id=?",
                               (json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                                datetime.now(timezone.utc).isoformat(), operation_id))
        return True

    def report_consumer_heartbeat(self, consumer, favorites_revision=0, quote_status="unknown"):
        if consumer not in ("TK", "ATS"):
            return False
        if quote_status not in ("ready", "pending_fetch", "unknown", "market_closed", "stale", "quota_limited"):
            quote_status = "unknown"
        with self._consumer_heartbeat_lock:
            now = time.time()
            with self._db() as connection:
                connection.execute("BEGIN IMMEDIATE")
                previous = connection.execute(
                    "SELECT last_seen FROM linkage_consumer_health WHERE consumer=?", (consumer,)
                ).fetchone()
                reconnected = not previous or now - float(previous["last_seen"] or 0) > 15
                connection.execute(
                    "INSERT INTO linkage_consumer_health(consumer,last_seen,favorites_revision,quote_status) VALUES(?,?,?,?) "
                    "ON CONFLICT(consumer) DO UPDATE SET last_seen=excluded.last_seen, "
                    "favorites_revision=MAX(linkage_consumer_health.favorites_revision,excluded.favorites_revision), "
                    "quote_status=CASE WHEN excluded.favorites_revision>=linkage_consumer_health.favorites_revision "
                    "THEN excluded.quote_status ELSE linkage_consumer_health.quote_status END",
                    (consumer, now, int(favorites_revision or 0), quote_status),
                )

            # A normal heartbeat must not scan and rewrite every completed operation.
            # Requeue stale consumer notifications only once at startup/reconnect, in
            # a separate transaction so a recovery scan cannot roll back the heartbeat.
            retry_after = self._consumer_recovery_retry_after.get(consumer, 0.0)
            should_reconcile = reconnected or consumer in self._consumer_recovery_pending
            if should_reconcile and time.monotonic() >= retry_after:
                try:
                    # Decode outside the writer transaction; compare-and-swap
                    # prevents a concurrent receipt from being overwritten.
                    with self._db() as connection:
                        rows = connection.execute(
                            "SELECT operation_id,result FROM linkage_operations "
                            "WHERE status IN ('applied','already_present') AND result LIKE '%not_running%'"
                        ).fetchall()
                    updates = []
                    for row in rows:
                        result = json.loads(row["result"])
                        consumers = result.setdefault("consumers", {})
                        if consumers.get(consumer, {}).get("status") == "not_running":
                            consumers[consumer] = {"status": "pending", "favorites_revision": 0,
                                                   "quote_status": "pending_fetch"}
                            updates.append((json.dumps(result, separators=(",", ":")),
                                            row["operation_id"], row["result"]))
                    conflicted = False
                    for offset in range(0, len(updates), 64):
                        with self._db() as connection:
                            connection.execute("BEGIN IMMEDIATE")
                            for values in updates[offset:offset + 64]:
                                changed = connection.execute(
                                    "UPDATE linkage_operations SET result=? WHERE operation_id=? AND result=?", values)
                                conflicted = conflicted or changed.rowcount != 1
                    if conflicted:
                        self._consumer_recovery_pending.add(consumer)
                        self._consumer_recovery_retry_after[consumer] = time.monotonic() + 30.0
                    else:
                        self._consumer_recovery_pending.discard(consumer)
                        self._consumer_recovery_retry_after.pop(consumer, None)
                except Exception:
                    self._consumer_recovery_pending.add(consumer)
                    self._consumer_recovery_retry_after[consumer] = time.monotonic() + 30.0
                    logger.exception("Could not reconcile %s notifications after reconnect", consumer)
        return True

    def report_consumer_batch(self, consumer, operations, favorites_revision=0):
        if consumer not in ("TK", "ATS") or not isinstance(operations, list):
            return 0
        reported = 0
        for item in operations[:128]:
            if not isinstance(item, dict):
                continue
            operation_id = str(item.get("operation_id", ""))
            quote_status = item.get("quote_status", "pending_fetch")
            if self.report_consumer(operation_id, consumer, "synced", favorites_revision, quote_status):
                reported += 1
        return reported
