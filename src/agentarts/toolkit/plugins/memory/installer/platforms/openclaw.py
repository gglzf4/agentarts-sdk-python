"""OpenClaw platform adapter (placeholder).

OpenClaw support is not yet implemented.  install/uninstall print a
placeholder message and exit normally.
"""

from __future__ import annotations

from .base import InstallResult, Platform


class OpenClawPlatform(Platform):
    name = "openclaw"
    display = "OpenClaw"
    fixed_user_level = False

    def detect(self) -> bool:
        # We don't know how to detect OpenClaw yet.
        return False

    def config_dir(self, scope: str) -> str:
        return ""

    def install(self, scope: str, creds: dict, yes: bool) -> InstallResult:
        print("openclaw 暂未实现，敬请期待")
        return InstallResult(config_dir="", scripts_dir="", files=[], config_files=[])

    def uninstall(self, entry: dict) -> None:
        print("openclaw 暂未实现，敬请期待")
