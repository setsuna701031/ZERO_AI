# run_zero.py
"""
ZERO One-Command Runner

Purpose:
- Start the current event-driven ZERO stack with one command.
- Replace the manual 4-terminal workflow during local testing.

It starts:
1. app.py                         -> ZERO CLI / core process
2. core.watch.file_watcher        -> watches workspace/inbox
3. core.watch.file_trigger_handler-> converts file events into ZERO tasks
4. core.watch.auto_task_runner    -> runs queued tasks through bounded task loop

Usage:
    python run_zero.py

Optional:
    python run_zero.py --no-app
    python run_zero.py --debug
    python run_zero.py --watch-dir workspace/inbox
    python run_zero.py --poll-seconds 2
    python run_zero.py --max-cycles 5

Stop:
    Ctrl+C
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_WATCH_DIR = "workspace/inbox"
DEFAULT_OUTPUT_DIR = "workspace/shared"


@dataclass
class ManagedProcess:
    name: str
    command: List[str]
    process: Optional[subprocess.Popen] = None


def _ensure_dirs(watch_dir: str, output_dir: str) -> None:
    (ROOT_DIR / watch_dir).mkdir(parents=True, exist_ok=True)
    (ROOT_DIR / output_dir).mkdir(parents=True, exist_ok=True)


def _build_env() -> Dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    root_text = str(ROOT_DIR)
    if existing:
        if root_text not in existing.split(os.pathsep):
            env["PYTHONPATH"] = root_text + os.pathsep + existing
    else:
        env["PYTHONPATH"] = root_text
    return env


def _reader_thread(name: str, stream) -> None:
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            print(f"[{name}] {line.rstrip()}", flush=True)
    except Exception as exc:
        print(f"[{name}] reader stopped: {exc}", flush=True)


def _start_process(item: ManagedProcess, env: Dict[str, str]) -> None:
    print(f"[runner] starting {item.name}: {' '.join(item.command)}", flush=True)
    item.process = subprocess.Popen(
        item.command,
        cwd=str(ROOT_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE if item.name == "app" else subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    if item.process.stdout is not None:
        thread = threading.Thread(
            target=_reader_thread,
            args=(item.name, item.process.stdout),
            daemon=True,
        )
        thread.start()


def _stop_process(item: ManagedProcess, timeout: float = 5.0) -> None:
    proc = item.process
    if proc is None:
        return

    if proc.poll() is not None:
        return

    print(f"[runner] stopping {item.name}", flush=True)

    try:
        if os.name == "nt":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
    except Exception:
        pass

    try:
        proc.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        print(f"[runner] killing {item.name}", flush=True)
        proc.kill()
    except Exception:
        pass


def _is_alive(item: ManagedProcess) -> bool:
    proc = item.process
    return proc is not None and proc.poll() is None


def _make_processes(args: argparse.Namespace) -> List[ManagedProcess]:
    python = sys.executable
    processes: List[ManagedProcess] = []

    if not args.no_app:
        processes.append(
            ManagedProcess(
                name="app",
                command=[python, "app.py"],
            )
        )

    watcher_cmd = [
        python,
        "-m",
        "core.watch.file_watcher",
        "--watch-dir",
        args.watch_dir,
        "--output-dir",
        args.output_dir,
        "--poll-seconds",
        str(args.poll_seconds),
    ]
    if args.debug:
        watcher_cmd.append("--debug")
    if args.emit_existing:
        watcher_cmd.append("--emit-existing")

    processes.append(
        ManagedProcess(
            name="watcher",
            command=watcher_cmd,
        )
    )

    trigger_cmd = [
        python,
        "-m",
        "core.watch.file_trigger_handler",
        "--poll-seconds",
        str(args.poll_seconds),
    ]
    if args.debug:
        trigger_cmd.append("--debug")

    processes.append(
        ManagedProcess(
            name="trigger",
            command=trigger_cmd,
        )
    )

    auto_runner_cmd = [
        python,
        "-m",
        "core.watch.auto_task_runner",
        "--poll-seconds",
        str(args.poll_seconds),
        "--max-cycles",
        str(args.max_cycles),
    ]
    if args.debug:
        auto_runner_cmd.append("--debug")

    processes.append(
        ManagedProcess(
            name="auto_runner",
            command=auto_runner_cmd,
        )
    )

    return processes


def _print_banner(args: argparse.Namespace) -> None:
    print("", flush=True)
    print("========================================", flush=True)
    print(" ZERO One-Command Runner", flush=True)
    print("========================================", flush=True)
    print(f" root       : {ROOT_DIR}", flush=True)
    print(f" watch_dir  : {args.watch_dir}", flush=True)
    print(f" output_dir : {args.output_dir}", flush=True)
    print(f" poll       : {args.poll_seconds}s", flush=True)
    print(f" max_cycles : {args.max_cycles}", flush=True)
    print("", flush=True)
    print("Drop a .txt or .md file into:", flush=True)
    print(f"  {ROOT_DIR / args.watch_dir}", flush=True)
    print("", flush=True)
    print("Expected flow:", flush=True)
    print("  file -> watcher -> trigger -> queued task -> auto runner -> summary output", flush=True)
    print("", flush=True)
    print("Press Ctrl+C to stop all processes.", flush=True)
    print("========================================", flush=True)
    print("", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the local ZERO event-driven stack")
    parser.add_argument("--watch-dir", default=DEFAULT_WATCH_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--max-cycles", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--emit-existing", action="store_true")
    parser.add_argument("--no-app", action="store_true")
    parser.add_argument("--restart-crashed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _ensure_dirs(args.watch_dir, args.output_dir)
    _print_banner(args)

    env = _build_env()
    processes = _make_processes(args)

    try:
        for item in processes:
            _start_process(item, env)
            time.sleep(0.4)

        while True:
            for item in processes:
                proc = item.process
                if proc is None:
                    continue

                code = proc.poll()
                if code is None:
                    continue

                print(f"[runner] process exited: {item.name} code={code}", flush=True)

                if args.restart_crashed:
                    print(f"[runner] restarting {item.name}", flush=True)
                    _start_process(item, env)

            time.sleep(1.0)

    except KeyboardInterrupt:
        print("", flush=True)
        print("[runner] Ctrl+C received; shutting down", flush=True)

    finally:
        for item in reversed(processes):
            _stop_process(item)

    print("[runner] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
