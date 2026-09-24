#!/usr/bin/env python3
"""
export_project_snapshot.py

指定したプロジェクト配下の Python ソースコードを
ChatGPT共有用の txt ファイルへ出力する。

Usage:
    python export_project_snapshot.py ALICE_Transcript
"""

from pathlib import Path
import sys

# 無視するディレクトリ
IGNORE_DIRS = {
    "old",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
}

OUTPUT_SUFFIX = "_Source.txt"


# ------------------------------------------------------------
# 判定
# ------------------------------------------------------------
def is_ignored(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def collect_python_files(root: Path):
    files = []

    for f in root.rglob("*.py"):
        if is_ignored(f):
            continue
        files.append(f)

    return sorted(files)


# ------------------------------------------------------------
# Pythonファイルを持つディレクトリだけ残す
# ------------------------------------------------------------
def collect_valid_dirs(root: Path, py_files):
    valid = set()

    for f in py_files:
        p = f.parent

        while True:
            valid.add(p)

            if p == root:
                break

            p = p.parent

    return valid


# ------------------------------------------------------------
# Tree出力
# ------------------------------------------------------------
def write_tree(fp, root, current, valid_dirs, prefix=""):

    children = []

    for child in sorted(current.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):

        if is_ignored(child):
            continue

        if child.is_dir():
            if child not in valid_dirs:
                continue

        elif child.suffix != ".py":
            continue

        children.append(child)

    for i, child in enumerate(children):

        last = i == len(children) - 1

        branch = "└── " if last else "├── "

        fp.write(prefix + branch + child.name)

        if child.is_dir():
            fp.write("/\n")

            extension = "    " if last else "│   "

            write_tree(
                fp,
                root,
                child,
                valid_dirs,
                prefix + extension,
            )

        else:
            fp.write("\n")


# ------------------------------------------------------------
# ソースコード出力
# ------------------------------------------------------------
def write_source(fp, root, py_files):

    for file in py_files:

        rel = file.relative_to(root)

        fp.write("\n")
        fp.write("=" * 80 + "\n")
        fp.write(f"File : {rel}\n")
        fp.write("=" * 80 + "\n\n")

        try:
            lines = file.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines()

        except Exception as e:
            fp.write(f"<< Read Error : {e} >>\n")
            continue

        for i, line in enumerate(lines, start=1):
            fp.write(f"{i:04d} {line}\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():

    if len(sys.argv) != 2:
        print("Usage:")
        print("    python export_project_snapshot.py <ProjectName>")
        sys.exit(1)

    project = Path(sys.argv[1])

    if not project.exists():
        print(f"Project not found : {project}")
        sys.exit(1)

    root = project.resolve()

    py_files = collect_python_files(root)

    valid_dirs = collect_valid_dirs(root, py_files)

    output = Path.cwd() / f"{root.name}{OUTPUT_SUFFIX}"

    with output.open(
        "w",
        encoding="utf-8",
    ) as fp:

        fp.write("=" * 80 + "\n")
        fp.write("Project Snapshot\n")
        fp.write("=" * 80 + "\n\n")

        fp.write(f"Project : {root.name}\n\n")

        fp.write("=" * 80 + "\n")
        fp.write("Directory Tree\n")
        fp.write("=" * 80 + "\n\n")

        fp.write(root.name + "/\n")

        write_tree(
            fp,
            root,
            root,
            valid_dirs,
        )

        fp.write("\n")

        write_source(
            fp,
            root,
            py_files,
        )

    print(f"Saved : {output}")


if __name__ == "__main__":
    main()