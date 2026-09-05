"""Decide which local files to upload: all / selective / git-modified."""

import os
import subprocess

BUILTIN_IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
BUILTIN_IGNORE_FILES = {".DS_Store"}


def _is_git_repo(root):
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git_ls_files(root):
    """Tracked + untracked files, honoring .gitignore. Relative posix paths."""
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _walk_all_files(root):
    """Fallback for non-git directories: built-in ignore list only."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in BUILTIN_IGNORE_DIRS]
        for name in filenames:
            if name in BUILTIN_IGNORE_FILES:
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            files.append(rel.replace(os.sep, "/"))
    return sorted(files)


def list_all_files(root="."):
    if _is_git_repo(root):
        return sorted(_git_ls_files(root))
    return _walk_all_files(root)


def list_git_modified_files(root="."):
    """Modified/staged/untracked files per `git status`. Returns None if not a git repo."""
    if not _is_git_repo(root):
        return None
    result = subprocess.run(
        # --untracked-files=all: list files inside a new directory individually
        # rather than collapsing the whole directory to one line.
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    files = []
    deleted = []
    for line in result.stdout.splitlines():
        status, path = line[:2], line[3:]
        # Handle renames: "R  old -> new"
        if "->" in path:
            path = path.split("->", 1)[1].strip()
        if "D" in status:
            deleted.append(path)
            continue
        files.append(path)
    return sorted(set(files)), sorted(set(deleted))


def prompt_selective(all_files):
    """Ask the user to pick a subset via numbered checklist input."""
    print("Files available:")
    for i, f in enumerate(all_files, start=1):
        print(f"  {i:>3}. {f}")
    print("Enter numbers/ranges (e.g. 1-3,7), or 'all':")
    while True:
        raw = input("> ").strip()
        if raw.lower() == "all":
            return list(all_files)
        indices = set()
        try:
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    lo, hi = part.split("-", 1)
                    indices.update(range(int(lo), int(hi) + 1))
                else:
                    indices.add(int(part))
        except ValueError:
            print("Couldn't parse that. Try again.")
            continue
        selected = [all_files[i - 1] for i in sorted(indices) if 1 <= i <= len(all_files)]
        if not selected:
            print("No valid files selected. Try again.")
            continue
        return selected
