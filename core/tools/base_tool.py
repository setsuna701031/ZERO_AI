from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseTool(ABC):
    """
    所有工具的基底類別。
    """

    name: str = ""
    description: str = ""
    input_schema: Dict[str, Any] = {}

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    @abstractmethod
    def run(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def validate_arguments(self, arguments: Dict[str, Any]) -> List[str]:
        errors: List[str] = []

        if not isinstance(arguments, dict):
            errors.append("arguments must be a dict")
            return errors

        required_fields = self.input_schema.get("required", [])
        properties = self.input_schema.get("properties", {})

        for field in required_fields:
            if field not in arguments:
                errors.append(f"missing required field: {field}")

        for key in arguments.keys():
            if key not in properties:
                errors.append(f"unexpected field: {key}")

        return errors