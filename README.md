# ZERO AI - 自主工程代理人 (Autonomous Engineering Agent)

ZERO 是一個基於本地語言模型 (LLM) 的自主 AI 系統。它不僅能理解對話，更具備執行計畫、編寫程式碼與自動化操作本地檔案的能力。

## 🚀 核心亮點
- **100% 本地化隱私**：基於 Ollama 運行，數據不外流。
- **自主執行環 (Self-Execution Loop)**：AI 能夠將複雜任務拆解為多個步驟，並自動調用工具執行。
- **沙盒工作區 (Sandbox)**：所有操作限制在 `zero_workspace` 內，兼顧功能與系統安全。
- **自動化維運**：已實測可自主編寫 Python 監控腳本並回傳實時系統數據 (如 CPU 使用率)。

## 🛠️ 技術架構
- **大腦 (Core)**：採用 ReAct 推理框架 (Planner + Executor)。
- **後端 (Server)**：Flask API 驅動的工具註冊表 (Tool Registry)。
- **模型**：支援 Qwen, Llama 3 等本地高性能模型。

## 📂 專案結構
- `core/`: AI 的決策中心與計畫引擎。
- `tools/`: 各式執行工具（檔案讀寫、Python 腳本執行）。
- `zero_workspace/`: AI 的專屬實驗室。

## 📈 未來展望
- 增加 Web 爬蟲工具組。
- 實現報錯自動修復 (Self-Healing) 機制。
- 支援更複雜的數據分析與視覺化報表生成。
