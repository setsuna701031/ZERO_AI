from core.llm_client import LocalLLMClient


def main() -> None:
    client = LocalLLMClient()

    tool_descriptions = """
- file_tool:
  description: Read and write files inside workspace.
  supported actions:
    - write_file(path, content)
    - read_file(path)

- command_tool:
  description: Execute safe shell commands.
  supported actions:
    - run(command)

- web_search:
  description: Search web information.
  supported actions:
    - search(query)
""".strip()

    user_input_1 = "你好，你是誰？"
    user_input_2 = "幫我建立一個 notes.txt，內容是 hello"

    print("=== health_check ===")
    print(client.health_check())
    print()

    print("=== tool decision 1 ===")
    print(client.generate_tool_decision(user_input_1, tool_descriptions))
    print()

    print("=== tool decision 2 ===")
    print(client.generate_tool_decision(user_input_2, tool_descriptions))
    print()


if __name__ == "__main__":
    main()