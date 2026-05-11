"""Static and behavioral checks for the deploy-time pytest temp harness.

These tests guard the Phase B6.4 fix for the WinError 5 deploy failure that
occurred when pytest tried to remove the fixed
``C:\\Dashboard\\MacMarket-Trader\\.tmp\\pytest-deploy`` basetemp on repeated
deploys.

The intent is to make sure that the deploy script:

1. Allocates a unique per-run basetemp outside the deploy tree.
2. Passes ``-p no:cacheprovider`` to deploy-time pytest invocations.
3. Cleans stale deploy-time temp artifacts before tests as a best-effort step.
4. Never broadly deletes the deploy root or runtime data directories.

The companion ``scripts/deploy_test_temp.ps1`` helper is checked via static
text assertions (PowerShell unit-testing from pytest is not portable across
all dev machines) plus an opportunistic subprocess invocation that only runs
when a PowerShell interpreter is available.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_BAT = REPO_ROOT / "scripts" / "deploy_windows.bat"
DEPLOY_PS1 = REPO_ROOT / "scripts" / "deploy_test_temp.ps1"


def _read(path: Path) -> str:
    assert path.exists(), f"missing required script: {path}"
    return path.read_text(encoding="utf-8")


def test_deploy_bat_uses_basetemp_for_pytest() -> None:
    text = _read(DEPLOY_BAT)
    assert "--basetemp" in text, "deploy script must pass --basetemp to pytest"


def test_deploy_bat_disables_pytest_cache_provider() -> None:
    text = _read(DEPLOY_BAT)
    assert "-p no:cacheprovider" in text, (
        "deploy pytest invocation must include '-p no:cacheprovider' to avoid "
        ".pytest_cache permission failures on the deploy tree"
    )


def test_deploy_bat_does_not_pin_basetemp_to_deploy_tmp_dir() -> None:
    """Regression: the old form was `pytest -q --basetemp "%TMP_DIR%\\pytest-deploy"`.

    That fixed path under C:\\Dashboard\\MacMarket-Trader\\.tmp caused WinError 5
    on repeated deploys when a prior child python/node process kept handles open.
    """
    text = _read(DEPLOY_BAT)
    # The old, broken pattern must not be the pytest invocation. We tolerate it
    # appearing only inside a preflight cleanup branch (`if exist ... Remove`).
    forbidden = re.compile(
        r"pytest\s+-q\s+--basetemp\s+\"%TMP_DIR%\\pytest-deploy\"",
        re.IGNORECASE,
    )
    assert not forbidden.search(text), (
        "deploy script still pins pytest --basetemp to the deploy-local "
        "%TMP_DIR%\\pytest-deploy path; this is the WinError 5 regression."
    )


def test_deploy_bat_invokes_unique_temp_helper() -> None:
    text = _read(DEPLOY_BAT)
    assert "deploy_test_temp.ps1" in text, (
        "deploy script must source its pytest basetemp from the deploy_test_temp.ps1 helper"
    )
    assert "-Mode New" in text, (
        "deploy script must request a fresh unique temp via the helper's New mode"
    )
    assert "DEPLOY_PYTEST_BASETEMP" in text, (
        "deploy script must capture the helper output into DEPLOY_PYTEST_BASETEMP"
    )


def test_deploy_bat_preflight_cleans_stale_temp() -> None:
    text = _read(DEPLOY_BAT)
    assert "-Mode CleanStale" in text, (
        "deploy script must invoke best-effort CleanStale before tests"
    )
    # Preflight cleanup must explicitly target the legacy .tmp\pytest-deploy
    # folder so it is removed before pytest tries to reuse it.
    assert "TMP_DIR%\\pytest-deploy" in text


def test_deploy_bat_warns_clearly_when_not_admin() -> None:
    text = _read(DEPLOY_BAT)
    assert "Not running as Administrator" in text
    # The new copy explains that non-admin can leave temp folders locked.
    assert "stale child python/node processes".lower() in text.lower() or (
        "stale child python" in text.lower()
    )


def test_deploy_bat_does_not_broad_remove_deploy_root() -> None:
    text = _read(DEPLOY_BAT)
    # No recursive deletion of the deploy root or runtime artifact roots.
    forbidden_patterns = [
        r"Remove-Item\s+[\"']?C:\\Dashboard\\MacMarket-Trader[\"']?\s+-Recurse",
        r"rmdir\s+/[sS]\s+/[qQ]\s+\"?C:\\Dashboard\\MacMarket-Trader\"?",
        r"Remove-Item\s+[\"']?%DST%[\"']?\s+-Recurse",
    ]
    for pattern in forbidden_patterns:
        assert not re.search(pattern, text, re.IGNORECASE), (
            f"deploy script must not broadly delete deploy root: matched {pattern!r}"
        )


def test_deploy_bat_preserves_runtime_artifacts_in_mirror() -> None:
    """Robocopy mirror must keep excluding runtime data directories."""
    text = _read(DEPLOY_BAT)
    for protected in ("logs", "uploads", "backups"):
        assert protected in text, f"mirror exclusion list should still mention {protected}"
    # data / storage are recreated post-mirror; they exist as set variables.
    assert "%DATA_DIR%" in text
    assert "%STORAGE_DIR%" in text


def test_deploy_bat_supports_full_and_no_test_modes() -> None:
    text = _read(DEPLOY_BAT)
    # Default behavior remains "run tests".
    assert re.search(r"set\s+\"RUN_TESTS=1\"", text)
    # The script still honours RUN_TESTS=0 / skip messaging.
    assert "Backend tests skipped" in text
    assert "Set RUN_TESTS=1 to enable them" in text


# ---------- deploy_test_temp.ps1 static checks ---------- #


def test_deploy_test_temp_ps1_exists() -> None:
    assert DEPLOY_PS1.exists(), "deploy_test_temp.ps1 helper must exist for deploy script"


def test_deploy_test_temp_ps1_refuses_dangerous_paths() -> None:
    text = _read(DEPLOY_PS1)
    assert "Test-IsDangerousPath" in text
    # Must refuse drive roots, Windows, and the deploy root itself.
    assert "c:\\windows" in text.lower()
    assert "c:\\program files" in text.lower()
    assert "c:\\dashboard\\macmarket-trader" in text.lower()


def test_deploy_test_temp_ps1_protects_runtime_artifacts() -> None:
    text = _read(DEPLOY_PS1)
    # Suffix list must include every runtime data area we care about.
    for suffix in (r"\data", r"\storage", r"\uploads", r"\logs", r"\backups"):
        assert suffix in text, f"runtime artifact suffix {suffix!r} missing from refusal list"


def test_deploy_test_temp_ps1_only_removes_known_temp_artifacts() -> None:
    text = _read(DEPLOY_PS1)
    assert "Test-IsAllowedTempPath" in text
    # Allowlist must mention the deploy-local temp roots and the per-run root.
    for fragment in ("pytest-deploy", "pytest_cache", "macmarket-pytest-deploy"):
        assert fragment in text


def test_deploy_test_temp_ps1_has_remove_retry_loop() -> None:
    text = _read(DEPLOY_PS1)
    assert "Remove-PathRobust" in text
    assert "Remove-Item" in text
    assert "Start-Sleep" in text


def test_deploy_test_temp_ps1_supports_required_modes() -> None:
    text = _read(DEPLOY_PS1)
    for mode in ("New", "CleanStale", "Remove"):
        assert f'"{mode}"' in text, f"PS1 helper must declare mode {mode!r}"


# ---------- opportunistic behavioral checks ---------- #


def _powershell_executable() -> str | None:
    for candidate in ("pwsh", "powershell"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


@pytest.mark.skipif(
    _powershell_executable() is None,
    reason="PowerShell not available on this runner; behavioral helper test skipped",
)
def test_deploy_test_temp_new_mode_returns_unique_path_outside_deploy_tree(tmp_path: Path) -> None:
    exe = _powershell_executable()
    assert exe is not None
    env = os.environ.copy()
    # Force the helper to pick a known sandbox so this test never touches the
    # real %TEMP%.
    env["TEMP"] = str(tmp_path)
    env["TMP"] = str(tmp_path)

    completed = subprocess.run(
        [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(DEPLOY_PS1), "-Mode", "New"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    emitted = completed.stdout.strip().splitlines()
    assert emitted, "helper must emit at least one path on stdout"
    path = Path(emitted[-1].strip())
    assert path.is_absolute()
    assert path.exists(), f"unique basetemp {path} should be created"

    # The path must NOT live under the deploy tree or repo .tmp.
    deploy_tree = Path(r"C:\Dashboard\MacMarket-Trader")
    repo_tmp = REPO_ROOT / ".tmp"
    assert deploy_tree not in path.parents
    assert repo_tmp not in path.parents

    # And it must live under our sandboxed temp root.
    assert tmp_path in path.parents

    # Path component must encode a per-run unique stamp.
    assert "macmarket-pytest-deploy" in str(path)
    assert re.search(r"\d{8}-\d{6}", path.name), f"per-run path lacks timestamp: {path.name}"


@pytest.mark.skipif(
    _powershell_executable() is None,
    reason="PowerShell not available on this runner; behavioral helper test skipped",
)
def test_deploy_test_temp_remove_mode_refuses_protected_path(tmp_path: Path) -> None:
    """Sanity check: Remove on a non-temp path must be a no-op."""
    exe = _powershell_executable()
    assert exe is not None

    protected = tmp_path / "data"
    protected.mkdir()
    sentinel = protected / "keep.me"
    sentinel.write_text("runtime data", encoding="utf-8")

    completed = subprocess.run(
        [
            exe,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(DEPLOY_PS1),
            "-Mode",
            "Remove",
            "-Path",
            str(protected),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0  # Always best-effort.
    # The protected directory and its sentinel must still exist; the helper
    # must refuse to delete a path that ends in \data.
    assert protected.exists()
    assert sentinel.exists()
