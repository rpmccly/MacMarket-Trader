"""Static checks for the deploy-profile hardening of ``deploy_windows.bat``.

The deploy script is the canonical operator entrypoint. These tests pin
the contract added by the deploy-profile work:

- ``-TestProfile`` is the documented parameter, defaulting to ``full``.
- ``full`` runs the full backend pytest + full frontend Vitest + tsc —
  the historic safe release path.
- ``fast`` runs a targeted backend smoke (charts + Momentum active
  guards + Phase C static + deploy temp) and a narrow frontend Vitest
  subset plus tsc.
- ``frontend`` skips backend pytest and runs the full frontend Vitest
  plus tsc.
- ``backend`` skips frontend Vitest but keeps tsc + full backend pytest.
- ``none`` (emergency) requires ``-ForceNoTests`` and refuses to run if
  live broker env vars are present.
- An unknown profile fails the deploy with a clear error before any
  tests run.
- The script never reintroduces the fixed
  ``%TMP_DIR%\\pytest-deploy`` basetemp that caused the deploy-time
  ``WinError 5``.
- The script does not introduce broad / destructive Remove-Item or
  process-kill patterns.

The wrapper (``deploy-macmarket-trader.bat``) must resolve the repo
root from ``%~dp0``, not from positional args or the current working
directory, and must forward ``%*`` to the canonical script.

The tests are intentionally text-based for the most part: invoking
the .bat from pytest requires an interactive Windows shell, which is
not portable. A small opportunistic subprocess test covers the
``-DryRun`` mode on Windows.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_BAT = REPO_ROOT / "scripts" / "deploy_windows.bat"
WRAPPER_BAT = REPO_ROOT / "deploy-macmarket-trader.bat"
DEPLOY_PROFILES_DOC = REPO_ROOT / "docs" / "deploy-profiles.md"


def _read(path: Path) -> str:
    assert path.exists(), f"missing required script: {path}"
    return path.read_text(encoding="utf-8")


# ── Parameter / default plumbing ─────────────────────────────────────


def test_deploy_bat_exposes_test_profile_parameter() -> None:
    text = _read(DEPLOY_BAT)
    assert "-TestProfile" in text
    # Default must remain full to preserve historic safe behavior.
    assert re.search(r'set\s+"TEST_PROFILE=full"', text), (
        "deploy script default test profile must remain 'full'"
    )


def test_deploy_bat_accepts_all_documented_profiles() -> None:
    text = _read(DEPLOY_BAT).lower()
    for profile in ("full", "fast", "frontend", "backend", "none"):
        assert f'"%test_profile%"=="{profile}"' in text or (
            f'set "valid_profile=1"' in text and profile in text
        ), f"deploy script must accept the {profile} profile"


def test_deploy_bat_rejects_unknown_profile_with_clear_error() -> None:
    text = _read(DEPLOY_BAT)
    assert "Unknown test profile" in text
    assert "Allowed: full" in text


# ── Full profile — historic safe behavior ────────────────────────────


def test_full_profile_runs_full_backend_pytest_and_frontend_npm_test() -> None:
    text = _read(DEPLOY_BAT)
    # The unbranded `pytest -q -p no:cacheprovider --basetemp "..."`
    # invocation must still exist as the full-profile path. Either
    # delayed (`!VAR!`) or normal (`%VAR%`) expansion is accepted;
    # the subroutine refactor uses normal expansion since the call
    # no longer lives inside a parenthesized IF block.
    assert re.search(
        r'pytest\s+-q\s+-p\s+no:cacheprovider\s+--basetemp\s+"[!%]DEPLOY_PYTEST_BASETEMP[!%]"',
        text,
    ), "full profile must still invoke full pytest with --basetemp"
    # The full frontend `npm test` path is still used outside the fast
    # subset branch.
    assert "call npm test" in text


# ── Fast profile — targeted smoke ────────────────────────────────────


def test_fast_profile_runs_targeted_backend_smoke() -> None:
    text = _read(DEPLOY_BAT)
    # The fast branch must enumerate the exact target tests called out
    # in docs/deploy-profiles.md.
    for target in (
        r"tests\test_charts_api.py",
        r"tests\test_momentum_charts_api.py",
        r"tests\test_momentum_b64_queue_response_guard.py",
        r"tests\test_momentum_b63_queue_consistency.py",
        r"tests\test_momentum_active_delta_scale.py",
        r"tests\test_true_momentum_strategy_families.py",
        r"tests\test_momentum_phase_closeout.py",
        r"tests\test_deploy_test_temp.py",
        r"tests\test_deploy_profiles.py",
    ):
        assert target in text, f"fast profile must include {target}"


def test_fast_profile_runs_narrow_frontend_vitest_subset_and_tsc() -> None:
    text = _read(DEPLOY_BAT)
    # The narrow Vitest set must include the chart-history-range and
    # Phase C2 evidence smoke files.
    assert "lib/chart-history-range.test.ts" in text
    assert "components/charts/chart-history-range-select.test.tsx" in text
    assert "lib/momentum-integration.test.ts" in text
    assert "lib/true-momentum-preview-evidence.test.ts" in text
    assert "components/recommendations/true-momentum-preview-evidence-panel.test.tsx" in text
    # tsc must run for both full and fast profiles.
    assert "tsc --noEmit" in text


# ── Frontend profile — frontend Vitest + tsc, no backend pytest ───────


def test_frontend_profile_skips_backend_pytest() -> None:
    text = _read(DEPLOY_BAT)
    # The branching variable RUN_BACKEND_TESTS=0 is set when profile is frontend.
    assert re.search(
        r'set "RUN_BACKEND_TESTS=0"[\s\S]*?if /I "%TEST_PROFILE%"=="frontend"',
        text,
    ) or "Backend tests skipped: -TestProfile frontend" in text


# ── Backend profile — backend pytest + tsc, no frontend Vitest ────────


def test_backend_profile_skips_frontend_vitest() -> None:
    text = _read(DEPLOY_BAT)
    assert "Frontend Vitest skipped: -TestProfile backend" in text


# ── None profile — emergency, requires force ─────────────────────────


def test_none_profile_requires_force_flag() -> None:
    text = _read(DEPLOY_BAT)
    assert '"FORCE_NO_TESTS=0"' in text
    assert 'requires -ForceNoTests to run' in text
    assert "operator emergency mode" in text


def test_none_profile_refuses_when_broker_live_envs_present() -> None:
    text = _read(DEPLOY_BAT)
    assert "MACMARKET_BROKER_LIVE" in text
    assert "BROKER_PROVIDER" in text
    assert "Refusing -TestProfile none" in text


# ── Deploy-temp hardening preserved ──────────────────────────────────


def test_deploy_pytest_still_uses_unique_basetemp_helper() -> None:
    text = _read(DEPLOY_BAT)
    assert "DEPLOY_PYTEST_BASETEMP" in text
    assert "deploy_test_temp.ps1" in text
    assert "no:cacheprovider" in text


def test_deploy_bat_never_pins_basetemp_to_deploy_tmp_dir() -> None:
    """Regression: the old form was
    ``pytest -q --basetemp "%TMP_DIR%\\pytest-deploy"`` which caused
    WinError 5 on repeated deploys. The profile branches must never
    reintroduce that fixed path."""
    text = _read(DEPLOY_BAT)
    bad = re.compile(
        r"pytest\s+-q\s+(?:[^\n]*\s)?--basetemp\s+\"%TMP_DIR%\\pytest-deploy\"",
        flags=re.IGNORECASE,
    )
    assert bad.search(text) is None, (
        "deploy script must not pin --basetemp to %TMP_DIR%\\pytest-deploy"
    )


# ── Safety: no broad destructive patterns added ──────────────────────


def test_deploy_bat_does_not_recursively_remove_deploy_root() -> None:
    text = _read(DEPLOY_BAT).lower()
    for forbidden in (
        "rmdir /s /q %dst%",
        "remove-item -recurse -force %dst%",
        "remove-item -recurse -force \"%dst%\"",
        "rd /s /q %dst%",
    ):
        assert forbidden not in text, (
            f"deploy script must not recursively remove the deploy root: {forbidden}"
        )


def test_deploy_bat_does_not_broadly_kill_node_or_python() -> None:
    text = _read(DEPLOY_BAT).lower()
    # The deploy uses targeted Get-CimInstance + Where-Object filtering.
    # A pattern like `taskkill /F /IM python.exe` or `taskkill /F /IM
    # node.exe` would broadly kill unrelated developer processes.
    assert "taskkill /f /im python.exe" not in text
    assert "taskkill /f /im node.exe" not in text


def test_deploy_bat_warns_clearly_when_not_admin() -> None:
    text = _read(DEPLOY_BAT)
    assert "Not running as Administrator" in text


# ── Profile contract surfaced to logs ────────────────────────────────


def test_deploy_bat_prints_selected_profile_before_tests() -> None:
    text = _read(DEPLOY_BAT)
    assert "Test profile: %TEST_PROFILE%" in text
    assert "Backend validation:" in text
    assert "Frontend validation:" in text


# ── Doc surface ─────────────────────────────────────────────────────


def test_deploy_profiles_doc_exists_and_lists_supported_profiles() -> None:
    body = _read(DEPLOY_PROFILES_DOC)
    for profile in ("full", "fast", "frontend", "backend", "none"):
        assert profile in body
    # The doc must call out that full remains the default safe path.
    assert "default" in body.lower()
    # No-tests / emergency posture must be explicit.
    assert "emergency" in body.lower()
    # The deploy-temp hardening is part of the contract every profile
    # inherits.
    assert "deploy_test_temp.ps1" in body or "basetemp" in body.lower()


def test_deploy_profiles_doc_records_no_ranking_or_order_behavior_change() -> None:
    body = _read(DEPLOY_PROFILES_DOC).lower()
    assert "ranking" in body
    assert "approval" in body or "approve" in body
    assert "paper-order" in body or "paper order" in body
    assert "no" in body  # smoke check that "no <X> change" wording exists


# ── No accidental coupling to recommendation/ranking/order code ─────


def test_deploy_profile_changes_do_not_touch_ranking_or_order_modules() -> None:
    text = _read(DEPLOY_BAT)
    # The deploy script is operational — it must not reference any
    # ranking / approval / paper-order Python module.
    forbidden_modules = (
        "DeterministicRankingEngine",
        "build_momentum_ranking_contribution",
        "paper_order",
        "approve_recommendation",
        "promote_to_recommendation",
        "True_Momentum_Continuation",
    )
    for mod in forbidden_modules:
        assert mod not in text, (
            f"deploy script must not reference ranking/approval/order code: {mod}"
        )


# ── Wrapper: source-root resolution via %~dp0 ────────────────────────


def test_wrapper_bat_exists() -> None:
    assert WRAPPER_BAT.exists(), (
        "top-level deploy-macmarket-trader.bat wrapper must exist"
    )


def test_wrapper_bat_resolves_repo_root_from_own_location() -> None:
    """The wrapper must compute the repo root from %~dp0 (its own
    location), never from %CD% or positional args. This is the bug fix
    for: running `.\\deploy-macmarket-trader.bat -TestProfile fast`
    printing SRC = parent of repo root."""
    text = _read(WRAPPER_BAT)
    assert 'REPO_ROOT=%~dp0' in text, (
        "wrapper must derive REPO_ROOT from %~dp0"
    )
    assert 'pushd "%REPO_ROOT%"' in text, (
        "wrapper must pushd to REPO_ROOT before invoking deploy script"
    )
    # Wrapper must not infer the source from the parent of the current
    # working directory.
    assert "%CD%\\.." not in text
    assert "%cd%\\.." not in text.lower() or "%CD%\\.." not in text


def test_wrapper_bat_forwards_args_to_canonical_script() -> None:
    text = _read(WRAPPER_BAT)
    assert re.search(
        r'call\s+"%REPO_ROOT%\\scripts\\deploy_windows\.bat"\s+%\*',
        text,
    ), "wrapper must forward %* to scripts\\deploy_windows.bat"


def test_wrapper_bat_propagates_exit_code() -> None:
    text = _read(WRAPPER_BAT)
    assert "WRAPPER_RC=%ERRORLEVEL%" in text
    assert "exit /b %WRAPPER_RC%" in text


# ── Deploy script: SRC resolution + validation ───────────────────────


def test_deploy_bat_captures_script_dir_before_arg_parsing() -> None:
    """``shift`` can rotate %0, making a later %~dp0 expand to the
    current working directory instead of the script location. The
    deploy script must capture SCRIPT_DIR / SRC at the top, before
    any shift / arg parsing happens."""
    text = _read(DEPLOY_BAT)
    # SCRIPT_DIR must be set before any :PARSE_ARGS label.
    idx_script_dir = text.find('set "SCRIPT_DIR=%~dp0"')
    idx_parse_label = text.find(":PARSE_ARGS")
    assert idx_script_dir != -1, "deploy script must set SCRIPT_DIR from %~dp0"
    assert idx_parse_label != -1, "deploy script must have :PARSE_ARGS label"
    assert idx_script_dir < idx_parse_label, (
        "SCRIPT_DIR must be captured before any shift / arg parsing"
    )
    # SRC must be derived from SCRIPT_DIR up-front too.
    assert re.search(
        r'for\s+%%I\s+in\s+\("%SCRIPT_DIR%\\\.\."\)\s+do\s+set\s+"SRC=%%~fI"',
        text,
    ), "deploy script must derive SRC from %SCRIPT_DIR%\\.. before parsing"
    # SRC derivation must come before :PARSE_ARGS as well.
    idx_src = text.find('SRC=%%~fI')
    assert idx_src != -1 and idx_src < idx_parse_label


def test_deploy_bat_validates_required_repo_files() -> None:
    """SRC validation must require all four canonical repo markers
    (README.md, pyproject.toml, apps\\web, src\\macmarket_trader)."""
    text = _read(DEPLOY_BAT)
    assert 'if not exist "%SRC%\\README.md"' in text
    assert 'if not exist "%SRC%\\pyproject.toml"' in text
    assert 'if not exist "%SRC%\\apps\\web"' in text
    assert 'if not exist "%SRC%\\src\\macmarket_trader"' in text
    # If validation fails the script must surface the computed
    # diagnostics so an operator can find the wrapper bug.
    assert "SCRIPT_DIR" in text
    assert "%CD%" in text


# ── Deploy script: goto-based parser (no fragile parenthesized IF
#    blocks around arg parsing) ──────────────────────────────────────


def test_arg_parser_uses_goto_based_handlers() -> None:
    text = _read(DEPLOY_BAT)
    # Each flag should goto its own labeled handler.
    for label in (
        ":HANDLE_TESTPROFILE",
        ":HANDLE_FORCENOTESTS",
        ":HANDLE_DRYRUN",
    ):
        assert label in text, f"deploy script must define {label}"
    # -TestProfile and -Profile alias both jump to the same handler.
    assert re.search(
        r'if /I "%~1"=="-TestProfile"\s+goto :HANDLE_TESTPROFILE',
        text,
    )
    assert re.search(
        r'if /I "%~1"=="-Profile"\s+goto :HANDLE_TESTPROFILE',
        text,
    )
    # Missing -TestProfile value must error out with code 64.
    assert "ERR_TESTPROFILE_MISSING" in text
    assert "-TestProfile requires a value" in text


def test_arg_parser_does_not_use_emergency_inside_paren_blocks() -> None:
    """Regression: ``set "...=SKIPPED (emergency)"`` and ``echo
    ... -TestProfile none (emergency).`` inside parenthesized IF
    blocks caused the ``... was unexpected at this time.`` parse
    error. The fix replaces them with square-bracket
    ``[emergency]`` strings which the parser never miscounts."""
    text = _read(DEPLOY_BAT)
    assert "(emergency)" not in text or _emergency_only_in_comments(text), (
        "deploy script must not contain literal '(emergency)' outside of comments"
    )
    # The replacement [emergency] markers are still present.
    assert "[emergency]" in text


def _emergency_only_in_comments(text: str) -> bool:
    """``(emergency)`` is acceptable only when it appears inside a
    ``REM`` documentation line — never inside executable code where
    the parser could miscount block parens."""
    for line in text.splitlines():
        stripped = line.strip()
        if "(emergency)" in stripped:
            if not stripped.upper().startswith("REM"):
                return False
    return True


# ── Dry-run mode ─────────────────────────────────────────────────────


def test_deploy_bat_supports_dry_run_flag() -> None:
    text = _read(DEPLOY_BAT)
    assert "-DryRun" in text
    assert ":HANDLE_DRYRUN" in text
    assert ":DRY_RUN_EXIT" in text
    # DryRun must short-circuit before mirror / install / build / restart.
    idx_dry_check = text.find('if "%DRY_RUN%"=="1" goto :DRY_RUN_EXIT')
    idx_mirror = text.find("Mirroring repo to deployment folder")
    idx_pip_install = text.find("Installing backend dependencies")
    idx_start_backend = text.find("Starting backend")
    assert idx_dry_check != -1
    for marker, idx in (
        ("mirror", idx_mirror),
        ("backend install", idx_pip_install),
        ("backend start", idx_start_backend),
    ):
        assert idx > idx_dry_check, (
            f"DRY_RUN short-circuit must precede the {marker} step"
        )


def test_wrapper_bat_skips_pause_on_dry_run() -> None:
    """For -DryRun to be safe to call from automation / unit tests,
    the wrapper must not block on the trailing `pause`."""
    text = _read(WRAPPER_BAT)
    assert "WRAPPER_DRY_RUN" in text
    assert 'if "%WRAPPER_DRY_RUN%"=="0" pause' in text


# ── Opportunistic behavioral test for -DryRun ────────────────────────


@pytest.mark.skipif(
    platform.system() != "Windows" or shutil.which("cmd.exe") is None,
    reason="DryRun behavioral test requires Windows + cmd.exe",
)
def test_wrapper_dry_run_resolves_correct_src_with_fast_profile(tmp_path: Path) -> None:
    """Behavioral check for the SRC-parent-folder bug: running
    ``deploy-macmarket-trader.bat -TestProfile fast -DryRun`` must
    print ``SRC: <repo root>`` (not the parent of the repo) and exit 0
    without mirroring / installing / building / restarting."""
    completed = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(WRAPPER_BAT),
            "-TestProfile",
            "fast",
            "-DryRun",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 0, (
        f"DryRun should exit 0; got {completed.returncode}.\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    out = completed.stdout
    # SRC must resolve to the repo root, not its parent.
    assert f"SRC: {REPO_ROOT}" in out, (
        f"DryRun must print SRC equal to repo root; got:\n{out}"
    )
    assert "Test profile: fast" in out
    # No mirror / install / build / restart should have run.
    for forbidden in (
        "Mirroring repo to deployment folder",
        "Installing backend dependencies",
        "Building frontend",
        "Starting backend",
    ):
        assert forbidden not in out, (
            f"DryRun must not execute step: {forbidden!r}\n{out}"
        )


@pytest.mark.skipif(
    platform.system() != "Windows" or shutil.which("cmd.exe") is None,
    reason="DryRun behavioral test requires Windows + cmd.exe",
)
def test_wrapper_dry_run_no_args_defaults_to_full(tmp_path: Path) -> None:
    completed = subprocess.run(
        ["cmd.exe", "/c", str(WRAPPER_BAT), "-DryRun"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    out = completed.stdout
    assert f"SRC: {REPO_ROOT}" in out
    assert "Test profile: full" in out


@pytest.mark.skipif(
    platform.system() != "Windows" or shutil.which("cmd.exe") is None,
    reason="DryRun behavioral test requires Windows + cmd.exe",
)
def test_wrapper_dry_run_profile_alias_works(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(WRAPPER_BAT),
            "-Profile",
            "fast",
            "-DryRun",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Test profile: fast" in completed.stdout


@pytest.mark.skipif(
    platform.system() != "Windows" or shutil.which("cmd.exe") is None,
    reason="DryRun behavioral test requires Windows + cmd.exe",
)
def test_wrapper_rejects_unknown_profile(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(WRAPPER_BAT),
            "-TestProfile",
            "notaprofile",
            "-DryRun",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(REPO_ROOT),
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 64, completed.stdout + completed.stderr
    assert "Unknown test profile" in completed.stdout


@pytest.mark.skipif(
    platform.system() != "Windows" or shutil.which("cmd.exe") is None,
    reason="DryRun behavioral test requires Windows + cmd.exe",
)
def test_wrapper_rejects_missing_testprofile_value(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(WRAPPER_BAT),
            "-TestProfile",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(REPO_ROOT),
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 64, completed.stdout + completed.stderr
    assert "-TestProfile requires a value" in completed.stdout


# ── Post-schema parser hardening ─────────────────────────────────────


def test_no_parens_inside_top_level_if_block_bodies() -> None:
    """Regression for the post-schema "... was unexpected at this time."
    parse failure. ``echo ... (profile: %TEST_PROFILE%)...`` and
    ``echo ... (tsc --noEmit)...`` lived inside large parenthesized
    IF blocks at script top level. The literal ``(...)`` text in
    those echoes prematurely closed the block parens, leaving the
    parser unable to balance the outer block.

    This test enforces: no echo/set line that lives inside a top-
    level parenthesized IF / FOR block may contain a literal ``(``
    or ``)`` unless the parens are escaped (``^(``, ``^)``) or the
    whole line is a comment. Subroutines reached via ``call :LABEL``
    are exempt because their body is parsed sequentially, not as
    part of any caller's block.
    """
    text = _read(DEPLOY_BAT)
    lines = text.splitlines()

    in_subroutine = False
    paren_depth = 0
    offenders: list[tuple[int, str]] = []

    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        # Label transitions: a `:LABEL` at column 0 starts a subroutine
        # / named region. Reaching another label or the implicit `:END`
        # exits it.
        if stripped.startswith(":") and not stripped.startswith("::"):
            # Subroutine bodies are reached only via `call :LABEL`, so
            # paren_depth is reset at every label boundary.
            in_subroutine = True
            paren_depth = 0
            continue
        # `goto :PARSE_ARGS` etc don't change subroutine status, but
        # falling off the top of the script (before any label) is the
        # top-level region.
        if not in_subroutine:
            # Track parenthesized block depth crudely. Ignore quoted
            # text and `^(` / `^)` escapes.
            cleaned = re.sub(r'"[^"]*"', '', raw)
            cleaned = cleaned.replace("^(", "").replace("^)", "")
            opens = cleaned.count("(")
            closes = cleaned.count(")")
            # We only care about lines that have an echo/set with
            # literal parens inside an open block.
            if paren_depth > 0:
                if re.match(r'\s*(echo|set)\s', raw, re.IGNORECASE):
                    code = re.sub(r'"[^"]*"', '', raw)
                    code = code.replace("^(", "").replace("^)", "")
                    if "(" in code or ")" in code:
                        offenders.append((i, raw.rstrip()))
            paren_depth += opens - closes
            if paren_depth < 0:
                paren_depth = 0
    assert not offenders, (
        "echo/set lines with unescaped () inside top-level parenthesized "
        "blocks (would cause '... was unexpected at this time.'):\n"
        + "\n".join(f"  line {i}: {line}" for i, line in offenders)
    )


# ── Step tracing ─────────────────────────────────────────────────────


def test_deploy_bat_defines_step_subroutine() -> None:
    text = _read(DEPLOY_BAT)
    assert ":STEP" in text
    assert re.search(r":STEP\s*\n\s*echo \[STEP\]\s+%~1", text), (
        "expected a :STEP subroutine that echoes [STEP] <name>"
    )


def test_deploy_bat_traces_key_post_schema_steps() -> None:
    """The deploy script must log named trace steps so the next time a
    deploy fails we can see which step ran last."""
    text = _read(DEPLOY_BAT)
    for step in (
        "validate-source-root",
        "database-check",
        "schema-update",
        "backend-validation-plan",
        "frontend-validation-plan",
        "restart-services",
    ):
        assert f'call :STEP "{step}"' in text, (
            f"deploy script must call :STEP \"{step}\" so failures pinpoint phase"
        )


# ── -ValidateRealPath flag ──────────────────────────────────────────


def test_deploy_bat_supports_validate_real_path_flag() -> None:
    text = _read(DEPLOY_BAT)
    assert "-ValidateRealPath" in text
    assert ":HANDLE_VALIDATEREALPATH" in text
    assert "VALIDATE_REAL_PATH" in text
    # The validate-real-path flag must skip mirror / install / schema /
    # test / build / restart but still walk through the test-plan
    # branching. The script jumps to :POST_SCHEMA_PLAN to skip the
    # side-effectful pre-test phase, and the per-phase guards must
    # short-circuit individual execution calls.
    assert 'if "%VALIDATE_REAL_PATH%"=="1" goto :POST_SCHEMA_PLAN' in text
    # After the plan section it must exit via the dedicated exit label.
    assert ":PLAN_REPORT_DONE" in text


def test_wrapper_bat_skips_pause_on_validate_real_path() -> None:
    text = _read(WRAPPER_BAT)
    assert "-ValidateRealPath" in text
    assert 'if "%WRAPPER_DRY_RUN%"=="0" pause' in text


# ── Subroutine refactor: backend/frontend phases live outside the
#    top-level parenthesized IF blocks that previously broke the parser
#    after schema update ───────────────────────────────────────────────


def test_backend_validation_runs_in_subroutine() -> None:
    text = _read(DEPLOY_BAT)
    assert ":RUN_BACKEND_VALIDATION" in text
    # The pytest call must live inside the subroutine, not inside a
    # top-level `if "%RUN_BACKEND_TESTS%"=="1" (` block.
    after_label = text.split(":RUN_BACKEND_VALIDATION", 1)[1]
    assert "pytest -q -p no:cacheprovider" in after_label


def test_frontend_validation_runs_in_subroutines() -> None:
    text = _read(DEPLOY_BAT)
    for label in (
        ":FRONTEND_PHASE",
        ":INSTALL_FRONTEND_DEPS",
        ":BUILD_FRONTEND",
        ":RUN_TYPESCRIPT_CHECK",
        ":RUN_FRONTEND_VALIDATION",
    ):
        assert label in text, f"deploy script must define {label}"


# ── Opportunistic behavioral tests for -ValidateRealPath ────────────


@pytest.mark.skipif(
    platform.system() != "Windows" or shutil.which("cmd.exe") is None,
    reason="ValidateRealPath behavioral test requires Windows + cmd.exe",
)
def test_wrapper_validate_real_path_fast_reaches_test_plan(tmp_path: Path) -> None:
    """The real-path failure mode was a parser error AFTER schema update
    but BEFORE backend tests ran. ``-ValidateRealPath`` must traverse
    that exact branching without touching the filesystem / DB / venv /
    services, and must exit 0 if the parser can balance the script."""
    completed = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(WRAPPER_BAT),
            "-TestProfile",
            "fast",
            "-ValidateRealPath",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 0, (
        f"ValidateRealPath should exit 0 — a non-zero exit usually means "
        f"the batch parser tripped post-schema.\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    out = completed.stdout
    assert "[STEP] backend-validation-plan" in out
    assert "[STEP] frontend-validation-plan" in out
    assert "Backend validation plan:" in out
    assert "Frontend validation plan:" in out
    # No real side effect should have run.
    for forbidden in (
        "Mirroring repo to deployment folder",
        "Installing backend dependencies",
        "Running backend tests",
        "Installing frontend dependencies",
        "Building frontend",
        "Running TypeScript check",
        "Starting backend",
    ):
        assert forbidden not in out, (
            f"ValidateRealPath must not perform side effect: {forbidden!r}"
        )
    # And the unexpected-at-this-time symptom must not appear.
    assert "was unexpected at this time" not in out.lower()


@pytest.mark.skipif(
    platform.system() != "Windows" or shutil.which("cmd.exe") is None,
    reason="ValidateRealPath behavioral test requires Windows + cmd.exe",
)
def test_wrapper_validate_real_path_full(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(WRAPPER_BAT),
            "-TestProfile",
            "full",
            "-ValidateRealPath",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    out = completed.stdout
    assert "Test profile: full" in out
    assert "[STEP] backend-validation-plan" in out
    assert "[STEP] frontend-validation-plan" in out
    assert "was unexpected at this time" not in out.lower()


@pytest.mark.skipif(
    platform.system() != "Windows" or shutil.which("cmd.exe") is None,
    reason="ValidateRealPath behavioral test requires Windows + cmd.exe",
)
def test_wrapper_validate_real_path_no_args_defaults_full(tmp_path: Path) -> None:
    completed = subprocess.run(
        ["cmd.exe", "/c", str(WRAPPER_BAT), "-ValidateRealPath"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Test profile: full" in completed.stdout
    assert "was unexpected at this time" not in completed.stdout.lower()


@pytest.mark.skipif(
    platform.system() != "Windows" or shutil.which("cmd.exe") is None,
    reason="ValidateRealPath behavioral test requires Windows + cmd.exe",
)
def test_wrapper_validate_real_path_frontend_profile_skips_backend(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(WRAPPER_BAT),
            "-TestProfile",
            "frontend",
            "-ValidateRealPath",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    out = completed.stdout
    assert "Backend tests skipped: -TestProfile frontend" in out
    assert "Frontend validation plan:" in out
    assert "was unexpected at this time" not in out.lower()
