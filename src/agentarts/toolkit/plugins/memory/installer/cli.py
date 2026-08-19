"""Typer callbacks for ``agentarts memory install|uninstall|server``.

These callbacks are registered onto the shared ``memory_app`` in
``agentarts.toolkit.cli.memory.commands``.  The business logic is ported from
the original argparse-based ``agentarts-memory`` installer.
"""

from __future__ import annotations

import os
import sys
from typing import Annotated

import typer

from .platforms import detect_all, get_platform
from .server_manager import start as _server_start
from .server_manager import status as _server_status
from .server_manager import stop as _server_stop
from .utils import (
    EscapeInterrupt,
    add,
    confirm,
    ensure_credentials,
    expand,
    find,
    list_all,
    remove,
    select_one,
    set_yes,
)

VALID_TARGETS = ("hermes", "claude", "codex", "opencode", "openclaw")

# Platforms that depend on the local adapter server.
SERVER_DEPENDENT = {"claude", "codex", "opencode"}


def _select_scope(platform_name: str, yes: bool) -> str:
    """Determine install scope (project or global)."""
    platform = get_platform(platform_name)
    if platform and platform.fixed_user_level:
        return "global"
    if yes:
        return "project"
    idx = select_one(
        "Install scope",
        ["Project \u2014 this project only", "Global \u2014 all projects"],
        0,
    )
    return "project" if idx == 0 else "global"


def _check_server_dependency(yes: bool) -> None:
    """Print server dependency hint for claude/codex/opencode."""
    print("\nNote: This platform requires the local adapter server (127.0.0.1:8719).")
    print("  Start it with: agentarts memory server start")
    print("  Configure: HUAWEICLOUD_SDK_MEMORY_API_KEY + AGENTARTS_MEMORY_SPACE_ID")


def _degraded_scan(target: str) -> None:
    """Attempt to find and clean up files when manifest is missing."""
    candidates = {
        "hermes": [expand("~/.hermes/hermes-agent/plugins/memory/agentarts")],
        "claude": [
            expand("~/.claude/agentarts-memory"),
            os.path.join(os.getcwd(), ".claude", "agentarts-memory"),
        ],
        "codex": [
            expand("~/.codex/agentarts-memory"),
            os.path.join(os.getcwd(), ".codex", "agentarts-memory"),
        ],
        "opencode": [expand("~/.config/opencode/plugins/agentarts-memory-capture.ts")],
    }

    found = candidates.get(target, [])
    any_found = False
    for path in found:
        if os.path.exists(path):
            any_found = True
            print(f"  Found leftover: {path}")
            print(f"  Remove manually: rm -rf {path}")

    if not any_found:
        print(f"  No leftover {target} files found.")


def _do_install(target: str | None, global_scope: bool, yes: bool) -> int:
    """Handle the install flow. Returns process exit code."""
    if target is not None and target not in VALID_TARGETS:
        print(
            f"Error: invalid target '{target}'. Choose from: {', '.join(VALID_TARGETS)}",
            file=sys.stderr,
        )
        return 2

    if target == "openclaw":
        print("openclaw \u672a\u5b9e\u73b0\uff0c\u656c\u8bf7\u671f\u5f85")
        return 0

    if target is None:
        detected = detect_all(global_scope)
        if not detected:
            print("\nNo supported platforms detected.")
            print(
                "Install Claude Code, Codex, OpenCode, or Hermes Agent, "
                "then run 'agentarts memory install' again."
            )
            return 1
        print("Detecting platforms...")
        for _, p in detected:
            print(f"  \u2713 {p.display}")
        options = [p.display for _, p in detected]
        idx = select_one("\nSelect platform", options, 0)
        target = detected[idx][0]

    platform = get_platform(target)
    if platform is None:
        print(f"Error: unknown platform '{target}'", file=sys.stderr)
        return 2

    print("\nChecking credentials...")
    creds = ensure_credentials(yes)

    scope = "global" if global_scope else _select_scope(target, yes)

    print(f"\nInstalling {platform.display} ({scope})...")
    result = platform.install(scope, creds, yes)

    add(
        {
            "platform": target,
            "scope": scope,
            "config_dir": result.config_dir,
            "scripts_dir": result.scripts_dir,
            "files": result.files,
            "config_files": result.config_files,
        }
    )

    print(f"\n\U0001f389 Install complete: {platform.display} ({scope})")
    print(f"  Config dir: {result.config_dir}")
    if result.scripts_dir:
        print(f"  Scripts:    {result.scripts_dir}")
    print(f"  Files:      {len(result.files)} deployed")
    if result.config_files:
        print(f"  Config:     {', '.join(result.config_files)}")

    if target in SERVER_DEPENDENT:
        _check_server_dependency(yes)

    print("\nRestart the platform to activate.")
    return 0


