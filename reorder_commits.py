#!/usr/bin/env python3
"""
Reorder commits in a git repo chronologically by GIT_AUTHOR_DATE.

Used after batch-scraping multiple laws to interleave their commits
in real chronological order (like legalize-es).

Usage:
    python reorder_commits.py --repo-dir ./repo
"""

import argparse
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


def _rm_readonly(func, path, exc_info):
    """Handle read-only files on Windows during rmtree."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def run_git(args, cwd, env=None, capture=True):
    """Run a git command and return stdout."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged_env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={result.returncode}):\n{result.stderr}"
        )
    return result.stdout if capture else None


def read_commits(repo_dir):
    """Read all commits from the repo, sorted oldest-first by git log --reverse."""
    # Use \x00 as record separator to handle multi-line bodies
    raw = run_git(
        ["log", "--format=%H|%aI|%s|%b%x00", "--reverse"],
        cwd=repo_dir,
    )
    commits = []
    records = raw.split("\x00")
    for record in records:
        record = record.strip()
        if not record:
            continue
        # Split on first 3 pipes only: hash | date | subject | body
        parts = record.split("|", 3)
        if len(parts) < 3:
            continue
        commit_hash = parts[0].strip()
        author_date = parts[1].strip()
        subject = parts[2].strip()
        body = parts[3].strip() if len(parts) > 3 else ""
        commits.append({
            "hash": commit_hash,
            "date": author_date,
            "subject": subject,
            "body": body,
        })
    return commits


def sort_commits_by_date(commits):
    """Sort commits chronologically by author date (ISO 8601 string sort works)."""
    return sorted(commits, key=lambda c: c["date"])


def get_changed_files(commit_hash, repo_dir):
    """Get list of files changed in a commit using diff-tree."""
    # For the root commit, diff-tree needs --root
    try:
        output = run_git(
            ["diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
            cwd=repo_dir,
        )
    except RuntimeError:
        # Fallback for root commit
        output = run_git(
            ["diff-tree", "--no-commit-id", "-r", "--name-only", "--root", commit_hash],
            cwd=repo_dir,
        )
    files = [f.strip() for f in output.strip().splitlines() if f.strip()]
    return files


def get_file_content(commit_hash, file_path, repo_dir):
    """Extract file contents at a specific commit using git show."""
    content = run_git(
        ["show", f"{commit_hash}:{file_path}"],
        cwd=repo_dir,
    )
    return content


def rebuild_repo(repo_dir, sorted_commits, exclude_files=None):
    """Rebuild the repo from scratch with commits in the given order."""
    repo_dir = Path(repo_dir).resolve()
    original_git_dir = repo_dir / ".git"
    exclude_files = set(exclude_files or [])

    # Use a sibling directory instead of tempdir to avoid cleanup issues on Windows
    tmp_repo = repo_dir.parent / "repo-rebuilt"
    if tmp_repo.exists():
        shutil.rmtree(tmp_repo, onerror=_rm_readonly)
    tmp_repo.mkdir()

    # Init new repo
    run_git(["init"], cwd=tmp_repo)
    run_git(["config", "user.name", "Legalize CL"], cwd=tmp_repo)
    run_git(["config", "user.email", "bot@legalize.cl"], cwd=tmp_repo)

    total = len(sorted_commits)
    for i, commit in enumerate(sorted_commits, 1):
        commit_hash = commit["hash"]
        author_date = commit["date"]
        subject = commit["subject"]
        body = commit["body"]

        # Build full commit message
        if body:
            full_message = f"{subject}\n\n{body}"
        else:
            full_message = subject

        # Get files changed in this commit
        changed_files = get_changed_files(commit_hash, repo_dir)

        # Filter out excluded files
        if exclude_files:
            changed_files = [f for f in changed_files if f not in exclude_files]

        if not changed_files:
            print(f"  [{i}/{total}] Skipping empty commit: {subject[:60]}")
            continue

        # Extract each file and write it into the new repo
        for file_path in changed_files:
            dest = tmp_repo / file_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                content = get_file_content(commit_hash, file_path, repo_dir)
                dest.write_text(content, encoding="utf-8")
            except RuntimeError:
                # File was deleted in this commit; remove it from new repo
                if dest.exists():
                    dest.unlink()

        # Stage all changes
        run_git(["add", "-A"], cwd=tmp_repo)

        # Check if there's anything to commit
        status = run_git(["status", "--porcelain"], cwd=tmp_repo)
        if not status.strip():
            print(f"  [{i}/{total}] Skipping no-change commit: {subject[:60]}")
            continue

        # Commit with original dates using temp file (Windows compat)
        date_env = {
            "GIT_AUTHOR_DATE": author_date,
            "GIT_COMMITTER_DATE": author_date,
        }
        msg_file = tmp_repo / ".commitmsg"
        msg_file.write_text(full_message, encoding="utf-8")
        run_git(
            ["commit", "-F", str(msg_file.resolve()), "--allow-empty-message"],
            cwd=tmp_repo,
            env=date_env,
        )
        msg_file.unlink(missing_ok=True)

        print(f"  [{i}/{total}] {author_date} | {subject[:60]}")

    # Replace original .git with rebuilt one
    rebuilt_git_dir = tmp_repo / ".git"

    print("\nReplacing .git directory...")
    if original_git_dir.exists():
        shutil.rmtree(original_git_dir, onerror=_rm_readonly)
    shutil.copytree(rebuilt_git_dir, original_git_dir)

    # Sync working tree with new HEAD
    run_git(["checkout", "-f", "HEAD"], cwd=repo_dir)

    # Clean up rebuilt directory
    shutil.rmtree(tmp_repo, onerror=_rm_readonly)
    print("Working tree synced with rebuilt repo.")


def print_summary(repo_dir):
    """Print a summary of the rebuilt repo."""
    log_output = run_git(
        ["log", "--format=%h %aI %s", "--reverse", "-n", "10"],
        cwd=repo_dir,
    )
    total = run_git(
        ["rev-list", "--count", "HEAD"],
        cwd=repo_dir,
    ).strip()

    print(f"\n{'=' * 70}")
    print(f"Rebuild complete. Total commits: {total}")
    print(f"{'=' * 70}")
    print("First 10 commits:")
    print(log_output)


def main():
    parser = argparse.ArgumentParser(
        description="Reorder git commits chronologically by GIT_AUTHOR_DATE."
    )
    parser.add_argument(
        "--repo-dir",
        type=Path,
        required=True,
        help="Path to the git repository to reorder.",
    )
    parser.add_argument(
        "--exclude-files",
        nargs="*",
        default=[],
        help="Files to exclude from the rebuilt repo (e.g. cl/BCN-29613.md)",
    )
    args = parser.parse_args()

    repo_dir = args.repo_dir.resolve()
    if not (repo_dir / ".git").is_dir():
        raise SystemExit(f"Error: {repo_dir} is not a git repository.")

    print(f"Reading commits from {repo_dir}...")
    commits = read_commits(repo_dir)
    print(f"Found {len(commits)} commits.")

    # Filter out non-law commits (test commits, etc.)
    commits = [c for c in commits if c["subject"].startswith("[")]
    print(f"After filtering non-law commits: {len(commits)} commits.")

    print("Sorting by author date...")
    sorted_commits = sort_commits_by_date(commits)

    print(f"Rebuilding repo with {len(sorted_commits)} commits in chronological order...\n")
    rebuild_repo(repo_dir, sorted_commits, exclude_files=args.exclude_files)

    print_summary(repo_dir)


if __name__ == "__main__":
    main()
