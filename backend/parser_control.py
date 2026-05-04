from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


class ParserProcessManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._started_at: float | None = None
        backend_dir = Path(__file__).resolve().parent
        if load_dotenv is not None:
            load_dotenv(backend_dir / ".env", override=False)
        self._working_dir = backend_dir
        self._log_file = backend_dir.parent / "data" / "irkbus" / "logs" / "collector.log"
        self._python_executable = os.getenv("IRKBUS_PYTHON_EXECUTABLE") or sys.executable

    def _is_running_unlocked(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def is_running(self) -> bool:
        with self._lock:
            return self._is_running_unlocked()

    def start(self, use_db: bool = False, cookie: str | None = None) -> Dict[str, object]:
        with self._lock:
            cookie_value = (cookie or "").strip()
            if self._is_running_unlocked():
                # If user provides a new cookie while parser is running,
                # restart process to apply fresh auth context immediately.
                if cookie_value:
                    self._terminate_unlocked()
                else:
                    return self.status_unlocked()

            cmd = [self._python_executable, "-m", "ingest.irkbus.run"]
            if not use_db:
                cmd.append("--no-db")

            env = os.environ.copy()
            env["IRKBUS_USE_DB"] = "true" if use_db else "false"
            if cookie_value:
                env["IRKBUS_COOKIE"] = cookie_value
            elif "IRKBUS_COOKIE" in env:
                # Avoid reusing stale cookie from parent environment when user starts without cookie.
                env.pop("IRKBUS_COOKIE", None)
            self._log_file.parent.mkdir(parents=True, exist_ok=True)

            creation_flags = 0
            if os.name == "nt":
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

            self._process = subprocess.Popen(
                cmd,
                cwd=str(self._working_dir),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            self._started_at = time.time()
            return self.status_unlocked()

    def stop(self) -> Dict[str, object]:
        with self._lock:
            if not self._is_running_unlocked():
                self._process = None
                self._started_at = None
                return self.status_unlocked()

            self._terminate_unlocked()
            return self.status_unlocked()

    def status(self) -> Dict[str, object]:
        with self._lock:
            return self.status_unlocked()

    def status_unlocked(self) -> Dict[str, object]:
        running = self._is_running_unlocked()
        pid = self._process.pid if running and self._process else None
        uptime_sec = int(time.time() - self._started_at) if running and self._started_at else 0
        return {
            "running": running,
            "pid": pid,
            "uptime_sec": uptime_sec,
            "log_file": str(self._log_file),
            "python_executable": self._python_executable,
        }

    def _terminate_unlocked(self) -> None:
        if not self._is_running_unlocked():
            self._process = None
            self._started_at = None
            return

        process = self._process
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

        self._process = None
        self._started_at = None

    def read_logs(self, lines: int = 200) -> Dict[str, object]:
        clamped_lines = max(10, min(2000, int(lines)))
        log_lines = _read_last_lines(self._log_file, clamped_lines)
        return {
            **self.status(),
            "lines": clamped_lines,
            "log": "\n".join(log_lines),
        }


def _read_last_lines(path: Path, lines: int) -> List[str]:
    if not path.exists():
        return []
    # Keep implementation simple and robust for moderate log sizes.
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(content) <= lines:
        return content
    return content[-lines:]


parser_manager = ParserProcessManager()
