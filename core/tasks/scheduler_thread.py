import threading
import time


class SchedulerThread:
    """
    背景 Scheduler 執行緒
    會每隔 interval 秒執行 scheduler.run_one()
    """

    def __init__(self, scheduler, interval=1):
        self.scheduler = scheduler
        self.interval = interval
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        print("[SchedulerThread] started")

    def stop(self):
        self.running = False
        print("[SchedulerThread] stopped")

    def loop(self):
        while self.running:
            try:
                # 重要：每次先 rebuild queue
                if hasattr(self.scheduler, "rebuild_queue_from_repo"):
                    self.scheduler.rebuild_queue_from_repo()

                result = self.scheduler.run_one()

                if result:
                    if result.get("task_id") is not None or result.get("ok"):
                        print("[SchedulerThread]", result)

            except Exception as e:
                print("[SchedulerThread ERROR]", e)

            time.sleep(self.interval)