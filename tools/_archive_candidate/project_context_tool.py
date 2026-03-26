import os


def project_context_tool():
    """
    返回整個專案結構
    """

    root = os.getcwd()

    output = []

    for root_dir, dirs, files in os.walk(root):

        level = root_dir.replace(root, "").count(os.sep)
        indent = " " * (level * 2)

        folder = os.path.basename(root_dir)

        if folder == "":
            folder = "project_root"

        output.append(f"{indent}[DIR] {folder}")

        subindent = " " * ((level + 1) * 2)

        for f in files:
            output.append(f"{subindent}- {f}")

    return "\n".join(output)