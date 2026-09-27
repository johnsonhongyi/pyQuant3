# -*- coding: utf-8 -*-
"""
ats/llm/antigravity_cli_backend.py
----------------------------------
基于本地 Antigravity CLI (agy) 的大模型推理适配器
- 优先级：系统第一优先推理资源 (Priority 1)；
- 复用本地环境：直接复用本地环境已登录/配置的大模型特权，无需额外 API Key；
- 严格受控与只读隔离：
  - 增加 --sandbox 终端沙箱限制；
  - 增加 --print-timeout 硬超时限制；
  - 强制 --output-format json 结构化输出；
  - Prompt 经由 stdin 传输，杜绝参数长度超限与字符转义溢出；
  - 超时与异常快速熔断，主交易 100% 走纯规则保底。
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger("AntigravityCLIBackend")

_DEFAULT_AGY_PATH = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.ps1")


class AntigravityCLIBackend:
    """Antigravity CLI (agy) 只读旁路推理适配器"""

    def __init__(
        self,
        cli_path: Optional[str] = None,
        timeout_seconds: float = 25.0,
        model_id: Optional[str] = None,
    ) -> None:
        self.cli_path = self._resolve_cli_path(cli_path)
        self.timeout_seconds = max(5.0, min(float(timeout_seconds), 30.0))
        self.model_id = str(model_id).strip() if model_id else None

    @staticmethod
    def _resolve_cli_path(explicit_path: Optional[str] = None) -> str:
        if explicit_path and Path(explicit_path).is_file():
            return str(Path(explicit_path).resolve())
        if Path(_DEFAULT_AGY_PATH).is_file():
            return str(Path(_DEFAULT_AGY_PATH).resolve())
        which_agy = shutil.which("agy")
        if which_agy:
            return which_agy
        return _DEFAULT_AGY_PATH

    def is_available(self) -> bool:
        """检查 agy CLI 是否在当前系统就绪"""
        return Path(self.cli_path).is_file() or bool(shutil.which("agy"))

    def invoke(
        self,
        prompt: str,
        json_schema: Optional[Mapping[str, Any]] = None,
        timeout_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """向 agy CLI 发送只读推理请求并获取结构化 JSON 响应。

        Returns:
            dict: {
                "success": bool,
                "payload": Optional[dict],
                "error_code": Optional[str],
                "error_msg": Optional[str],
                "duration_ms": float,
            }
        """
        import time
        start_time = time.monotonic()
        timeout = float(timeout_override) if timeout_override else self.timeout_seconds

        if not self.is_available():
            return {
                "success": False,
                "payload": None,
                "error_code": "CLI_NOT_FOUND",
                "error_msg": f"未找到可执行的 agy CLI: {self.cli_path}",
                "duration_ms": 0.0,
            }

        # 构造执行命令
        # Windows 上若为 .ps1 脚本，使用 powershell.exe 执行
        is_ps1 = self.cli_path.lower().endswith(".ps1")
        timeout_arg = f"{int(timeout)}s"

        cmd = []
        if is_ps1:
            cmd.extend([
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-Command",
                f"& '{self.cli_path}' -p - --output-format json --sandbox --disable-slash-commands --print-timeout {timeout_arg}"
            ])
            if self.model_id:
                cmd[-1] += f" --model {self.model_id}"
        else:
            cmd.extend([
                self.cli_path,
                "-p", "-",
                "--output-format", "json",
                "--sandbox",
                "--disable-slash-commands",
                "--print-timeout", timeout_arg,
            ])
            if self.model_id:
                cmd.extend(["--model", self.model_id])

        # 若提供了 json_schema，将 Schema 约束写入提示引导
        effective_prompt = prompt
        if json_schema:
            try:
                schema_str = json.dumps(json_schema, ensure_ascii=False)
                effective_prompt = (
                    f"{prompt}\n\n"
                    f"【严格约束】你必须只输出符合以下 JSON Schema 的纯合法 JSON，严禁输出任何解释或 Markdown：\n"
                    f"{schema_str}"
                )
            except Exception:
                pass

        try:
            # 经由 stdin 传输 Prompt
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout_data, stderr_data = proc.communicate(
                input=effective_prompt,
                timeout=timeout + 2.0,  # 留出 2 秒子进程清理缓冲
            )
            duration_ms = (time.monotonic() - start_time) * 1000.0

            if proc.returncode != 0:
                return {
                    "success": False,
                    "payload": None,
                    "error_code": f"CLI_EXIT_{proc.returncode}",
                    "error_msg": stderr_data.strip()[:300] if stderr_data else "CLI 非零退出",
                    "duration_ms": duration_ms,
                }

            # 解析返回的 JSON
            cleaned_text = stdout_data.strip()
            # 过滤可能的 markdown ```json 包裹
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()

            parsed = json.loads(cleaned_text)
            return {
                "success": True,
                "payload": parsed,
                "error_code": None,
                "error_msg": None,
                "duration_ms": duration_ms,
            }

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except Exception:
                pass
            return {
                "success": False,
                "payload": None,
                "error_code": "CLI_TIMEOUT",
                "error_msg": f"agy CLI 执行超时 (> {timeout}s)",
                "duration_ms": duration_ms,
            }
        except json.JSONDecodeError as exc:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return {
                "success": False,
                "payload": None,
                "error_code": "JSON_DECODE_ERROR",
                "error_msg": f"输出非有效 JSON: {str(exc)[:150]} (原始输出: {stdout_data[:100]})",
                "duration_ms": duration_ms,
            }
        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            return {
                "success": False,
                "payload": None,
                "error_code": "CLI_EXCEPTION",
                "error_msg": str(exc)[:200],
                "duration_ms": duration_ms,
            }