def _do_uninstall(target: str | None, global_scope: bool, yes: bool) -> int:
    """Handle the uninstall flow. Returns process exit code."""
    if target is not None and target not in VALID_TARGETS:
        print(
            f"Error: invalid target '{target}'. Choose from: {', '.join(VALID_TARGETS)}",
            file=sys.stderr,
        )
        return 2

    if target == "openclaw":
        print("openclaw \u672a\u5b9e\u73b0\uff0c\u656c\u8bf7\u671f\u5f85")
        return 0

    scope = "global" if global_scope else None

    entry = None
    if target is not None:
        entry = find(target, scope, None)
        if entry is None:
            print(f"\nNo {target} installation found in manifest.")
            print("Attempting degraded scan...")
            _degraded_scan(target)
            return 1
    else:
        all_installs = list_all()
        if not all_installs:
            print("\nNo installations found.")
            return 1
        print("\nInstalled platforms:")
        options = [
            f"{i['platform']} ({i.get('scope', '?')}) \u2014 {i.get('config_dir', '?')}"
            for i in all_installs
        ]
        idx = select_one("Select installation to remove", options, 0)
        entry = all_installs[idx]
        target = entry["platform"]

    platform = get_platform(target)
    if platform is None:
        print(f"Error: unknown platform '{target}'", file=sys.stderr)
        return 2

    if not yes and not confirm(
        f"Remove {platform.display} from {entry.get('config_dir', '?')}?",
        default=True,
    ):
        print("Cancelled.")
        return 0

    print(f"\nUninstalling {platform.display}...")
    platform.uninstall(entry)

    remove(
        target,
        entry.get("scope", ""),
        entry.get("config_dir", ""),
    )

    print(f"\n\U00002705 Uninstall complete: {platform.display}")
    print("Restart the platform to apply changes.")
    return 0


def install_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help=f"Platform ({', '.join(VALID_TARGETS)}). Omit to detect."),
    ] = None,
    global_scope: Annotated[
        bool, typer.Option("--global", help="Install to user-level config.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Auto-confirm all prompts.")
    ] = False,
) -> None:
    """Install the AgentArts Memory plugin for a supported AI agent."""
    set_yes(yes)
    try:
        code = _do_install(target, global_scope, yes)
    except EscapeInterrupt:
        print("\nCancelled.")
        code = 0
    if code:
        raise typer.Exit(code)


def uninstall_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help=f"Platform ({', '.join(VALID_TARGETS)}). Omit to select."),
    ] = None,
    global_scope: Annotated[
        bool, typer.Option("--global", help="Limit to user-level installs.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Auto-confirm all prompts.")
    ] = False,
) -> None:
    """Uninstall an AgentArts Memory plugin."""
    set_yes(yes)
    try:
        code = _do_uninstall(target, global_scope, yes)
    except EscapeInterrupt:
        print("\nCancelled.")
        code = 0
    if code:
        raise typer.Exit(code)


server_app = typer.Typer(
    name="server",
    help="Manage the local AgentArts Memory adapter server (127.0.0.1:8719).",
    add_completion=False,
    no_args_is_help=True,
)


@server_app.command("start")
def server_start_cmd(
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Auto-confirm all prompts.")
    ] = False,
) -> None:
    """Start the local adapter server."""
    set_yes(yes)
    code = _server_start()
    if code:
        raise typer.Exit(code)


@server_app.command("stop")
def server_stop_cmd() -> None:
    """Stop the local adapter server."""
    code = _server_stop()
    if code:
        raise typer.Exit(code)


@server_app.command("status")
def server_status_cmd() -> None:
    """Check the local adapter server status."""
    code = _server_status()
    if code:
        raise typer.Exit(code)
