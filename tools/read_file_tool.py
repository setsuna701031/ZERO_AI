import os


def read_file_tool(file_path: str):
    """
    讀取指定檔案內容
    """

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return content

    except Exception as e:
        return f"Error reading file: {str(e)}"