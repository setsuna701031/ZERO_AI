\# ZERO Dev Log



\---



\## Case 1 - scheduler crash



錯誤：

執行 task\_resume 後 crash



ZERO 表現：

⚠️ 找到問題，但需要我手動覆蓋檔案



步數：

4



\---



\## Case 2 - CLI 指令錯誤



錯誤：

task\_list 指令跑錯路徑



ZERO 表現：

✅ 修好



步數：

2



\---



\## Case 3 - 模組路徑錯誤



錯誤：

import 路徑不一致



ZERO 表現：

⚠️ 修一半，需要我補



步數：

3



\---



\# Phase: System Convergence



\---



\## 2026-04-10



\### 🎯 主題



主流程收束（Planner 接入 / Agent Loop 穩定 / Flow 修正）



\---



\### 🧩 今日重點工作



\* 收斂主流程：Router → Planner → Agent Loop → Executor

\* 排查 `command / task` 分流問題

\* 修正 `submit` 指令未正確進入流程

\* 檢查 Planner 接入狀態（是否穩定觸發）

\* 排查 `agent\_loop` 報錯問題

\* 檢查舊邏輯 / fallback 殘留干擾

\* 確認 trace viewer（demo素材）可用並已保存



\---



\### ⚠️ 遇到的問題



\* `submit` 指令未穩定進入預期流程

\* `agent\_loop` 出現報錯（非單點問題）

\* Planner 有時未觸發或出現重複輸出（例：`### USING NEW PLANNER`）

\* 舊流程與新流程同時存在，導致行為不一致

\* 系統整體行為仍不夠可預測



\---



\### 🧠 關鍵觀察



\* 問題不是單一檔案，而是「主流程多節點耦合問題」

\* 當前瓶頸不在功能，而在「流程收斂與穩定性」

\* 舊邏輯殘留是主要干擾來源

\* 系統仍處於「能動 → 穩定動」過渡期



\---



\### 📊 當前狀態



\* 核心主流程尚未完全收束

\* Agent Loop / Planner / Executor 尚在對齊

\* Trace viewer 已可用（作為觀測與未來 demo 基礎）

\* GitHub / Demo 暫緩整理，優先專注穩定性



\---



\### ▶️ 下一步



\* 固定單一路徑（避免多流程並存）

\* 確認入口 → Agent Loop → Planner → Executor 完整串接

\* 清理舊邏輯與 fallback

\* 提升任務執行穩定性（重跑一致性）

\* 完成主流程收束後，再整理 demo / GitHub



\---



\### 🧭 階段定位



當前處於：

「能動 → 能穩定動（收束期）」



此階段為系統最關鍵階段，優先級高於功能擴展與展示。

# ZERO Dev Log (整理版)

## 狀態結論
核心主流程已打通，但仍在收束期（能動 → 穩定動）

---

## 已完成（重要）

- Router → Planner → Agent Loop → Executor 主流程串接完成
- command / task 分流基本可用
- scheduler 可執行任務
- executor 有實際落地（非假執行）
- trace viewer 可用（已具備 demo 素材）

---

## 已修問題

- task_list 路徑錯誤（已修）
- scheduler crash（部分修復）
- import 路徑問題（部分修復）

---

## 核心問題（昨天卡點）

- submit 指令流程不穩
- agent_loop 偶發報錯
- planner 觸發不穩 / 重複輸出
- 舊流程與新流程並存（最大問題）
- 系統行為不可預測

---

## 關鍵判斷（很重要）

問題不是功能缺失，而是：

👉 主流程未完全收斂（多路徑干擾）

---

## 當前階段

系統處於：

👉 收束期（Convergence Phase）

不是開發期，也不是產品期

# 2026-04-12

## 主題

Document Flow 主線重收斂，完成 action-items extraction flow

---

## 今日完成

- 決定文件流程主線從單純 summary，改為更有展示價值的 `input.txt -> action_items.txt`
- 釐清目前 document flow 不是獨立 `document_flow.py`，而是：
  `app.py -> agent_loop.py -> planner.py -> step_executor.py -> step_handlers.py`
- 修通 action-items extraction flow 所需主路徑
- 修正多個關鍵卡點：
  - PowerShell 直接把自然語句當 shell 指令執行
  - planner 把整句誤吞成 read path
  - router direct route 先攔截，導致 planner document flow 沒生效
  - single-shot 寫檔時預設走 sandbox，因沒有 `task_id` 而報錯
- 讓 document flow 輸出改為寫入 `workspace/shared`
- 升級 action-items prompt，改善 due 抽取品質
- 完成 3 組 action-items extraction 測試
- 整理並保留 demo 資產與案例檔案

---

## 今日驗證結果

### Case 1
- `input.txt -> action_items.txt` 成功跑通
- 可正常抽出：
  - owner
  - task
  - due
- 功能閉環成立

### Case 2
- 初版可抓 owner / task，但 `by Monday` 未穩定抽出
- 升級 prompt 後已能正確抓到：
  - `By Monday`
  - `This afternoon`
  - `Tomorrow`

### Case 3
- 未把純事件描述誤判成 action item
- 升級 prompt 後已能抓到：
  - `Today`
- 對沒有明確 owner / due 的項目，能合理落到：
  - `Unassigned`
  - `Not specified`

---

## 今日產出

### 功能成果
- `input.txt -> action_items.txt` flow v1.1 已完成
- 已達到：
  - 可執行
  - 可重跑
  - 多案例可驗證
  - 可展示

### 已保留的 demo 資產
- `input_case_1.txt`
- `input_case_2.txt`
- `input_case_3.txt`
- `action_items_case_1.txt`
- `action_items_case_2.txt`
- `action_items_case_3.txt`
- `trace_action_items_success_1.png`
- `trace_action_items_batch_runs.png`

---

## 關鍵判斷

今天的進展不是單純「做出一個 txt 檔」而已，而是：

**把 ZERO 的 document flow，從摘要型流程，推進成可從非結構化 notes 中抽取可執行事項的文件能力。**

這比單純 summary 更接近真正可展示的 agent 工作。

---

## 當前狀態

- action-items extraction flow 主線已打通
- 多案例驗證已完成
- due 抽取品質已明顯改善
- 功能本身已具備展示價值
- trace 展示層尚未同步完成

---

## 下一步

- 補 trace，讓 Trace Viewer 正確顯示：
  - `read_input`
  - `extract_action_items`
  - `write_action_items`
- 讓 action-items flow 在 trace viewer 內也具備展示力

---

## 階段定位

當前處於：

**Document Flow 可展示化收束階段**

不是再擴功能，而是把已打通的能力收成穩定、可驗證、可展示的資產。



