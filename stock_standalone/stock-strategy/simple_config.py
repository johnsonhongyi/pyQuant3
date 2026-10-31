"""Dependency-free reader for the flat/nested sections used by the paper worker.

The production host does not ship PyYAML.  Only ``version``, ``buy``, ``sell``,
``decision_gate`` and ``execution`` are needed by ``auto_follow.py``; those
sections contain maps, scalars and inline string lists, which this reader
handles without pretending to be a general YAML implementation.
"""
from pathlib import Path

SECTIONS = ("version", "buy", "sell", "decision_gate", "execution")


def _strip_comment(text):
    quote = None
    for index, char in enumerate(text):
        if char in "\"'":
            quote = None if quote == char else (char if quote is None else quote)
        elif char == "#" and quote is None and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip()
    return text.rstrip()


def _scalar(text):
    text = _strip_comment(text).strip()
    if not text:
        return None
    if text[0] in "[{" and text[-1] in "]}":
        body = text[1:-1].strip()
        if not body:
            return []
        items, current, quote = [], "", None
        for char in body:
            if char in "\"'":
                quote = None if quote == char else (char if quote is None else quote)
                current += char
            elif char == "," and quote is None:
                items.append(_scalar(current))
                current = ""
            else:
                current += char
        if current.strip():
            items.append(_scalar(current))
        return items
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "none", "~"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _section_lines(lines, name):
    start = None
    for index, line in enumerate(lines):
        if line.startswith(name + ":"):
            start = index
            break
    if start is None:
        return []
    result = []
    for line in lines[start + 1:]:
        if line and not line.startswith((" ", "\t", "#")):
            break
        result.append(line)
    return result


def _parse_block(lines, index, indent):
    result = {}
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        current = len(raw) - len(raw.lstrip(" "))
        if current < indent:
            break
        if current > indent:
            raise ValueError("unexpected indentation: %s" % stripped)
        key, separator, rest = stripped.partition(":")
        if not separator:
            raise ValueError("invalid line: %s" % stripped)
        key = key.strip()
        if _strip_comment(rest).strip():
            result[key] = _scalar(rest)
            index += 1
        else:
            value, index = _parse_block(lines, index + 1, indent + 2)
            result[key] = value
    return result, index


def load(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    config = {}
    for line in lines:
        if line.startswith("version:"):
            config["version"] = _scalar(line.split(":", 1)[1])
            break
    for name in SECTIONS:
        if name == "version":
            continue
        body = _section_lines(lines, name)
        if not body:
            continue
        parsed, _ = _parse_block(body, 0, 2)
        config[name] = parsed
    return config
