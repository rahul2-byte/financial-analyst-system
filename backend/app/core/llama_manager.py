import asyncio
import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import psutil

from app.config import settings

logger = logging.getLogger(__name__)


class LlamaServerManager:
    """
    Manages the lifecycle of the llama.cpp server process.
    - Starts the server if it's not running.
    - Tracks the server's process.
    - Performs health checks and cleanup.
    """

    _instance = None
    _process: Optional[subprocess.Popen] = None
    _lock = asyncio.Lock()
    _is_shutting_down = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LlamaServerManager, cls).__new__(cls)
        return cls._instance

    def _health_url(self) -> str:
        return f"{str(settings.api.base_url).rstrip('/')}/health"

    async def _check_health(self, timeout: float = 2.0) -> bool:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self._health_url())
                if response.status_code != 200:
                    return False
                payload = response.json()
                return payload.get("status") == "ok"
        except Exception:
            return False

    def _is_server_running(self) -> bool:
        """Checks if any process is listening on the configured server port."""
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if (
                    conn.status == psutil.CONN_LISTEN
                    and conn.laddr
                    and conn.laddr.port == settings.llama_server.port
                ):
                    return True
            return False
        except psutil.AccessDenied:
            logger.warning(
                "Access denied when checking network connections. Assuming not running."
            )
            return False

    async def _wait_for_server_ready(self, timeout: int = 180) -> bool:
        """Polls the server's health endpoint until it's ready."""
        start_time = time.time()

        # Give process a moment to initialize before first probe.
        await asyncio.sleep(2)

        while time.time() - start_time < timeout:
            if await self._check_health(timeout=1.0):
                logger.info("Llama.cpp server is healthy and ready.")
                return True
            await asyncio.sleep(1)

        logger.error(
            "Llama.cpp server did not become ready within %s seconds.", timeout
        )
        return False

    def _kill_existing_server(self):
        """Kills any existing process listening on the configured port."""
        for conn in psutil.net_connections(kind="tcp"):
            if (
                conn.status == psutil.CONN_LISTEN
                and conn.laddr
                and conn.laddr.port == settings.llama_server.port
            ):
                try:
                    p = psutil.Process(conn.pid)
                    logger.warning(
                        "Killing existing process %s (PID: %s) on port %s",
                        p.name(),
                        p.pid,
                        settings.llama_server.port,
                    )
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        p.kill()
                except psutil.NoSuchProcess:
                    continue
                except Exception as e:
                    logger.error("Failed to kill existing process: %s", e)

    def _start_process(self):
        """Constructs the command and starts the llama.cpp server process."""
        binary_path = Path(settings.llama_server.binary_path)
        model_path = Path(settings.llama_server.model_path)

        if not binary_path.exists():
            raise FileNotFoundError(f"Llama server binary not found at: {binary_path}")
        if not model_path.exists():
            raise FileNotFoundError(f"Llama model not found at: {model_path}")

        command = [
            str(binary_path.resolve()),
            "--model",
            str(model_path.resolve()),
            "--host",
            settings.llama_server.host,
            "--port",
            str(settings.llama_server.port),
        ]

        for key, value in settings.llama_server.args.items():
            command.append(str(key))
            if value is not None:
                command.append(str(value))

        log_path = Path(settings.server_logfile)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Starting llama.cpp server with command: %s", " ".join(command))

        env = os.environ.copy()
        binary_dir = str(binary_path.parent.resolve())
        env["LD_LIBRARY_PATH"] = (
            f"{binary_dir}:{env['LD_LIBRARY_PATH']}"
            if "LD_LIBRARY_PATH" in env
            else binary_dir
        )

        self._log_file = open(log_path, "a")
        self._process = subprocess.Popen(
            command,
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
            env=env,
        )
        logger.info("Llama.cpp server process started with PID: %s", self._process.pid)

    async def ensure_server_running(self):
        """
        Ensures the server is running, starting it if necessary.
        Uses a lock to avoid concurrent restarts.
        """
        if self._is_shutting_down:
            return

        async with self._lock:
            # Fast path: we started it and it is healthy.
            if (
                self._process
                and self._process.poll() is None
                and await self._check_health()
            ):
                return

            # If an external process is already healthy on the port, use it.
            if self._is_server_running() and await self._check_health():
                logger.debug("Llama.cpp already running on port and healthy.")
                return

            # Cleanup stale/broken process and restart.
            self._terminate_process()
            self._kill_existing_server()
            self._start_process()

            if not await self._wait_for_server_ready(timeout=180):
                self._terminate_process()
                raise RuntimeError(
                    "Failed to start and connect to the llama.cpp server."
                )

    def _terminate_process(self):
        """Terminates the managed server process if it's running."""
        if self._process and self._process.poll() is None:
            logger.info(
                "Terminating llama.cpp server process with PID: %s", self._process.pid
            )
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Server process %s did not terminate gracefully, killing it.",
                    self._process.pid,
                )
                self._process.kill()

        self._process = None

        if hasattr(self, "_log_file") and self._log_file:
            self._log_file.close()

    def cleanup(self):
        """Public method to be called on application shutdown."""
        if self._is_shutting_down:
            return
        logger.info("LlamaServerManager cleaning up.")
        self._is_shutting_down = True
        self._terminate_process()

    def get_stats(self) -> Dict[str, Any]:
        """Returns resource usage statistics for the managed llama.cpp process."""
        if not self._process or self._process.poll() is not None:
            return {"status": "not_running"}

        try:
            p = psutil.Process(self._process.pid)
            mem = p.memory_info()
            return {
                "status": "running",
                "pid": self._process.pid,
                "cpu_percent": p.cpu_percent(),
                "memory_rss_mb": mem.rss / (1024 * 1024),
                "memory_vms_mb": mem.vms / (1024 * 1024),
                "num_threads": p.num_threads(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"status": "error", "message": "could_not_access_process"}


llama_manager = LlamaServerManager()
