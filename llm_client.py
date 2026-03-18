# llm_client.py
import json
from typing import Any, Dict

import requests


class LocalLLMClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:7b",
        timeout: int = 120,
        debug: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.debug = debug

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }

        try:
            if self.debug:
                print("[LLM DEBUG] POST", url)
                print("[LLM DEBUG] model =", self.model)

            resp = requests.post(url, json=payload, timeout=self.timeout)

            if self.debug:
                print("[LLM DEBUG] status_code =", resp.status_code)

            resp.raise_for_status()

            data = resp.json()

            if self.debug:
                print("[LLM DEBUG] raw_response =", json.dumps(data, ensure_ascii=False, indent=2))

            message = data.get("message", {})
            content = message.get("content", "")

            if isinstance(content, str) and content.strip():
                return content.strip()

            return ""

        except requests.HTTPError as e:
            if self.debug:
                print(f"[LLM ERROR] HTTP error: {e}")
                try:
                    print("[LLM ERROR] response text =", resp.text)
                except Exception:
                    pass
            return ""

        except Exception as e:
            if self.debug:
                print(f"[LLM ERROR] chat failed: {e}")
            return ""

    def ask_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        raw = self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )

        if not raw:
            return {}

        try:
            return json.loads(raw)
        except Exception:
            pass

        raw = raw.strip()

        if "```json" in raw:
            try:
                start = raw.index("```json") + len("```json")
                end = raw.index("```", start)
                candidate = raw[start:end].strip()
                return json.loads(candidate)
            except Exception:
                pass

        if "```" in raw:
            try:
                parts = raw.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("{") and part.endswith("}"):
                        return json.loads(part)
            except Exception:
                pass

        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = raw[start:end + 1]
                return json.loads(candidate)
        except Exception:
            pass

        if self.debug:
            print("[LLM ERROR] ask_json parse failed.")
            print(raw)

        return {}