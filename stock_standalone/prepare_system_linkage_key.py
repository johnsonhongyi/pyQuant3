"""Prepare the TK linkage key as a packaging resource without exposing it."""

import os
import re
import secrets


def ensure_linkage_key_file(project_dir=None):
    project_dir = os.path.abspath(project_dir or os.path.dirname(__file__))
    key_path = os.path.join(project_dir, "system_linkage.key")
    try:
        descriptor = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="") as key_file:
            key_file.write(secrets.token_hex(32) + "\n")
            key_file.flush()
            os.fsync(key_file.fileno())

    with open(key_path, "rb") as key_file:
        raw_key = key_file.read(4096).strip()
    valid_hex = len(raw_key) == 64 and re.fullmatch(rb"[0-9a-fA-F]{64}", raw_key)
    if not valid_hex and len(raw_key) < 32:
        raise ValueError("system_linkage.key must contain at least 32 bytes")
    return key_path


if __name__ == "__main__":
    print(ensure_linkage_key_file())
