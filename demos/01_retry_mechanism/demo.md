\# Demo - Retry Mechanism



\## Goal

Test task retry and requeue behavior.



\## Steps

1\. Create task with max\_retries

2\. Dispatch task

3\. Fail task

4\. Requeue on retry

5\. Check queue next task



\## Result

Task retry count increased.

Task requeued successfully.

Task appears again in queue.



\## Conclusion

Retry and requeue mechanism works correctly.

