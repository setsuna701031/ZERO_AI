import subprocess
import sys
import time
import yaml
from pathlib import Path

CONFIG_PATH = Path("config/default.yaml")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def spawn(cmd, name):
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )


def log_filter(line):
    line = line.strip()

    # 精簡輸出（只留關鍵）
    if "file_detected" in line:
        return "[watcher] file detected"

    if "task submitted" in line:
        return "[trigger] task submitted"

    if '"status": "finished"' in line:
        return "[auto_runner] task finished"

    if '"action": "idle"' in line:
        return "[auto_runner] idle"

    return None


def stream_output(p, name):
    for line in p.stdout:
        msg = log_filter(line)
        if msg:
            print(msg)


def main():
    config = load_config()

    watch_dir = config["watch"]["inbox"]
    output_dir = config["watch"]["shared"]
    poll = config["watch"]["poll_seconds"]
    max_cycles = config["runner"]["max_cycles"]

    print("=== ZERO Runner (quiet mode) ===")
    print(f"watch_dir: {watch_dir}")
    print(f"output_dir: {output_dir}")
    print("Drop file into inbox to trigger.\n")

    processes = []

    try:
        # app
        processes.append(spawn([sys.executable, "app.py"], "app"))
        time.sleep(1)

        # watcher
        processes.append(spawn([
            sys.executable,
            "-m", "core.watch.file_watcher",
            "--watch-dir", watch_dir,
            "--output-dir", output_dir,
            "--poll-seconds", str(poll)
        ], "watcher"))

        time.sleep(1)

        # trigger
        processes.append(spawn([
            sys.executable,
            "-m", "core.watch.file_trigger_handler",
            "--poll-seconds", str(poll)
        ], "trigger"))

        time.sleep(1)

        # auto runner
        processes.append(spawn([
            sys.executable,
            "-m", "core.watch.auto_task_runner",
            "--poll-seconds", str(poll),
            "--max-cycles", str(max_cycles)
        ], "runner"))

        # 並行讀輸出
        while True:
            for p in processes:
                stream_output(p, "proc")
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n[runner] stopping...")
        for p in processes:
            p.terminate()


if __name__ == "__main__":
    main()