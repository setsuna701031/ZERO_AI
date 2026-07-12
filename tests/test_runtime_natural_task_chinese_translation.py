from core.runtime.runtime_natural_task_package_generator import (
    build_runtime_operator_package_from_task,
)


def test_chinese_create_file_with_content_becomes_mutation_request() -> None:
    result = build_runtime_operator_package_from_task(
        "在 workspace 建立 sentinel_activity_check.txt，"
        "內容寫入 ZERO sentinel activity integration verified"
    )

    assert result["ok"] is True

    package = result["runtime_operator_package"]
    assert package["requested_changes"] == [
        {
            "change_id": "natural-task-change-1",
            "change_type": "file_mutation",
            "description": (
                "在 workspace 建立 sentinel_activity_check.txt，"
                "內容寫入 ZERO sentinel activity integration verified"
            ),
            "target_path": "workspace/sentinel_activity_check.txt",
            "path": "workspace/sentinel_activity_check.txt",
            "relative_path": "workspace/sentinel_activity_check.txt",
            "operation": "create_file",
            "content": "ZERO sentinel activity integration verified",
        }
    ]


def test_unsafe_absolute_path_stays_plan_only() -> None:
    result = build_runtime_operator_package_from_task(
        "建立 C:/temp/unsafe.txt，內容寫入 blocked"
    )

    change = result["runtime_operator_package"]["requested_changes"][0]
    assert change["operation"] == "plan_only_until_authorized"
    assert change["target_path"] == ""
