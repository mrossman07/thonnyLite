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


def _repo_toplevel(root):
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _to_root_relative(root, top_level, repo_relative_path):
    """Convert a path from `git status` (always relative to the repo's top
    level) into a path relative to `root` (wherever thonnylite was launched
    from) — needed so uploads land at the right place whether `root` is the
    repo root itself or some subdirectory of it (e.g. a `src/` that maps
    onto the Pico's filesystem root)."""
    abs_path = os.path.join(top_level, repo_relative_path)
    return os.path.relpath(abs_path, root).replace(os.sep, "/")


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
    """Modified or newly-staged files per `git status`. Returns None if not a git repo.

    Deliberately excludes plain untracked ("??") files: those are files git
    has never been told about at all (no `git add`), which in a project with
    a lot of not-yet-added cruft would otherwise sweep in far more than the
    one changed file the user actually wants. "New" here means git already
    knows about it (staged with `git add`), not merely present on disk.

    Results are relative to `root` (wherever thonnylite was launched from),
    restricted to files under `root`. `git status` itself always reports
    paths relative to the repo's top level, not the current directory, so
    both the pathspec restriction (`-- .`) and the path conversion below are
    needed for `root` to correctly be treated as "this is what maps onto the
    Pico's filesystem" when it's a subdirectory of the repo (e.g. a `src/`
    folder), not just when it happens to be the repo root.
    """
    if not _is_git_repo(root):
        return None
    top_level = _repo_toplevel(root)
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", "."],
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
        path = _to_root_relative(root, top_level, path)
        if "D" in status:
            deleted.append(path)
            continue
        files.append(path)
    return sorted(set(files)), sorted(set(deleted))


def parse_index_selection(raw, items):
    """Parse '1-3,7' / 'all' style input into a subset of `items`.

    Returns None if `raw` is blank (caller's cue to treat it as cancelled).
    Raises ValueError if `raw` can't be parsed as indices/ranges.
    """
    raw = raw.strip()
    if not raw:
        return None
    if raw.lower() == "all":
        return list(items)
    indices = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            indices.update(range(int(lo), int(hi) + 1))
        else:
            indices.add(int(part))
    return [items[i - 1] for i in sorted(indices) if 1 <= i <= len(items)]


def prompt_selection(items, prompt="Enter numbers/ranges (e.g. 1-3,7), or 'all':"):
    """Print a numbered list of `items` and prompt until a valid subset is chosen."""
    for i, item in enumerate(items, start=1):
        print(f"  {i:>3}. {item}")
    print(prompt)
    while True:
        raw = input("> ").strip()
        try:
            selected = parse_index_selection(raw, items)
        except ValueError:
            print("Couldn't parse that. Try again.")
            continue
        if not selected:
            print("No valid selection. Try again.")
            continue
        return selected


def prompt_selective(all_files):
    """Ask the user to pick a subset of files via numbered checklist input."""
    print("Files available:")
    return prompt_selection(all_files)


def prompt_selection_or_none(items):
    """Like prompt_selection, but blank input cancels (returns None) instead of re-prompting."""
    for i, item in enumerate(items, start=1):
        print(f"  {i:>3}. {item}")
    while True:
        raw = input("> ").strip()
        if not raw:
            return None
        try:
            selected = parse_index_selection(raw, items)
        except ValueError:
            print("Couldn't parse that. Try again (or leave blank to cancel).")
            continue
        if not selected:
            print("No valid selection. Try again (or leave blank to cancel).")
            continue
        return selected
