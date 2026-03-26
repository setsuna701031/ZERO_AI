import json
import re
import requests


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


class LLMClient:
    def __init__(self, model: str = "qwen:7b", timeout: int = 120):
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }

        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return str(data.get("response", "")).strip()
        except Exception as exc:
            return f"LLM_ERROR: {exc}"

    def generate_json(self, prompt: str) -> dict:
        raw = self.generate(prompt)

        if raw.startswith("LLM_ERROR:"):
            return {
                "success": False,
                "raw": raw,
                "data": None,
                "error": raw
            }

        text = raw.strip()

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1 and end >= start:
            text = text[start:end + 1]

        try:
            parsed = json.loads(text)
            return {
                "success": True,
                "raw": raw,
                "data": parsed,
                "error": ""
            }
        except Exception as exc:
            return {
                "success": False,
                "raw": raw,
                "data": None,
                "error": f"JSON parse failed: {exc}"
            }

    def extract_python_code(self, text: str) -> str:
        raw = str(text or "").strip()

        if not raw:
            return ""

        if raw.startswith("LLM_ERROR:"):
            return ""

        # Case 1: fenced code block
        fenced = re.search(r"```(?:python|py)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
        if fenced:
            code = fenced.group(1).strip()
            return code

        # Remove very common lead-in lines
        lines = raw.splitlines()

        cleaned_lines = []
        skip_prefixes = [
            "here is the corrected python code",
            "here's the corrected python code",
            "here is the python code",
            "here's the python code",
            "corrected python code",
            "python code:",
            "code:",
            "sure,",
        ]

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            if any(lower.startswith(prefix) for prefix in skip_prefixes):
                continue

            cleaned_lines.append(line)

        candidate = "\n".join(cleaned_lines).strip()

        # If explanatory text exists after a valid first statement block,
        # keep only lines that look like Python code-ish lines.
        codeish = []
        for line in candidate.splitlines():
            stripped = line.strip()

            if not stripped:
                codeish.append(line)
                continue

            lower = stripped.lower()

            if lower.startswith("this is ") or lower.startswith("when run ") or lower.startswith("it will "):
                break

            looks_like_code = (
                stripped.startswith("import ")
                or stripped.startswith("from ")
                or stripped.startswith("print(")
                or stripped.startswith("def ")
                or stripped.startswith("class ")
                or stripped.startswith("if ")
                or stripped.startswith("for ")
                or stripped.startswith("while ")
                or stripped.startswith("try:")
                or stripped.startswith("except ")
                or stripped.startswith("with ")
                or stripped.startswith("return ")
                or stripped.startswith("#")
                or stripped.startswith("@")
                or stripped.startswith("async ")
                or stripped.startswith("await ")
                or "=" in stripped
                or stripped.endswith(":")
                or stripped in ["pass", "break", "continue"]
            )

            if looks_like_code:
                codeish.append(line)
            else:
                # stop at obvious non-code explanation
                if len(codeish) > 0:
                    break

        final_code = "\n".join(codeish).strip()

        if final_code:
            return final_code

        return candidate