"""Public-readiness guards: .gitignore secret coverage and the brand guard.

Repo-level checks that back the public flip. They live in the root tests/ tree
(run by `make lattice` and the CI "Repo-level guards" step), not the package
testpaths, because they assert properties of the repository itself rather than of
any one package.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRAND_GUARD = REPO_ROOT / "tools" / "brand_guard.py"


def _is_ignored(relpath: str) -> bool:
    """Whether git ignores a path, via check-ignore (exit 0 means ignored)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", relpath],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


def _is_tracked(relpath: str) -> bool:
    """Whether git tracks a path, via ls-files (nonempty output means tracked)."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relpath],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def test_gitignore_covers_secrets_dir() -> None:
    # A stray secret file under infra/secrets/ must be ignored, and the .gitkeep
    # placeholder must stay tracked so the directory survives a fresh clone.
    assert _is_ignored("infra/secrets/postgres_password")
    assert _is_ignored("infra/secrets/anything.pem")
    assert not _is_ignored("infra/secrets/.gitkeep")
    assert _is_tracked("infra/secrets/.gitkeep")


def test_gitignore_covers_env_and_graphify() -> None:
    assert _is_ignored(".env")
    assert _is_ignored("graphify-out/nodes.json")
    # The committed example env file must stay tracked despite the .env.* ignore
    # (the !.env.example negation holds), so a fresh clone can copy it.
    assert not _is_ignored("infra/.env.example")
    assert _is_tracked("infra/.env.example")


def _run_brand_guard(*paths: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BRAND_GUARD), *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_brand_guard_flags_a_planted_token(tmp_path: Path) -> None:
    # Build the token at runtime so this test file does not itself carry it.
    brand = "co" + "work"
    planted = tmp_path / "note.md"
    planted.write_text(f"see the {brand} mirror\n", encoding="utf-8")
    result = _run_brand_guard(str(planted))
    assert result.returncode == 1
    assert "brand guard" in result.stderr


def test_brand_guard_flags_the_kb_path(tmp_path: Path) -> None:
    fragment = "Architecting_" + "Domain_Driven"
    planted = tmp_path / "note.md"
    planted.write_text(f"path: {fragment}\\KB\n", encoding="utf-8")
    result = _run_brand_guard(str(planted))
    assert result.returncode == 1
    assert "KB directory path" in result.stderr


def test_brand_guard_flags_a_token_in_the_path(tmp_path: Path) -> None:
    # A brand token in the filename is caught even when the content is clean.
    brand = "co" + "work"
    planted = tmp_path / f"{brand}_notes.md"
    planted.write_text("clean content\n", encoding="utf-8")
    result = _run_brand_guard(str(planted))
    assert result.returncode == 1
    assert "in path" in result.stderr


def _init_repo_with(tmp_path: Path, filename: str, content: str) -> Path:
    """A throwaway git repo with one commit, so --history is tested independently
    of this repo's actual history (which stays dirty until the pre-flip scrub)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    run("init", "-q")
    (repo / filename).write_text(content, encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "seed")
    return repo


def _history_scan(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BRAND_GUARD), "--history"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_brand_guard_history_flags_a_token_in_an_old_commit(tmp_path: Path) -> None:
    brand = "co" + "work"
    repo = _init_repo_with(tmp_path, "old.md", f"see the {brand} mirror\n")
    result = _history_scan(repo)
    assert result.returncode == 1
    assert "scrub history" in result.stderr


def test_brand_guard_history_clean_repo_passes(tmp_path: Path) -> None:
    repo = _init_repo_with(tmp_path, "clean.md", "ReleasePlane control plane.\n")
    assert _history_scan(repo).returncode == 0


def test_brand_guard_passes_clean_file(tmp_path: Path) -> None:
    clean = tmp_path / "clean.md"
    clean.write_text("ReleasePlane is a control plane for LLM releases.\n", encoding="utf-8")
    assert _run_brand_guard(str(clean)).returncode == 0


def test_brand_guard_excludes_itself() -> None:
    # The guard source necessarily contains the denied tokens; scanning it must
    # not fail, or the guard could never live in the tree it protects.
    assert _run_brand_guard(str(BRAND_GUARD)).returncode == 0


def test_working_tree_is_brand_clean() -> None:
    # The live gate: every tracked file passes the guard right now.
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    result = _run_brand_guard(*tracked)
    assert result.returncode == 0, result.stderr
