import os

def list_files_tool(base_path="E:\\zero_ai", max_depth=3):
    result = []

    for root, dirs, files in os.walk(base_path):
        depth = root.replace(base_path, "").count(os.sep)

        if depth > max_depth:
            continue

        indent = "  " * depth
        result.append(f"{indent}[DIR] {os.path.basename(root)}")

        for f in files:
            result.append(f"{indent}  - {f}")

    return "\n".join(result)