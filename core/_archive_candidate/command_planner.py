from __future__ import annotations


class CommandPlanner:
    def __init__(self, llm_client) -> None:
        self.llm_client = llm_client

    def create_command_plan(self, goal: str) -> list[str]:
        prompt = (
            "你是本地工程 AI。\n"
            "請根據使用者目標，輸出可執行命令清單。\n"
            "每行只能輸出一條命令，不要解釋，不要編號，不要 markdown。\n\n"
            "允許命令格式只有下面這些：\n"
            "RUN_SHELL <command>\n"
            "WRITE_FILE <path> :: <content>\n"
            "RUN_PYTHON <path>\n"
            "DEBUG_PYTHON <path>\n"
            "DEBUG_PROJECT <path>\n"
            "READ_FILE <path>\n"
            "LIST_FILES <path>\n"
            "SEARCH_CODE <keyword>\n\n"
            "重要規則：\n"
            "1. RUN_PYTHON 只能是單一 Python 檔案路徑，例如：RUN_PYTHON app.py\n"
            "2. 只要 python 命令後面還有其他參數，就必須改用 RUN_SHELL，例如：RUN_SHELL python setup.py bdist_wheel\n"
            "3. pip install 一律使用 RUN_SHELL\n"
            "4. WRITE_FILE 必須維持單行輸出\n"
            "5. 不要輸出自然語言，不要輸出範例說明\n"
            "6. 不要輸出不存在的自訂命令\n"
            "7. 如果目標是建立 Flask API，優先使用這種形式：\n"
            "RUN_SHELL pip install flask\n"
            "WRITE_FILE app.py :: from flask import Flask;app=Flask(__name__);@app.route('/');def home(): return 'Hello Flask';if __name__=='__main__': app.run(debug=True)\n"
            "DEBUG_PYTHON app.py\n\n"
            f"使用者目標:\n{goal}\n\n"
            "現在只輸出命令清單："
        )

        result = self.llm_client.generate(prompt)

        commands: list[str] = []
        for line in result.splitlines():
            cmd = line.strip()
            if not cmd:
                continue

            if (
                cmd.startswith("RUN_SHELL ")
                or cmd.startswith("WRITE_FILE ")
                or cmd.startswith("RUN_PYTHON ")
                or cmd.startswith("DEBUG_PYTHON ")
                or cmd.startswith("DEBUG_PROJECT ")
                or cmd.startswith("READ_FILE ")
                or cmd.startswith("LIST_FILES ")
                or cmd.startswith("SEARCH_CODE ")
            ):
                commands.append(cmd)

        return commands