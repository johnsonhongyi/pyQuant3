"""Depth-bounded copying for ATS data snapshots and Windows worker threads."""

import datetime
import decimal
import enum
import pathlib
import types
import uuid
from collections import deque

_MAX_DEPTH = 64
_ATOMIC_TYPES = (
    str, bytes, int, float, complex, bool, type(None), range, type,
    datetime.date, datetime.time, datetime.timedelta, decimal.Decimal,
    enum.Enum, pathlib.PurePath, uuid.UUID,
    types.FunctionType, types.BuiltinFunctionType, types.MethodType, types.ModuleType,
)


def safe_deepcopy(value, memo=None, max_depth=_MAX_DEPTH, _current_depth=0):
    """Copy built-in containers and object state without unbounded deepcopy recursion.

    The depth ceiling is hard-capped. Opaque native objects are returned as leaves;
    NumPy/Pandas objects use their own copy methods. This prevents a custom
    ``__deepcopy__`` or reducer from exhausting a Nuitka worker's C stack.
    """
    if memo is None:
        memo = {}
    try:
        limit = min(_MAX_DEPTH, max(0, int(max_depth)))
        depth = max(0, int(_current_depth))
    except (TypeError, ValueError, OverflowError):
        limit, depth = _MAX_DEPTH, 0
    return _copy_bounded(value, memo, limit, depth)


def _shallow(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, set):
        return set(value)
    if isinstance(value, bytearray):
        return bytearray(value)
    if isinstance(value, deque):
        return deque(value, maxlen=value.maxlen)
    return value


def _empty_container(value, fallback):
    if type(value) is type(fallback):
        return fallback
    try:
        factory = getattr(value, "default_factory", None)
        return type(value)(factory) if factory is not None else type(value)()
    except Exception:
        return fallback


def _copy_bounded(value, memo, limit, depth):
    if isinstance(value, _ATOMIC_TYPES):
        return value
    identity = id(value)
    if identity in memo:
        return memo[identity]
    if depth >= limit:
        return _shallow(value)

    if isinstance(value, dict):
        result = _empty_container(value, {})
        memo[identity] = result
        for key, item in value.items():
            result[_copy_bounded(key, memo, limit, depth + 1)] = _copy_bounded(item, memo, limit, depth + 1)
        return result

    if isinstance(value, list):
        result = _empty_container(value, [])
        memo[identity] = result
        result.extend(_copy_bounded(item, memo, limit, depth + 1) for item in value)
        return result

    if isinstance(value, tuple):
        items = [_copy_bounded(item, memo, limit, depth + 1) for item in value]
        if identity in memo:
            return memo[identity]
        if hasattr(type(value), "_fields"):
            try:
                result = type(value)(*items)
            except Exception:
                result = tuple(items)
        elif type(value) is tuple:
            result = tuple(items)
        else:
            try:
                result = type(value)(items)
            except Exception:
                result = tuple(items)
        memo[identity] = result
        return result

    if isinstance(value, set):
        result = _empty_container(value, set())
        memo[identity] = result
        for item in value:
            result.add(_copy_bounded(item, memo, limit, depth + 1))
        return result

    if isinstance(value, frozenset):
        result = frozenset(_copy_bounded(item, memo, limit, depth + 1) for item in value)
        memo[identity] = result
        return result

    if isinstance(value, bytearray):
        result = bytearray(value)
        memo[identity] = result
        return result

    if isinstance(value, deque):
        result = deque(maxlen=value.maxlen)
        memo[identity] = result
        result.extend(_copy_bounded(item, memo, limit, depth + 1) for item in value)
        return result

    module = getattr(type(value), "__module__", "")
    if module.startswith("numpy"):
        try:
            result = value.copy()
            memo[identity] = result
            return result
        except Exception:
            return value
    if module.startswith("pandas"):
        try:
            result = value.copy(deep=True)
            memo[identity] = result
            return result
        except Exception:
            return value
    if module.startswith(("PyQt", "PySide")):
        return value

    try:
        result = object.__new__(type(value))
    except Exception:
        return value
    memo[identity] = result
    try:
        state = object.__getattribute__(value, "__dict__")
    except (AttributeError, TypeError):
        state = None
    if isinstance(state, dict):
        for name, item in state.items():
            try:
                object.__setattr__(result, name, _copy_bounded(item, memo, limit, depth + 1))
            except Exception:
                continue
    for base in type(value).__mro__:
        for name, descriptor in base.__dict__.items():
            if not isinstance(descriptor, types.MemberDescriptorType):
                continue
            try:
                item = object.__getattribute__(value, name)
                object.__setattr__(result, name, _copy_bounded(item, memo, limit, depth + 1))
            except Exception:
                continue
    return result
