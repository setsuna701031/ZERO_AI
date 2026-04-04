# core/runtime/task_queue.py

from collections import deque


class TaskQueue:
    def __init__(self):
        self.ready_queue = deque()
        self.in_queue = set()

    def enqueue(self, task_name):
        if task_name not in self.in_queue:
            self.ready_queue.append(task_name)
            self.in_queue.add(task_name)

    def dequeue(self):
        if not self.ready_queue:
            return None
        task_name = self.ready_queue.popleft()
        self.in_queue.remove(task_name)
        return task_name

    def remove(self, task_name):
        if task_name in self.in_queue:
            self.in_queue.remove(task_name)
            try:
                self.ready_queue.remove(task_name)
            except ValueError:
                pass

    def is_empty(self):
        return len(self.ready_queue) == 0

    def snapshot(self):
        return list(self.ready_queue)