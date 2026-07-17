from core.tasks.work_package_mode import WorkPackageMode

def test_modes_exist():
    assert WorkPackageMode.EXPLORE.value == "explore"
    assert WorkPackageMode.PLAN.value == "plan"
    assert WorkPackageMode.EXECUTE.value == "execute"
    assert WorkPackageMode.VERIFY.value == "verify"
