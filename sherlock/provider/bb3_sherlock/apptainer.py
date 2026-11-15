"""Inspect sandbox provider "apptainer" for running BixBench3 on Stanford Sherlock.

Mirrors the `default` service of sandbox/compose.yaml:
  - same image (the bixbench3-sandbox:1.0.0 Docker image converted to a SIF),
  - same mounts (/data read-only, /workspace, /outputs), working dir /workspace,
  - same proxy environment (HTTP(S)_PROXY -> network-gateway), root user,
  - no network except the gateway proxy, enforced by bb3jail (seccomp + ptrace)
    because Sherlock cannot create network namespaces.

Every command runs as `env -i ... apptainer exec --cleanenv instance://... bb3jail ...`
so no host variable (in particular no API key) reaches the sandbox.

Config: `inspect eval --sandbox apptainer:/path/to/sandbox.json` with
{
  "sif": "/path/bixbench3-sandbox_1.0.0.sif",
  "overlay_dir": "/lscratch/.../overlay",          # writable layer, fresh per run
  "binds": [["/host/data", "/data", "ro"], ["/host/workspace", "/workspace", "rw"], ...],
  "jail_dir": "/path/dir/containing/bb3jail",
  "jail_log_dir": "/host/dir/for/jail/log",
  "proxy_port": 31280,
  "hosts_file": "/host/hosts",                     # maps network-gateway -> 127.0.0.1
  "env": {"HTTP_PROXY": "http://network-gateway:31280", ...},
  "workdir": "/workspace",
  "host_path": "/usr/bin:/bin:..."                 # PATH used to find apptainer
}
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import socket
import tempfile
import time
import urllib.request
import uuid
import warnings
from pathlib import Path
from typing import Any, Literal, overload

from inspect_ai.util import ExecResult, subprocess
from inspect_ai.util._sandbox.environment import (
    SandboxEnvironment,
    SandboxEnvironmentConfigType,
)
from inspect_ai.util._sandbox.limits import (
    OutputLimitExceededError,
    SandboxEnvironmentLimits,
)
from inspect_ai.util._sandbox.registry import sandboxenv

JAIL_IN_CONTAINER = "/opt/bb3jail"
JAIL_LOG_IN_CONTAINER = "/opt/bb3jail-log"
TIMEOUT_GRACE_SECONDS = 30


def _load_config(config: SandboxEnvironmentConfigType | None) -> dict[str, Any]:
    if isinstance(config, str):
        return json.loads(Path(config).read_text(encoding="utf-8"))
    if isinstance(config, dict):
        return dict(config)
    raise ValueError("apptainer sandbox needs a JSON config file: --sandbox apptainer:/path/sandbox.json")


def _host_env(cfg: dict[str, Any]) -> dict[str, str]:
    """Minimal environment for the apptainer client itself (never the caller's)."""
    env = {
        "PATH": cfg.get("host_path") or "/usr/local/bin:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/tmp"),
        "USER": os.environ.get("USER", ""),
        "LANG": "C.UTF-8",
    }
    for key in ("APPTAINER_CACHEDIR", "APPTAINER_TMPDIR", "TMPDIR", "XDG_RUNTIME_DIR", "BB3_HOSTEXEC_SOCK"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


async def _run_clean(
    cfg: dict[str, Any],
    argv: list[str],
    *,
    input: str | bytes | None = None,
    timeout: int | None = None,
    text: bool = True,
    output_limit: int | None = None,
) -> ExecResult[Any]:
    # `env -i` drops the inherited environment (inspect's subprocess() merges os.environ).
    env_args = [f"{k}={v}" for k, v in _host_env(cfg).items()]
    return await subprocess(
        ["env", "-i", *env_args, *argv],
        text=text,  # type: ignore[arg-type]
        input=input,
        timeout=timeout,
        output_limit=output_limit,
        env={},
    )


GATEWAY_ENV_FROM_HOST = ("BIXBENCH3_BROKER_TOKEN", "OPENAI_API_KEY")


def _gateway_healthy(squid_port: int, broker_port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", squid_port), timeout=2).close()
        with urllib.request.urlopen(f"http://127.0.0.1:{broker_port}/health", timeout=2):
            return True
    except OSError:
        return False


async def _start_gateway(cfg: dict[str, Any]) -> asyncio.subprocess.Process:
    """Start the network gateway exactly like the compose `network-gateway` service."""
    gw = cfg["gateway"]
    workspace = os.environ["BIXBENCH3_WORKSPACE_DIR"]
    env = {
        "BIXBENCH3_BROKER_POLICY": "/broker/policy.json",
        "BIXBENCH3_BROKER_LOG_DIR": "/broker/logs",
        "BIXBENCH3_BROKER_CACHE_DIR": "/broker/cache",
        "BIXBENCH3_APPROVED_WEB_DIR": "/workspace/approved_web",
        "BIXBENCH3_TASK_PROMPT": "/task/prompt.md",
        "BIXBENCH3_RUNTIME_CASE": "/task/case.json",
        "BB3_SQUID_PORT": str(int(gw["squid_port"])),
        "BB3_BROKER_PORT": str(int(gw["broker_port"])),
    }
    for key in GATEWAY_ENV_FROM_HOST:
        if not os.environ.get(key):
            raise RuntimeError(f"{key} is required by the network gateway")
        env[key] = os.environ[key]
    fd, env_file = tempfile.mkstemp(prefix="bb3-gw-", suffix=".env")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        for key, value in env.items():
            handle.write(f"{key}={shlex.quote(value)}\n")
    binds = [
        f"{os.environ['BIXBENCH3_BROKER_POLICY']}:/broker/policy.json:ro",
        f"{os.environ['BIXBENCH3_BROKER_LOG_DIR']}:/broker/logs:rw",
        f"{os.environ['BIXBENCH3_BROKER_CACHE_DIR']}:/broker/cache:rw",
        f"{workspace}:/workspace:rw",
        f"{workspace}/../dataset:/task:ro",
        f"{gw['squid_log_dir']}:/var/log/squid:rw",
        f"{gw['supervisor_file']}:/app/bixbench3/network_gateway/supervisor.py:ro",
    ]
    argv = ["apptainer", "exec", "--containall", "--cleanenv", "--writable-tmpfs", "--pwd", "/app",
            "--env-file", env_file]
    for bind in binds:
        argv += ["--bind", bind]
    argv += [gw["sif"], "python", "-m", "bixbench3.network_gateway"]
    log = open(gw["log_file"], "ab")
    env_args = [f"{k}={v}" for k, v in _host_env(cfg).items()]
    process = await asyncio.create_subprocess_exec(
        "env", "-i", *env_args, *argv, stdout=log, stderr=log, stdin=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    log.close()
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if process.returncode is not None:
                raise RuntimeError(f"network gateway exited with status {process.returncode}; see {gw['log_file']}")
            if await asyncio.to_thread(_gateway_healthy, int(gw["squid_port"]), int(gw["broker_port"])):
                return process
            await asyncio.sleep(2)
        process.terminate()
        raise RuntimeError(f"network gateway did not become healthy; see {gw['log_file']}")
    finally:
        Path(env_file).unlink(missing_ok=True)


async def _stop_process(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=30)
    except TimeoutError:
        process.kill()
        await process.wait()


@sandboxenv(name="apptainer")
class ApptainerSandboxEnvironment(SandboxEnvironment):
    def __init__(
        self,
        cfg: dict[str, Any],
        instance: str,
        env_file: str,
        gateway: asyncio.subprocess.Process | None,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.instance = instance
        self.env_file = env_file
        self.gateway = gateway

    # ------------------------------------------------------------ lifecycle
    @classmethod
    async def sample_init(
        cls,
        task_name: str,
        config: SandboxEnvironmentConfigType | None,
        metadata: dict[str, str],
    ) -> dict[str, SandboxEnvironment]:
        cfg = _load_config(config)
        gateway = await _start_gateway(cfg) if cfg.get("gateway") else None
        instance = f"bb3-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        # One writable layer and /tmp per sample attempt, like a fresh container per attempt on GCP
        # (an Inspect sample retry must not inherit the dead attempt's root fs, /tmp or tool sockets).
        base = Path(cfg["overlay_dir"])
        overlay = base / instance
        overlay.mkdir(parents=True, exist_ok=True)
        # --containall would put /tmp and /var/tmp on a small session tmpfs; use node-local disk
        workdir = Path(cfg.get("workdir_dir") or base.parent / "apptainer-workdir") / instance
        workdir.mkdir(parents=True, exist_ok=True)
        fd, env_file = tempfile.mkstemp(prefix="bb3-env-", suffix=".env")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for key, value in (cfg.get("env") or {}).items():
                handle.write(f"{key}={shlex.quote(str(value))}\n")
        argv = [
            "apptainer", "instance", "start",
            "--containall", "--cleanenv",
            "--fakeroot", "--ignore-fakeroot-command",
            "--overlay", str(overlay),
            "--workdir", str(workdir),
            "--env-file", env_file,
            "--bind", f"{cfg['jail_dir']}:{JAIL_IN_CONTAINER}:ro",
            "--bind", f"{cfg['jail_log_dir']}:{JAIL_LOG_IN_CONTAINER}:rw",
        ]
        if cfg.get("hosts_file"):
            argv += ["--bind", f"{cfg['hosts_file']}:/etc/hosts:ro"]
        for source, target, mode in cfg.get("binds", []):
            argv += ["--bind", f"{source}:{target}:{mode}"]
        argv += [cfg["sif"], instance]
        result = await _run_clean(cfg, argv, timeout=600)
        if not result.success:
            await _stop_process(gateway)
            raise RuntimeError(f"apptainer instance start failed: {result.stderr.strip()}")
        return {"default": cls(cfg, instance, env_file, gateway)}

    @classmethod
    async def sample_cleanup(
        cls,
        task_name: str,
        config: SandboxEnvironmentConfigType | None,
        environments: dict[str, SandboxEnvironment],
        interrupted: bool,
    ) -> None:
        for environment in environments.values():
            sandbox = environment.as_type(ApptainerSandboxEnvironment)
            await _run_clean(sandbox.cfg, ["apptainer", "instance", "stop", "--force", sandbox.instance], timeout=120)
            Path(sandbox.env_file).unlink(missing_ok=True)
            base = Path(sandbox.cfg["overlay_dir"])
            for path in (base / sandbox.instance,
                         Path(sandbox.cfg.get("workdir_dir") or base.parent / "apptainer-workdir") / sandbox.instance):
                await asyncio.to_thread(shutil.rmtree, path, True)  # free node-local disk; errors ignored
            await _stop_process(sandbox.gateway)

    @classmethod
    async def cli_cleanup(cls, id: str | None) -> None:
        return None

    # ------------------------------------------------------------ helpers
    def _exec_prefix(self, cwd: str | None, env: dict[str, str] | None, env_file: str | None) -> list[str]:
        workdir = self.cfg.get("workdir", "/workspace")
        if cwd is None:
            cwd = workdir
        elif not cwd.startswith("/"):
            cwd = f"{workdir.rstrip('/')}/{cwd}"
        argv = ["apptainer", "exec", "--cleanenv", "--pwd", cwd, "--env-file", self.env_file]
        if env_file:
            argv += ["--env-file", env_file]
        return argv + [f"instance://{self.instance}"]

    def _jail(self) -> list[str]:
        return [
            f"{JAIL_IN_CONTAINER}/bb3jail",
            "--proxy-port", str(int(self.cfg["proxy_port"])),
            "--log", f"{JAIL_LOG_IN_CONTAINER}/jail.log",
            "--",
        ]

    # ------------------------------------------------------------ API
    async def exec(
        self,
        cmd: list[str],
        input: str | bytes | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        user: str | None = None,
        timeout: int | None = None,
        timeout_retry: bool = True,
        concurrency: bool = True,
    ) -> ExecResult[str]:
        if user not in (None, "root"):
            warnings.warn(
                f"apptainer sandbox runs every command as root (requested user {user!r})",
                UserWarning,
                stacklevel=2,
            )
        env_file = None
        if env:
            fd, env_file = tempfile.mkstemp(prefix="bb3-exec-env-", suffix=".env")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for key, value in env.items():
                    handle.write(f"{key}={shlex.quote(str(value))}\n")
        inner = list(cmd)
        if timeout is not None:
            inner = ["timeout", "--kill-after=5", str(int(timeout)), *inner]
        try:
            result = await _run_clean(
                self.cfg,
                [*self._exec_prefix(cwd, env, env_file), *self._jail(), *inner],
                input=input,
                timeout=(timeout + TIMEOUT_GRACE_SECONDS) if timeout is not None else None,
                output_limit=SandboxEnvironmentLimits.MAX_EXEC_OUTPUT_SIZE,
            )
        finally:
            if env_file:
                Path(env_file).unlink(missing_ok=True)
        if timeout is not None and result.returncode == 124:
            raise TimeoutError(f"command timed out after {timeout} seconds")
        return result

    async def write_file(self, file: str, contents: str | bytes) -> None:
        data = contents.encode("utf-8") if isinstance(contents, str) else contents
        script = 'mkdir -p -- "$(dirname -- "$1")" && cat > "$1"'
        result = await _run_clean(
            self.cfg,
            [*self._exec_prefix(None, None, None), "sh", "-c", script, "sh", file],
            input=data,
            timeout=600,
        )
        if not result.success:
            self._raise_file_error(result.stderr, file)

    @overload
    async def read_file(self, file: str, text: Literal[True] = True) -> str: ...

    @overload
    async def read_file(self, file: str, text: Literal[False]) -> bytes: ...

    async def read_file(self, file: str, text: bool = True) -> str | bytes:
        size = await _run_clean(
            self.cfg,
            [*self._exec_prefix(None, None, None), "stat", "-L", "-c", "%s %F", "--", file],
            timeout=120,
        )
        if not size.success:
            self._raise_file_error(size.stderr, file)
        parts = size.stdout.strip().split(" ", 1)
        if len(parts) == 2 and parts[1] == "directory":
            raise IsADirectoryError(file)
        limit = SandboxEnvironmentLimits.MAX_READ_FILE_SIZE
        if parts and parts[0].isdigit() and int(parts[0]) > limit:
            raise OutputLimitExceededError(limit_str=f"{limit} bytes", truncated_output=None)
        result = await _run_clean(
            self.cfg,
            [*self._exec_prefix(None, None, None), "cat", "--", file],
            text=False,
            timeout=600,
        )
        if not result.success:
            self._raise_file_error(result.stderr.decode("utf-8", errors="replace"), file)
        if text:
            return result.stdout.decode("utf-8")  # raises UnicodeDecodeError like other providers
        return result.stdout

    def default_polling_interval(self) -> float:
        return 0.2

    @staticmethod
    def _raise_file_error(stderr: str, file: str) -> None:
        if "No such file" in stderr:
            raise FileNotFoundError(file)
        if "Is a directory" in stderr:
            raise IsADirectoryError(file)
        if "Permission denied" in stderr:
            raise PermissionError(file)
        raise RuntimeError(f"apptainer file operation failed for {file}: {stderr.strip()}")
