import asyncio
import subprocess
import logging
import psutil
import httpx
import time
from pathlib import Path
from typing import Optional, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)


class LlamaServerManager:
    """
    Manages the lifecycle of the llama.cpp server process.
    - Starts the server if it's not running.
    - Tracks the server's process ID.
    - Provides a health check to see if the server is ready.
    """

    _instance = None
    _process: Optional[subprocess.Popen] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LlamaServerManager, cls).__new__(cls)
        return cls._instance

    def _is_server_running(self) -> bool:
        """Checks if a process is listening on the server's port."""
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if (
                    conn.status == psutil.CONN_LISTEN
                    and conn.laddr
                    and conn.laddr.port == settings.llama_server.port
                ):
                    logger.debug(
                        f"Port {settings.llama_server.port} is already in use."
                    )
                    return True
            return False
        except psutil.AccessDenied:
            logger.warning(
                "Access denied when checking network connections. Assuming server is not running."
            )
            return False

    async def _wait_for_server_ready(self, timeout: int = 60):
        """Polls the server's health endpoint until it's ready."""
        start_time = time.time()
        health_url = f"{str(settings.api.base_url).rstrip('/')}/health"

        # Initial sleep to allow the process to start before the first poll
        await asyncio.sleep(2)

        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    response = await client.get(health_url)
                    if (
                        response.status_code == 200
                        and response.json().get("status") == "ok"
                    ):
                        logger.info("Llama.cpp server is healthy and ready.")
                        return True
                    elif response.status_code == 503:
                        logger.debug(
                            "Server is loading model (503 Service Unavailable)..."
                        )
            except (httpx.ConnectError, httpx.ReadTimeout):
                pass  # Server not up yet, wait and retry
            except Exception as e:
                logger.error(f"Error while waiting for llama.cpp server: {e}")

            await asyncio.sleep(0.5)

        logger.error(f"Llama.cpp server did not become ready within {timeout} seconds.")
        self._terminate_process()
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
                        f"Killing existing process {p.name()} (PID: {p.pid}) on port {settings.llama_server.port}"
                    )
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        p.kill()
                except psutil.NoSuchProcess:
                    continue
                except Exception as e:
                    logger.error(f"Failed to kill existing process: {e}")

    def _start_process(self):
        """Constructs the command and starts the llama.cpp server process."""
        self._kill_existing_server()

        if not Path(settings.llama_server.binary_path).exists():
            raise FileNotFoundError(
                f"Llama server binary not found at: {settings.llama_server.binary_path}"
            )

        command = [
            settings.llama_server.binary_path,
            "--model",
            settings.llama_server.model_path,
            "--host",
            settings.llama_server.host,
            "--port",
            str(settings.llama_server.port),
        ]

        # Add additional configured arguments
        for key, value in settings.llama_server.args.items():
            command.append(str(key))
            if value is not None:
                command.append(str(value))

        # Ensure log directory exists
        log_path = Path(settings.server_logfile)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting llama.cpp server with command: {' '.join(command)}")
        try:
            # Set up the environment with the correct library paths
            import os

            env = os.environ.copy()
            binary_dir = str(Path(settings.llama_server.binary_path).parent.resolve())

            # Add the binary's directory to LD_LIBRARY_PATH
            if "LD_LIBRARY_PATH" in env:
                env["LD_LIBRARY_PATH"] = f"{binary_dir}:{env['LD_LIBRARY_PATH']}"
            else:
                env["LD_LIBRARY_PATH"] = binary_dir

            # Redirect stdout and stderr to a log file
            self._log_file = open(settings.server_logfile, "a")
            self._process = subprocess.Popen(
                command, stdout=self._log_file, stderr=subprocess.STDOUT, env=env
            )
            logger.info(
                f"Llama.cpp server process started with PID: {self._process.pid}"
            )
        except Exception as e:
            logger.error(f"Failed to start llama.cpp server process: {e}")
            if hasattr(self, "_log_file") and self._log_file:
                self._log_file.close()
            raise

    async def ensure_server_running(self):
        """
        The main public method. Ensures the server is running, starting it if necessary.
        Uses a lock to prevent race conditions from multiple concurrent requests.
        """
        async with self._lock:
            if self._is_server_running():
                logger.debug("Server is already running and listening.")
                return

            if self._process and self._process.poll() is None:
                logger.debug("Server process exists. Waiting for it to become ready.")
            else:
                self._start_process()

            if not await self._wait_for_server_ready():
                raise RuntimeError(
                    "Failed to start and connect to the llama.cpp server."
                )

    def _terminate_process(self):
        """Terminates the server process if it's running."""
        if self._process and self._process.poll() is None:
            logger.info(
                f"Terminating llama.cpp server process with PID: {self._process.pid}"
            )
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(
                    f"Server process {self._process.pid} did not terminate gracefully, killing it."
                )
                self._process.kill()
            self._process = None

        if hasattr(self, "_log_file") and self._log_file:
            self._log_file.close()

    def cleanup(self):
        """Public method to be called on application shutdown."""
        logger.info("LlamaServerManager cleaning up.")
        self._terminate_process()

    def get_stats(self) -> Dict[str, Any]:
        """Returns resource usage statistics for the llama.cpp process."""
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


# Singleton instance
llama_manager = LlamaServerManager()
