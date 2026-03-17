def select_model(question: str) -> dict:
    text = (question or "").strip()
    lower = text.lower()

    if not text:
        return {
            "model": "llama3.1",
            "reason": "empty fallback",
            "route": "default"
        }

    coding_keywords = [
        "python", "code", "coding", "bug", "fix", "debug", "function",
        "class", "script", "api", "flask", "json", "route", "router",
        "寫程式", "代碼", "程式", "修錯", "除錯", "函式", "腳本"
    ]

    lite_keywords = [
        "yes or no", "分類", "判斷", "選哪個", "要不要", "which one",
        "quick", "fast", "簡單回答", "簡答"
    ]

    planning_keywords = [
        "plan", "architecture", "design", "system", "agent", "roadmap",
        "規劃", "架構", "設計", "系統", "路線圖", "步驟", "流程", "工程"
    ]

    if any(keyword in lower for keyword in coding_keywords) or any(keyword in text for keyword in coding_keywords):
        return {
            "model": "zero_coder:latest",
            "reason": "coding task",
            "route": "coder"
        }

    if any(keyword in lower for keyword in lite_keywords) or any(keyword in text for keyword in lite_keywords):
        return {
            "model": "zero_lite:latest",
            "reason": "lightweight classification task",
            "route": "lite"
        }

    if any(keyword in lower for keyword in planning_keywords) or any(keyword in text for keyword in planning_keywords):
        return {
            "model": "zero_general:latest",
            "reason": "planning or architecture task",
            "route": "general"
        }

    return {
        "model": "llama3.1",
        "reason": "default general chat",
        "route": "default"
    }