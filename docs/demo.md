\# ZERO Demo



這份文件用來整理目前 ZERO 已完成的可驗證成果，以及這個階段的展示重點。



\---



\## Demo Positioning



目前 ZERO 的展示重點不是一般聊天能力，而是：



\- 本地 task execution

\- workspace action execution

\- verifiable success / failure behavior

\- basic multi-step task flow



換句話說，這一階段的 ZERO 重點在於：



\*\*讓 AI 任務不只會說，而是真的會做。\*\*



\---



\## What Has Been Verified



以下內容已經有實測證據支撐。



\### 1. Success path

已驗證任務成功時，系統可正確回傳 success / finished。



展示素材：



!\[Task Success Finished](images/ZERO\_TaskOS\_Success\_TaskFinished.png)



\---



\### 2. Failure path

已驗證任務失敗時，系統可正確反映 permanent failure，而不是表面成功。



展示素材：



!\[Retry Permanent Failure](images/ZERO\_TaskOS\_Retry\_PermanentFailure.png)



\---



\### 3. Basic multi-step workspace flow

已驗證基本 multi-step workspace 任務鏈。



目前已展示的流程包括：



1\. 建立資料夾

2\. 在資料夾中建立檔案

3\. 寫入內容

4\. 產生實際 workspace 落地結果



展示影片：



\[ZERO\_TaskOS\_MultiStep\_Workspace\_Demo.mp4](images/ZERO\_TaskOS\_MultiStep\_Workspace\_Demo.mp4)



\---



\## Why This Stage Matters



這個階段的重要性不在於功能數量，而在於 ZERO 已經開始具備：



\- 真實工具呼叫

\- 真實 workspace 變更

\- 真實 execution log

\- success / failure 對齊

\- 從單步走向多步任務鏈



這代表 ZERO 已經脫離純概念或聊天殼階段，開始進入可驗證成果期。



\---



\## Evidence Summary



目前已能證明：



\- ZERO 可以建立與執行 task

\- ZERO 可以透過 workspace tool 產生真實檔案系統變更

\- ZERO 可以正確標示成功結果

\- ZERO 可以正確標示失敗結果

\- ZERO 已能執行基本 multi-step workspace task flow



\---



\## Current Technical Interpretation



目前這個版本的 ZERO，比較接近：



\- local AI task runtime

\- workspace execution core

\- verified task-flow prototype

\- early-stage task operating system backbone



它還不是完整成熟的平台，但已經是一個可被驗證、可被展示、可持續深推的核心節點。



\---



\## What Is Next



下一階段預計繼續推進：



\- Planner 正式化 step 產生能力

\- 更強的 multi-step task orchestration

\- task status lifecycle

\- retry / resume

\- verifier / reflection

\- memory-aware planning

\- 更完整的 runtime 與 deployment 路線



\---



\## Short Summary



一句話總結目前這個 demo 階段：



> ZERO has already verified real task execution behavior in a local workspace, including success cases, failure cases, and a basic multi-step execution flow.

