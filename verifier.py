from typing import Any, Dict, List, Optional


class Verifier:
    """
    ZERO 最小版驗證器
    """

    def verify_execution_result(
        self,
        user_task: str,
        execute_result: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        checks: List[str] = []

        if not isinstance(execute_result, dict):
            return self._build_verify_result(
                success=False,
                summary="Verification failed.",
                checks=["execute result is not a valid dict"],
                error="Execution result must be a dictionary."
            )

        success_ok = self._check_success_flag(execute_result)
        if success_ok:
            checks.append("execute reported success")
        else:
            checks.append("execute did not report success")

        evidence_ok = self._check_evidence(execute_result)
        if evidence_ok:
            checks.append("evidence is present")
        else:
            checks.append("missing evidence")

        scope_ok = self._check_scope_match(user_task, execute_result)
        if scope_ok:
            checks.append("result matches user task")
        else:
            checks.append("result may not match user task")

        changed_ok = self._check_changed_targets(user_task, execute_result)
        if changed_ok:
            checks.append("changed targets are acceptable")
        else:
            checks.append("changed targets are missing or inconsistent")

        final_success = success_ok and evidence_ok and scope_ok and changed_ok

        if final_success:
            return self._build_verify_result(
                success=True,
                summary="Verification passed.",
                checks=checks,
                error=None
            )

        error_messages: List[str] = []
        if not success_ok:
            error_messages.append("execute did not report success")
        if not evidence_ok:
            error_messages.append("execution result did not include enough evidence")
        if not scope_ok:
            error_messages.append("execution result may not match the original task")
        if not changed_ok:
            error_messages.append("changed targets are missing or inconsistent")

        return self._build_verify_result(
            success=False,
            summary="Verification failed.",
            checks=checks,
            error="; ".join(error_messages)
        )

    def _check_success_flag(self, execute_result: Dict[str, Any]) -> bool:
        return execute_result.get("success") is True

    def _check_evidence(self, execute_result: Dict[str, Any]) -> bool:
        summary = execute_result.get("summary")
        evidence = execute_result.get("evidence")
        results = execute_result.get("results")

        summary_ok = isinstance(summary, str) and summary.strip() != ""
        evidence_ok = isinstance(evidence, list) and len(evidence) > 0
        results_ok = isinstance(results, list) and len(results) > 0

        return summary_ok or evidence_ok or results_ok

    def _check_scope_match(
        self,
        user_task: str,
        execute_result: Dict[str, Any]
    ) -> bool:
        if not isinstance(user_task, str) or user_task.strip() == "":
            return True

        task_text = user_task.strip().lower()
        tool_name = str(execute_result.get("tool_name", "")).strip().lower()
        summary = str(execute_result.get("summary", "")).strip().lower()
        evidence = execute_result.get("evidence", [])
        action = str(execute_result.get("action", "")).strip().lower()
        results = execute_result.get("results", [])

        combined_result_text = " ".join(
            [
                tool_name,
                action,
                summary,
                " ".join(str(x).lower() for x in evidence),
                self._flatten_results_text(results),
            ]
        ).strip()

        search_words = [
            "查一下", "查詢", "搜尋", "搜索", "幫我找", "找一下", "上網找",
            "查資料", "查規格", "查教學", "web", "search", "google", "資料"
        ]
        memory_write_words = [
            "記住", "記下來", "寫入記憶", "存記憶", "新增記憶"
        ]
        memory_list_words = [
            "查看記憶", "列出記憶", "全部記憶", "看記憶"
        ]
        memory_search_words = [
            "查記憶", "搜尋記憶", "搜索記憶", "找記憶"
        ]
        command_words = [
            "執行", "命令", "command", "shell", "run", "cmd"
        ]

        if self._contains_any(task_text, search_words):
            if tool_name == "web_search" or "search" in combined_result_text or "web" in combined_result_text:
                return True

        if self._contains_any(task_text, memory_write_words):
            if tool_name == "memory" and action == "write":
                return True
            if "memory" in combined_result_text:
                return True

        if self._contains_any(task_text, memory_list_words):
            if tool_name == "memory" and action in {"list", "read"}:
                return True
            if "memory" in combined_result_text:
                return True

        if self._contains_any(task_text, memory_search_words):
            if tool_name == "memory" and action == "search":
                return True
            if "memory" in combined_result_text:
                return True

        file_scope_ok = self._check_file_scope_match(task_text, tool_name, action, execute_result, combined_result_text)
        if file_scope_ok:
            return True

        if self._contains_any(task_text, command_words):
            if tool_name == "command":
                return True
            if (
                "execute_command" in tool_name
                or "run_command" in tool_name
                or "shell" in tool_name
                or "command" in combined_result_text
                or "execute" in combined_result_text
            ):
                return True

        task_keywords = self._extract_simple_keywords(task_text)
        if not task_keywords:
            return True

        match_count = 0
        for keyword in task_keywords:
            if keyword in combined_result_text:
                match_count += 1

        if match_count >= 1:
            return True

        if tool_name == "web_search" and self._contains_any(task_text, search_words):
            return True

        if tool_name == "memory" and "記憶" in task_text:
            return True

        if tool_name == "command" and self._contains_any(task_text, command_words):
            return True

        return False

    def _check_file_scope_match(
        self,
        task_text: str,
        tool_name: str,
        action: str,
        execute_result: Dict[str, Any],
        combined_result_text: str
    ) -> bool:
        if tool_name != "file":
            return False

        results = execute_result.get("results", [])
        changed_files = execute_result.get("changed_files", [])

        extracted_path = self._extract_file_path_from_task(task_text)
        extracted_content = self._extract_file_content_from_task(task_text)

        if self._is_file_read_task(task_text):
            if action != "read":
                return False

            if not isinstance(results, list) or not results:
                return False

            first = results[0] if isinstance(results[0], dict) else {}
            result_path = str(first.get("path", "")).strip().lower()
            has_content = "content" in first

            if not has_content:
                return False

            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                normalized_result_path = self._normalize_path_for_compare(result_path)
                if normalized_task_path and normalized_task_path not in normalized_result_path:
                    return False

            return True

        if self._is_file_list_dir_task(task_text):
            if action != "list_dir":
                return False

            if not isinstance(results, list):
                return False

            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                if normalized_task_path and normalized_task_path not in combined_result_text:
                    return False

            return True

        if self._is_file_write_task(task_text):
            if action != "write":
                return False

            if not isinstance(changed_files, list) or len(changed_files) == 0:
                return False

            first_changed = str(changed_files[0]).strip().lower()

            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                normalized_changed = self._normalize_path_for_compare(first_changed)
                if normalized_task_path and normalized_task_path not in normalized_changed:
                    return False

            if extracted_content is not None and isinstance(results, list) and results:
                first = results[0] if isinstance(results[0], dict) else {}
                result_content = str(first.get("content", ""))
                if extracted_content != result_content:
                    return False

            return True

        if self._is_file_overwrite_task(task_text):
            if action != "overwrite":
                return False

            if not isinstance(changed_files, list) or len(changed_files) == 0:
                return False

            first_changed = str(changed_files[0]).strip().lower()

            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                normalized_changed = self._normalize_path_for_compare(first_changed)
                if normalized_task_path and normalized_task_path not in normalized_changed:
                    return False

            if extracted_content is not None and isinstance(results, list) and results:
                first = results[0] if isinstance(results[0], dict) else {}
                result_content = str(first.get("content", ""))
                if extracted_content != result_content:
                    return False

            return True

        if self._is_file_safe_write_task(task_text):
            if action != "safe_write":
                return False

            if not isinstance(changed_files, list) or len(changed_files) == 0:
                return False

            first_changed = str(changed_files[0]).strip().lower()

            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                normalized_changed = self._normalize_path_for_compare(first_changed)
                if normalized_task_path and normalized_task_path not in normalized_changed:
                    return False

            if extracted_content is not None and isinstance(results, list) and results:
                first = results[0] if isinstance(results[0], dict) else {}
                result_content = str(first.get("content", ""))
                if extracted_content != result_content:
                    return False

            backup_path = str(first.get("backup_path", "")).strip()
            backup_created = execute_result.get("backup_created")
            existed_before = bool(first.get("existed_before", False))

            if existed_before and not backup_path and backup_created is not True:
                return False

            return True

        if self._is_file_append_task(task_text):
            if action != "append":
                return False

            if not isinstance(changed_files, list) or len(changed_files) == 0:
                return False

            first_changed = str(changed_files[0]).strip().lower()

            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                normalized_changed = self._normalize_path_for_compare(first_changed)
                if normalized_task_path and normalized_task_path not in normalized_changed:
                    return False

            if extracted_content is not None and isinstance(results, list) and results:
                first = results[0] if isinstance(results[0], dict) else {}
                result_content = str(first.get("content", ""))
                if extracted_content not in result_content:
                    return False

            return True

        if self._is_file_exists_task(task_text):
            if action != "exists":
                return False

            if not isinstance(results, list) or not results:
                return False

            first = results[0] if isinstance(results[0], dict) else {}

            if "exists" not in first or "type" not in first:
                return False

            result_path = str(first.get("path", "")).strip().lower()
            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                normalized_result_path = self._normalize_path_for_compare(result_path)
                if normalized_task_path and normalized_task_path not in normalized_result_path:
                    return False

            return True

        if self._is_file_mkdir_task(task_text):
            if action != "mkdir":
                return False

            if not isinstance(results, list) or not results:
                return False

            first = results[0] if isinstance(results[0], dict) else {}
            result_path = str(first.get("path", "")).strip().lower()

            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                normalized_result_path = self._normalize_path_for_compare(result_path)
                if normalized_task_path and normalized_task_path not in normalized_result_path:
                    return False

            if first.get("type") != "dir":
                return False

            return True

        if self._is_file_read_json_task(task_text):
            if action != "read_json":
                return False

            if not isinstance(results, list) or not results:
                return False

            first = results[0] if isinstance(results[0], dict) else {}
            result_path = str(first.get("path", "")).strip().lower()

            if "data" not in first:
                return False

            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                normalized_result_path = self._normalize_path_for_compare(result_path)
                if normalized_task_path and normalized_task_path not in normalized_result_path:
                    return False

            return True

        if self._is_file_write_json_task(task_text):
            if action != "write_json":
                return False

            if not isinstance(changed_files, list) or len(changed_files) == 0:
                return False

            first_changed = str(changed_files[0]).strip().lower()
            if extracted_path:
                normalized_task_path = self._normalize_path_for_compare(extracted_path)
                normalized_changed = self._normalize_path_for_compare(first_changed)
                if normalized_task_path and normalized_task_path not in normalized_changed:
                    return False

            return True

        if "file" in combined_result_text:
            return True

        return False

    def _check_changed_targets(
        self,
        user_task: str,
        execute_result: Dict[str, Any]
    ) -> bool:
        changed_files = execute_result.get("changed_files")
        tool_name = str(execute_result.get("tool_name", "")).strip().lower()
        action = str(execute_result.get("action", "")).strip().lower()

        if tool_name == "memory":
            if action in {"write", "list", "search", "read"}:
                return True

        if tool_name == "web_search":
            return True

        if tool_name == "command":
            return True

        if tool_name == "file":
            if action in {"read", "list_dir", "exists", "read_json"}:
                return True

            if action == "mkdir":
                if isinstance(changed_files, list):
                    return True
                return False

            if action in {"write", "append", "overwrite", "safe_write", "write_json"}:
                return isinstance(changed_files, list) and len(changed_files) > 0

        if isinstance(changed_files, list):
            if len(changed_files) > 0:
                return True

            write_like_words = ["write", "modify", "edit", "file", "檔案", "修改", "寫入", "覆寫"]
            combined_text = f"{tool_name} {action} {user_task}".lower()

            for word in write_like_words:
                if word in combined_text:
                    return False

            return True

        if changed_files is None:
            write_like_words = ["write", "modify", "edit", "file", "檔案", "修改", "寫入", "覆寫"]
            combined_text = f"{tool_name} {action} {user_task}".lower()

            for word in write_like_words:
                if word in combined_text:
                    return False

            return True

        return False

    def _flatten_results_text(self, results: Any) -> str:
        if not isinstance(results, list):
            return ""

        parts: List[str] = []
        for item in results:
            if isinstance(item, dict):
                for value in item.values():
                    parts.append(str(value).lower())
            else:
                parts.append(str(item).lower())
        return " ".join(parts)

    def _is_file_read_task(self, task_text: str) -> bool:
        return task_text.startswith("讀檔 ") or task_text.startswith("read file ")

    def _is_file_list_dir_task(self, task_text: str) -> bool:
        return task_text.startswith("列出資料夾 ") or task_text.startswith("list dir ")

    def _is_file_write_task(self, task_text: str) -> bool:
        return task_text.startswith("寫檔 ")

    def _is_file_overwrite_task(self, task_text: str) -> bool:
        return task_text.startswith("覆寫檔 ") or task_text.startswith("overwrite file ")

    def _is_file_safe_write_task(self, task_text: str) -> bool:
        return task_text.startswith("安全寫檔 ") or task_text.startswith("safe write ")

    def _is_file_append_task(self, task_text: str) -> bool:
        return task_text.startswith("append 檔案 ")

    def _is_file_exists_task(self, task_text: str) -> bool:
        return task_text.startswith("檢查檔案 ") or task_text.startswith("exists ")

    def _is_file_mkdir_task(self, task_text: str) -> bool:
        return task_text.startswith("建資料夾 ") or task_text.startswith("mkdir ")

    def _is_file_read_json_task(self, task_text: str) -> bool:
        return task_text.startswith("讀json ") or task_text.startswith("read json ")

    def _is_file_write_json_task(self, task_text: str) -> bool:
        return task_text.startswith("寫json ") or task_text.startswith("write json ")

    def _extract_file_path_from_task(self, task_text: str) -> str:
        if self._is_file_read_task(task_text):
            if task_text.startswith("讀檔 "):
                return task_text[3:].strip()
            if task_text.startswith("read file "):
                return task_text[10:].strip()

        if self._is_file_list_dir_task(task_text):
            if task_text.startswith("列出資料夾 "):
                return task_text[5:].strip()
            if task_text.startswith("list dir "):
                return task_text[9:].strip()

        if self._is_file_write_task(task_text):
            payload = task_text[3:].strip()
            path, _ = self._split_file_payload(payload)
            return path

        if self._is_file_overwrite_task(task_text):
            if task_text.startswith("覆寫檔 "):
                payload = task_text[4:].strip()
            else:
                payload = task_text[15:].strip()
            path, _ = self._split_file_payload(payload)
            return path

        if self._is_file_safe_write_task(task_text):
            if task_text.startswith("安全寫檔 "):
                payload = task_text[5:].strip()
            else:
                payload = task_text[11:].strip()
            path, _ = self._split_file_payload(payload)
            return path

        if self._is_file_append_task(task_text):
            payload = task_text[10:].strip()
            path, _ = self._split_file_payload(payload)
            return path

        if self._is_file_exists_task(task_text):
            if task_text.startswith("檢查檔案 "):
                return task_text[5:].strip()
            if task_text.startswith("exists "):
                return task_text[7:].strip()

        if self._is_file_mkdir_task(task_text):
            if task_text.startswith("建資料夾 "):
                return task_text[5:].strip()
            if task_text.startswith("mkdir "):
                return task_text[6:].strip()

        if self._is_file_read_json_task(task_text):
            if task_text.startswith("讀json "):
                return task_text[6:].strip()
            if task_text.startswith("read json "):
                return task_text[10:].strip()

        if self._is_file_write_json_task(task_text):
            if task_text.startswith("寫json "):
                payload = task_text[6:].strip()
            else:
                payload = task_text[11:].strip()
            path, _ = self._split_file_payload(payload)
            return path

        return ""

    def _extract_file_content_from_task(self, task_text: str) -> Optional[str]:
        if self._is_file_write_task(task_text):
            payload = task_text[3:].strip()
            _, content = self._split_file_payload(payload)
            return content

        if self._is_file_overwrite_task(task_text):
            if task_text.startswith("覆寫檔 "):
                payload = task_text[4:].strip()
            else:
                payload = task_text[15:].strip()
            _, content = self._split_file_payload(payload)
            return content

        if self._is_file_safe_write_task(task_text):
            if task_text.startswith("安全寫檔 "):
                payload = task_text[5:].strip()
            else:
                payload = task_text[11:].strip()
            _, content = self._split_file_payload(payload)
            return content

        if self._is_file_append_task(task_text):
            payload = task_text[10:].strip()
            _, content = self._split_file_payload(payload)
            return content

        if self._is_file_write_json_task(task_text):
            if task_text.startswith("寫json "):
                payload = task_text[6:].strip()
            else:
                payload = task_text[11:].strip()
            _, content = self._split_file_payload(payload)
            return content

        return None

    def _split_file_payload(self, payload: str) -> tuple[str, str]:
        separators = [" | ", "｜", "|||"]

        for sep in separators:
            if sep in payload:
                left, right = payload.split(sep, 1)
                return left.strip(), right.strip()

        return payload.strip(), ""

    def _normalize_path_for_compare(self, path_text: str) -> str:
        if not isinstance(path_text, str):
            return ""
        normalized = path_text.strip().lower().replace("/", "\\")
        return normalized

    def _contains_any(self, text: str, keywords: List[str]) -> bool:
        for keyword in keywords:
            if keyword in text:
                return True
        return False

    def _extract_simple_keywords(self, text: str) -> List[str]:
        raw_parts = (
            text.replace("：", " ")
            .replace(":", " ")
            .replace("，", " ")
            .replace(",", " ")
            .replace("|", " ")
            .split()
        )

        ignore_words = {
            "幫我", "一下", "查", "查詢", "搜尋", "搜索", "規格", "教學",
            "the", "a", "an", "to", "for", "of", "and"
        }

        keywords: List[str] = []
        for part in raw_parts:
            cleaned = part.strip().lower()
            if not cleaned:
                continue
            if cleaned in ignore_words:
                continue
            if len(cleaned) <= 1:
                continue
            keywords.append(cleaned)

        return keywords

    def _build_verify_result(
        self,
        success: bool,
        summary: str,
        checks: List[str],
        error: Optional[str]
    ) -> Dict[str, Any]:
        return {
            "success": success,
            "mode": "verify",
            "summary": summary,
            "checks": checks,
            "error": error,
        }