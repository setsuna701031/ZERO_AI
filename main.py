from core.router import Router
from core.flask_manager import (
    syntax_check_app,
    restart_flask_internal,
    stop_flask_internal,
    build_flask_api,
    list_flask_routes,
    add_flask_route,
    remove_flask_route,
)


def print_help() -> None:
    print("ZERO AI CLI 啟動。輸入 help 查看指令，輸入 exit 離開。")
    print("可用指令包含 build flask api / stop flask api / restart flask / list flask routes。")
    print("也支援 add flask route <name> / add flask post route <name> / remove flask route <name>。")


def print_plan(title: str) -> None:
    print("\n=== AI Command Plan ===")
    print(title)


def print_step(step_name: str, data: dict) -> None:
    print(f"\n=== {step_name} ===")
    for key, value in data.items():
        print(f"{key:<10}: {value}")


def handle_command(command: dict) -> None:
    action = command.get("action")

    if action == "build_flask_api":
        print_plan("BUILD_FLASK_API")
        result = build_flask_api()
        print_step("Step 1: build_flask_api", result)

        print("\n=== Summary ===")
        print(result["message"])
        return

    if action == "stop_flask":
        print_plan("STOP_FLASK")
        result = stop_flask_internal()
        print_step("Step 1: stop_flask_internal", result)

        print("\n=== Summary ===")
        print(result["message"])
        return

    if action == "restart_flask":
        print_plan("RESTART_FLASK")

        syntax_result = syntax_check_app()
        print_step("Step 1: syntax_check", syntax_result)

        if not syntax_result.get("success"):
            print("\n=== Summary ===")
            print("語法檢查未通過，已停止重啟。")
            return

        restart_result = restart_flask_internal()
        print_step("Step 2: restart_flask_internal", restart_result)

        print("\n=== Summary ===")
        if restart_result.get("success"):
            print("Flask 已重新啟動。請打開：http://127.0.0.1:5000")
        else:
            print(restart_result["message"])
        return

    if action == "list_flask_routes":
        print_plan("LIST_FLASK_ROUTES")
        result = list_flask_routes()
        print_step("Step 1: list_flask_routes", {"success": result["success"], "message": result["message"]})

        print("\n=== Routes ===")
        routes = result.get("routes", [])
        if not routes:
            print("(無自動路由)")
        else:
            for item in routes:
                print(f'{item["route"]}  [{item["methods"]}]  -> {item["function"]}')

        print("\n=== Summary ===")
        print(result["message"])
        return

    if action == "add_flask_route":
        route_name = command.get("route_name", "").strip()
        method = command.get("method", "GET").strip().upper()

        print_plan(f"ADD_FLASK_{method}_ROUTE")

        add_result = add_flask_route(route_name, method=method)
        print_step("Step 1: add_flask_route", add_result)

        if not add_result.get("success"):
            print("\n=== Summary ===")
            print(add_result["message"])
            return

        syntax_result = syntax_check_app()
        print_step("Step 2: syntax_check", syntax_result)

        if not syntax_result.get("success"):
            print("\n=== Summary ===")
            print("新增成功，但語法檢查失敗。請檢查 app.py。")
            return

        restart_result = restart_flask_internal()
        print_step("Step 3: restart_flask_internal", restart_result)

        print("\n=== Summary ===")
        if restart_result.get("success"):
            print(f"已新增 {method} route：/{route_name}，且 Flask 已重新啟動。")
        else:
            print(f"已新增 {method} route：/{route_name}，但 Flask 重啟失敗。")
        return

    if action == "remove_flask_route":
        route_name = command.get("route_name", "").strip()

        print_plan("REMOVE_FLASK_ROUTE")

        remove_result = remove_flask_route(route_name)
        print_step("Step 1: remove_flask_route", remove_result)

        if not remove_result.get("success"):
            print("\n=== Summary ===")
            print(remove_result["message"])
            return

        syntax_result = syntax_check_app()
        print_step("Step 2: syntax_check", syntax_result)

        if not syntax_result.get("success"):
            print("\n=== Summary ===")
            print("移除成功，但語法檢查失敗。請檢查 app.py。")
            return

        restart_result = restart_flask_internal()
        print_step("Step 3: restart_flask_internal", restart_result)

        print("\n=== Summary ===")
        if restart_result.get("success"):
            print(f"已移除 route：/{route_name}，且 Flask 已重新啟動。")
        else:
            print(f"已移除 route：/{route_name}，但 Flask 重啟失敗。")
        return

    print("未知動作。")


def main() -> None:
    router = Router()

    print("Starting ZERO AI v0.1.0")
    print_help()

    while True:
        try:
            text = input("ZERO> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n已離開 ZERO。")
            break

        result = router.route(text)

        if result["type"] == "empty":
            continue

        if result["type"] == "help":
            print_help()
            continue

        if result["type"] == "exit":
            print("已離開 ZERO。")
            break

        if result["type"] == "unknown":
            print(f"未知指令：{result['text']}")
            print("輸入 help 查看可用指令。")
            continue

        if result["type"] == "command":
            handle_command(result)
            continue


if __name__ == "__main__":
    main()