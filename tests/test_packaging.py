"""Build the macOS wheel from only the intended package source set."""

import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def test_installer_exposes_user_scripts_through_existing_local_bin(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    installer = project / "install"
    shutil.copy2(ROOT / "install", installer)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    user_base = tmp_path / "python-user"
    user_scripts = user_base / "bin"
    user_scripts.mkdir(parents=True)
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)

    python = fake_bin / "python3"
    python.write_text(
        "#!/bin/sh\n"
        "if [ \"$1 $2\" = \"-m site\" ]; then printf '%s\\n' \"$FAKE_USER_BASE\"; fi\n",
        encoding="utf-8",
    )
    uname = fake_bin / "uname"
    uname.write_text("#!/bin/sh\nprintf 'Linux\\n'\n", encoding="utf-8")
    for executable in (python, uname):
        executable.chmod(0o755)
    for name in ("desktop", "computer-mcp"):
        command = user_scripts / name
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)

    environment = {
        **os.environ,
        "HOME": str(home),
        "FAKE_USER_BASE": str(user_base),
        "PATH": os.pathsep.join((str(fake_bin), str(local_bin), "/bin", "/usr/bin")),
    }
    result = subprocess.run(
        ["/bin/sh", str(installer)],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "Installed desktop and computer-mcp" in result.stdout
    assert (local_bin / "desktop").resolve() == user_scripts / "desktop"
    assert (local_bin / "computer-mcp").resolve() == user_scripts / "computer-mcp"


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS package only")
def test_isolated_wheel_builds_helper_and_both_entry_points(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("pyproject.toml", "setup.py", "MANIFEST.in"):
        shutil.copy2(ROOT / name, stage / name)
    shutil.copytree(ROOT / "desktop", stage / "desktop")
    shutil.copytree(ROOT / "native", stage / "native")
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            ".",
        ],
        cwd=stage,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    wheel = next(wheel_dir.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        helper_name = next(
            name for name in names if name.endswith("desktop/_bin/cghelper")
        )
        helper = archive.read(helper_name)
        entry_points_name = next(
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = archive.read(entry_points_name).decode("utf-8")
    assert helper[:4] == b"\xca\xfe\xba\xbe"
    assert "desktop = desktop.cli:main" in entry_points
    assert "computer-mcp = desktop.mcp_server:main" in entry_points

    environment = tmp_path / "installed"
    subprocess.run(
        [sys.executable, "-m", "venv", str(environment)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    installed_python = environment / "bin" / "python"
    subprocess.run(
        [
            str(installed_python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            str(wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    desktop_help = subprocess.run(
        [str(environment / "bin" / "desktop"), "--help"],
        capture_output=True,
        text=True,
        cwd=environment,
        timeout=10,
    )
    mcp_help = subprocess.run(
        [str(environment / "bin" / "computer-mcp"), "--help"],
        capture_output=True,
        text=True,
        cwd=environment,
        timeout=10,
    )
    initialized = subprocess.run(
        [str(environment / "bin" / "computer-mcp")],
        input='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
        capture_output=True,
        text=True,
        cwd=environment,
        timeout=10,
    )
    helper_probe = subprocess.run(
        [
            str(installed_python),
            "-c",
            "from desktop.platforms.macos import helper_path; print(helper_path())",
        ],
        capture_output=True,
        text=True,
        cwd=environment,
        timeout=10,
    )

    assert desktop_help.returncode == 0
    assert mcp_help.returncode == 0
    assert "stdio" in mcp_help.stdout.lower()
    assert initialized.returncode == 0
    assert json.loads(initialized.stdout)["result"]["serverInfo"]["name"] == "computer-mcp"
    assert helper_probe.returncode == 0, helper_probe.stderr
    installed_helper = Path(helper_probe.stdout.strip())
    assert installed_helper.is_file()
    assert os.access(installed_helper, os.X_OK)
    assert installed_helper.read_bytes()[:4] == b"\xca\xfe\xba\xbe"
