\# DAG Scheduler



The DAG scheduler determines which tasks are ready to run based on dependency completion.



\---



\# Task States



Tasks can be in the following states:



\* queued

\* blocked

\* running

\* finished

\* failed



\---



\# Dependency Logic



A task is ready when all dependencies are finished.



Otherwise the task is blocked.



\---



\# Scheduler Flow



for each task:

if dependencies finished:

task → queued

else:

task → blocked



\---



\# Scheduler Queue



Once a task becomes ready, it is pushed into the scheduler queue where the runner can execute it.



