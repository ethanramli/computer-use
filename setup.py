"""Build the small macOS helper into the wheel; no binary lives in source."""

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.build_py import build_py


def _version() -> str:
    # ponytail: regex the single source; importing desktop at build time
    # would drag package deps into setup.
    text = (
        Path(__file__).resolve().parent / "desktop" / "_version.py"
    ).read_text()
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


class BuildPythonAndMacHelper(build_py):
    def run(self):
        super().run()
        if platform.system() != "Darwin":
            return
        clang = shutil.which("clang")
        if clang is None:
            raise RuntimeError("clang is required to build the macOS cghelper")
        source = Path(__file__).resolve().parent / "native" / "cghelper.c"
        target = Path(self.build_lib) / "desktop" / "_bin" / "cghelper"
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                clang,
                "-O2",
                "-arch",
                "arm64",
                "-arch",
                "x86_64",
                "-o",
                str(target),
                str(source),
                "-framework",
                "CoreGraphics",
                "-framework",
                "ApplicationServices",
                "-framework",
                "ImageIO",
            ],
            check=True,
        )
        os.chmod(target, 0o755)

    def get_outputs(self, include_bytecode=1):
        outputs = super().get_outputs(include_bytecode=include_bytecode)
        helper = Path(self.build_lib) / "desktop" / "_bin" / "cghelper"
        if helper.exists():
            outputs.append(str(helper))
        return outputs


class PlatformDistribution(Distribution):
    def has_ext_modules(self):
        return platform.system() == "Darwin"


setup(
    name="computer-automation",
    version=_version(),
    python_requires=">=3.9",
    packages=["desktop", "desktop.platforms"],
    install_requires=["mss>=9.0; sys_platform == 'darwin'"],
    entry_points={
        "console_scripts": [
            "desktop = desktop.cli:main",
            "computer-mcp = desktop.mcp_server:main",
        ]
    },
    cmdclass={"build_py": BuildPythonAndMacHelper},
    distclass=PlatformDistribution,
)
