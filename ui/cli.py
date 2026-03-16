from __future__ import annotations

from config import CLI_PROMPT


class CLI:
    def __init__(self, router, executor, session_state) -> None:
        self.router = router
        self.executor = executor
        self.session_state = session_state

    def run(self) -> None:
        print("ZERO AI CLI 啟動。輸入 help 查看指令，輸入 exit 離開。")
        print("多行錯誤貼上可用：fix error，結尾輸入 END")
        while True:
            try:
                user_input = input(CLI_PROMPT)
            except (EOFError, KeyboardInterrupt):
                print("\n已退出。")
                break

            if user_input.strip().lower() == "fix error":
                multiline_text = self._read_multiline_error()
                user_input = f"fix error {multiline_text}"

            route = self.router.route(user_input)
            result = self.executor.execute(route)

            if result == "__EXIT__":
                print("已退出。")
                break

            self.session_state.last_result = result
            print(result)

    def _read_multiline_error(self) -> str:
        print("請貼上完整 Traceback，結束請輸入單獨一行 END")
        lines: list[str] = []

        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                break

            if line.strip() == "END":
                break

            lines.append(line)

        return "\n".join(lines)