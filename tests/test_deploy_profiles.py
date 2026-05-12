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

The tests are intentionally text-based: invoking the .bat from pytest
would require an interactive Windows shell, which is not portable.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_BAT = REPO_ROOT / "scripts" / "deploy_windows.bat"
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
    # invocation must still exist as the full-profile path.
    assert re.search(
        r'pytest\s+-q\s+-p\s+no:cacheprovider\s+--basetemp\s+"!DEPLOY_PYTEST_BASETEMP!"',
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
