\# ZERO



ZERO is a local task-oriented AI runtime focused on executable task flows, workspace actions, and verifiable agent behavior.



ZERO 的方向不是一般聊天機器人，而是往「本地可控、可驗證、可執行任務」的 AI Task Operating System 核心推進。



\---



\## Current Focus



目前 ZERO 正在朝這幾個方向演進：



\- Local-first AI runtime

\- Task-oriented execution flow

\- Workspace action execution

\- Verifiable success / failure behavior

\- Multi-step task execution

\- Open-core architecture path



\---



\## What ZERO Can Already Do



以下是目前已經有實測證據支撐的能力：



\- 建立任務並執行基本 task flow

\- 執行 workspace actions

\- 建立資料夾

\- 建立檔案並寫入內容

\- 將任務結果寫入 execution log

\- 將 success / failure 與真實工具結果對齊

\- 執行基本 multi-step workspace flow



目前已驗證的方向，不是單純聊天，而是：



1\. 接收任務意圖

2\. 進入 task execution flow

3\. 呼叫工具

4\. 在 workspace 中產生真實結果

5\. 回傳 success / failure 與 execution log



\---



\## Verified Demo Evidence



\### 1. Task success / finished

成功案例已驗證，任務完成時可正確顯示 finished 結果。



!\[Task Success Finished](docs/images/ZERO\_TaskOS\_Success\_TaskFinished.png)



\### 2. Retry / permanent failure

失敗案例已驗證，當任務無法完成時，系統可正確反映 permanent failure，而不是假成功。



!\[Retry Permanent Failure](docs/images/ZERO\_TaskOS\_Retry\_PermanentFailure.png)



\### 3. Basic multi-step workspace execution

目前已完成基本 multi-step workspace flow 驗證：



\- 建立資料夾

\- 在資料夾中建立檔案

\- 寫入內容

\- 產生實體落地結果



Demo video:



\[ZERO\_TaskOS\_MultiStep\_Workspace\_Demo.mp4](docs/images/ZERO\_TaskOS\_MultiStep\_Workspace\_Demo.mp4)



\---



\## Current Status



目前 ZERO 比較接近這個狀態：



\- Single-step execution: verified

\- Basic workspace tool execution: verified

\- Success / failure alignment: verified

\- Basic multi-step workspace flow: verified

\- Planner-driven deeper orchestration: in progress

\- Retry / resume / verifier / richer multi-step flow: in progress



也就是說，ZERO 已經不是概念展示或聊天殼，而是正在形成一個真正可執行任務的本地 AI runtime 核心。



\---



\## Architecture Snapshot



目前的核心模組方向包含：



\- Router

\- Planner

\- Step Executor

\- Scheduler

\- Task Runtime

\- Memory

\- Command

\- Tool Registry

\- Workspace Tool

\- Agent Loop



ZERO 現在的重點不是把模組名稱堆多，而是把它們真正接成一條可驗證的 execution chain。



\---



\## Design Direction



ZERO 的目標不是做一個只會對話的 AI，而是做一個：



\- 可本地執行

\- 可審查

\- 可追蹤

\- 可驗證

\- 可逐步擴展到更強 task orchestration

\- 保留未來企業化與部署路線



這條路會優先重視：



\- controllability

\- inspectability

\- verifiable execution

\- extensibility

\- open-core friendliness



\---



\## Near-Term Roadmap



下一階段主線會放在：



\- Planner 正式化 step 產生能力

\- 更穩定的 multi-step task execution

\- task status lifecycle

\- task retry

\- task resume

\- verifier / reflection

\- memory-aware planning

\- deployment-oriented architecture path



\---



\## Open-Core Direction



ZERO 預計採取偏 open-core 的路線：



\- 公開核心 execution / task runtime 骨架

\- 持續演進 planner / orchestration / runtime 主線

\- 保留後續更高價值的進階層、部署層與企業化路線



這代表目前開源的重點是：



\- 展示可驗證的核心能力

\- 建立技術可信度

\- 讓外界看見 ZERO 的執行主幹



而不是一次公開所有未來路線。



\---



\## Repository Note



目前這個版本是 ZERO 的一個可驗證節點：



\- 已有真實 execution evidence

\- 已有 success / failure 對齊證據

\- 已有 basic multi-step workspace demo

\- 主線仍在持續快速推進



後續版本會持續往更完整的 task OS 與 agent runtime 能力演進。



\---



\## Demo / Documentation



更多展示與階段說明可見：



\- \[docs/demo.md](docs/demo.md)



\---



\## Status Summary



一句話描述現在的 ZERO：



> A local, task-oriented AI runtime that is already capable of verified workspace execution and is evolving toward a deeper agent task operating system core.

