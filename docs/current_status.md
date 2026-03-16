# ZERO AI Current Status

## 已完成
- Flask API 基本服務可正常啟動
- `/` 首頁路由可正常回應
- `/health` 健康檢查路由可正常回應
- `/echo` POST 測試路由可正常回應
- `/status` 系統狀態路由可正常回應
- 可透過 ZERO CLI 自動新增 GET route
- 可透過 ZERO CLI 自動新增 POST route
- `/test_verify` 已驗證成功
- `/echo_data` 已驗證成功
- 已將 AI 請求處理邏輯抽到 `core/ai_handler.py`
- 已建立 `intent_parser -> tool_router -> tool_registry` Agent 骨架
- `/ai/ask` 已可呼叫工具：
  - `list_routes`
  - `read_file`
  - `restart_flask`
- 已接入 Ollama LLM gateway，做為非工具型問題的回覆後端

## 目前架構
- `app.py`
  - Flask 對外 API 入口
- `core/ai_handler.py`
  - 處理 `/ai/ask`，先判斷工具，再 fallback 到 LLM
- `core/intent_parser.py`
  - 規則式意圖解析
- `core/tool_router.py`
  - 工具分派
- `core/tool_registry.py`
  - 工具註冊中心
- `core/llm_client.py`
  - 本地 LLM gateway（Ollama）
- `docs/`
  - 專案狀態與規劃文件

## 目前限制
- intent parser 仍以規則式為主
- `/ai/ask` 尚未讓 LLM 主導工具選擇
- 工具數量仍少
- 尚未建立 Planner / Executor
- 尚未建立長期記憶整合流程
- 尚未建立完整錯誤處理與日誌機制

## 下一步
1. 確認 Ollama 路徑可通並成功回答一般問題
2. 新增可修改平台本身的工具：
   - `add_flask_route`
   - `add_flask_post_route`
   - `remove_flask_route`
3. 讓 LLM 參與工具選擇
4. 建立 Planner / Executor 骨架
5. 持續把架構知識沉澱到本地 docs