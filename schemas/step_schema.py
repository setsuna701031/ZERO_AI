from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ----------------------------------------------------------------------
# Step Types
# ----------------------------------------------------------------------

STEP_TYPE_CREATE_PROJECT = "create_project"
STEP_TYPE_CREATE_FOLDER = "create_folder"
STEP_TYPE_CREATE_FILE = "create_file"
STEP_TYPE_WRITE_FILE = "write_file"
STEP_TYPE_APPEND_FILE = "append_file"
STEP_TYPE_RUN_PYTHON = "run_python"
STEP_TYPE_RUN_SHELL = "run_shell"
STEP_TYPE_START_SERVER = "start_server"
STEP_TYPE_TEST_HTTP = "test_http"
STEP_TYPE_STOP_SERVER = "stop_server"
STEP_TYPE_DELETE_FILE = "delete_file"


ALL_STEP_TYPES = {
    STEP_TYPE_CREATE_PROJECT,
    STEP_TYPE_CREATE_FOLDER,
    STEP_TYPE_CREATE_FILE,
    STEP_TYPE_WRITE_FILE,
    STEP_TYPE_APPEND_FILE,
    STEP_TYPE_RUN_PYTHON,
    STEP_TYPE_RUN_SHELL,
    STEP_TYPE_START_SERVER,
    STEP_TYPE_TEST_HTTP,
    STEP_TYPE_STOP_SERVER,
    STEP_TYPE_DELETE_FILE,
}


# ----------------------------------------------------------------------
# Step Schema
# ----------------------------------------------------------------------

@dataclass
class Step:
    """
    Structured Step Schema

    Example:
    {
        "step_id": "step_3",
        "type": "create_file",
        "name": "Create server.py",
        "path": "server.py",
        "template": "http_server"
    }
    """

    step_id: str
    type: str
    name: Optional[str] = None

    # file / folder
    path: Optional[str] = None
    content: Optional[str] = None
    template: Optional[str] = None

    # command
    command: Optional[str] = None
    args: Optional[List[str]] = None

    # http
    url: Optional[str] = None
    method: Optional[str] = None

    # dependency
    depends_on: Optional[List[str]] = field(default_factory=list)

    # retry / policy
    retry: int = 0
    timeout: Optional[int] = None

    # metadata
    meta: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        if not self.step_id:
            raise ValueError("step_id is required")

        if self.type not in ALL_STEP_TYPES:
            raise ValueError(f"Unsupported step type: {self.type}")

        if self.type in {STEP_TYPE_CREATE_FILE, STEP_TYPE_WRITE_FILE, STEP_TYPE_APPEND_FILE}:
            if not self.path:
                raise ValueError(f"{self.type} requires 'path'")

        if self.type == STEP_TYPE_TEST_HTTP:
            if not self.url:
                raise ValueError("test_http requires 'url'")

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "type": self.type,
            "name": self.name,
            "path": self.path,
            "content": self.content,
            "template": self.template,
            "command": self.command,
            "args": self.args,
            "url": self.url,
            "method": self.method,
            "depends_on": self.depends_on,
            "retry": self.retry,
            "timeout": self.timeout,
            "meta": self.meta,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Step":
        return Step(
            step_id=data.get("step_id"),
            type=data.get("type"),
            name=data.get("name"),
            path=data.get("path"),
            content=data.get("content"),
            template=data.get("template"),
            command=data.get("command"),
            args=data.get("args"),
            url=data.get("url"),
            method=data.get("method"),
            depends_on=data.get("depends_on") or [],
            retry=data.get("retry", 0),
            timeout=data.get("timeout"),
            meta=data.get("meta") or {},
        )


# ----------------------------------------------------------------------
# Step Factory Helpers
# ----------------------------------------------------------------------

def create_project_step(step_id: str) -> Step:
    return Step(
        step_id=step_id,
        type=STEP_TYPE_CREATE_PROJECT,
        name="Create project workspace",
    )


def create_file_step(step_id: str, path: str, template: Optional[str] = None) -> Step:
    return Step(
        step_id=step_id,
        type=STEP_TYPE_CREATE_FILE,
        name=f"Create file {path}",
        path=path,
        template=template,
    )


def start_server_step(step_id: str, path: str) -> Step:
    return Step(
        step_id=step_id,
        type=STEP_TYPE_START_SERVER,
        name="Start server",
        path=path,
    )


def test_http_step(step_id: str, url: str) -> Step:
    return Step(
        step_id=step_id,
        type=STEP_TYPE_TEST_HTTP,
        name="Test HTTP endpoint",
        url=url,
        method="GET",
    )