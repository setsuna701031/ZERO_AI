import os


def write_file_tool(file_path: str, content: str):
    """
    寫入指定檔案內容
    """

    try:
        folder = os.path.dirname(file_path)

        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"File written successfully: {file_path}"

    except Exception as e:
        return f"Error writing file: {str(e)}"