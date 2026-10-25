"""The .env contract: it is read, it never beats a real variable, and tests are isolated."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _run(code: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run a snippet in a clean interpreter so import-time loading is real."""
    import os

    base = {k: v for k, v in os.environ.items() if not k.startswith(("PAYPAL_", "BUSINESS_", "SLOTSAVER_"))}
    base["PYTHONPATH"] = str(BACKEND)
    if env:
        base.update(env)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=base,
        timeout=60,
    )


def test_env_file_is_loaded_at_import(tmp_path):
    env_file = BACKEND / ".env"
    original = env_file.read_text() if env_file.is_file() else None
    try:
        env_file.write_text("BUSINESS_NAME=DotenvProofCo\nPAYPAL_MODE=simulated\n")
        result = _run(
            "from app.config import get_settings, DOTENV_LOADED;"
            "print(f'{DOTENV_LOADED}|{get_settings().business_name}')"
        )
        assert result.returncode == 0, result.stderr
        loaded, name = result.stdout.strip().split("|", 1)
        assert loaded == "True"
        assert name == "DotenvProofCo"
    finally:
        if original is None:
            env_file.unlink(missing_ok=True)
        else:
            env_file.write_text(original)


def test_real_environment_variable_beats_the_file():
    env_file = BACKEND / ".env"
    original = env_file.read_text() if env_file.is_file() else None
    try:
        env_file.write_text("BUSINESS_NAME=FromTheFile\nPAYPAL_MODE=simulated\n")
        result = _run(
            "from app.config import get_settings; print(get_settings().business_name)",
            env={"BUSINESS_NAME": "FromTheShell"},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "FromTheShell"
    finally:
        if original is None:
            env_file.unlink(missing_ok=True)
        else:
            env_file.write_text(original)


def test_skip_flag_disables_loading():
    env_file = BACKEND / ".env"
    original = env_file.read_text() if env_file.is_file() else None
    try:
        env_file.write_text("BUSINESS_NAME=ShouldNotBeRead\nPAYPAL_MODE=simulated\n")
        result = _run(
            "from app.config import get_settings, DOTENV_LOADED;"
            "print(f'{DOTENV_LOADED}|{get_settings().business_name}')",
            env={"SLOTSAVER_SKIP_DOTENV": "1"},
        )
        assert result.returncode == 0, result.stderr
        loaded, name = result.stdout.strip().split("|", 1)
        assert loaded == "False"
        assert name == "Northline Appliance Care"
    finally:
        if original is None:
            env_file.unlink(missing_ok=True)
        else:
            env_file.write_text(original)


def test_a_populated_env_file_cannot_break_the_test_suite():
    """The suite must be hermetic even for a developer with real sandbox keys."""
    env_file = BACKEND / ".env"
    original = env_file.read_text() if env_file.is_file() else None
    try:
        env_file.write_text(
            "PAYPAL_MODE=sandbox\nPAYPAL_CLIENT_ID=RealLookingId\n"
            "PAYPAL_CLIENT_SECRET=RealLookingSecret\nBUSINESS_NAME=DevMachine\n"
        )
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_happy_path.py", "-q"],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-800:]
    finally:
        if original is None:
            env_file.unlink(missing_ok=True)
        else:
            env_file.write_text(original)
