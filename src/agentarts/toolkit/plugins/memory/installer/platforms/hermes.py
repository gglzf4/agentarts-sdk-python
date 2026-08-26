"""Hermes Agent platform adapter.

Deploys the hermes memory provider (provider.py, plugin.yaml, __init__.py)
to ``~/.hermes/plugins/agentarts/``.

All credentials (API Key, space_id, region) are written to ``~/.hermes/.env``
(deduped by key). Hermes does NOT depend on the local adapter server
(provider connects to the cloud SDK directly).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..utils import (
    ENV_API_KEY,
    ENV_REGION,
    ENV_SPACE_ID,
    expand,
    hermes_files,
    remove_if_empty,
    set_yaml_key,
    status_err,
    status_ok,
    strip_env_keys,
    write_env_file,
)
from .base import InstallResult, Platform

HERMES_HOME = "~/.hermes"
PLUGIN_DIR = "~/.hermes/plugins/agentarts"
ENV_FILE = "~/.hermes/.env"
CONFIG_YAML = "~/.hermes/config.yaml"


class HermesPlatform(Platform):
    name = "hermes"
    display = "Hermes Agent"
    fixed_user_level = True

    def detect(self) -> bool:
        return self._dir_exists(HERMES_HOME)

    def config_dir(self, scope: str) -> str:
        # scope is ignored — hermes is always user-level.
        return expand(PLUGIN_DIR)

    def install(self, scope: str, creds: dict, yes: bool) -> InstallResult:
        plugin_dir = expand(PLUGIN_DIR)
        env_path = expand(ENV_FILE)

        # Phase 1: Deploy plugin files.
        src_files = hermes_files()
        deployed: list[str] = []
        for src in src_files:
            dst = os.path.join(plugin_dir, os.path.basename(src))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            deployed.append(dst)
            status_ok(f"Deploy {os.path.basename(src)}", dst)

        # Phase 2: Write .env (API key, space_id, region).
        env_entries = {var: creds.get(var, "") for var in (ENV_API_KEY, ENV_SPACE_ID, ENV_REGION)}
        env_entries = {k: v for k, v in env_entries.items() if v}
        if env_entries:
            write_env_file(env_path, env_entries)
            status_ok("Write .env", env_path)
        else:
            status_err("Write .env", "Credentials missing")

        # Phase 3: Activate hermes memory provider in config.yaml.
        config_yaml_path = expand(CONFIG_YAML)
        set_yaml_key(config_yaml_path, "memory", "provider", "agentarts")
        status_ok("Activate memory provider", config_yaml_path)

        config_files = [env_path, config_yaml_path]
        return InstallResult(
            config_dir=plugin_dir,
            scripts_dir="",
            files=deployed,
            config_files=config_files,
        )

    def uninstall(self, entry: dict) -> None:
        plugin_dir = expand(PLUGIN_DIR)
        env_path = expand(ENV_FILE)

        # Phase 1: Remove plugin directory.
        p = Path(plugin_dir)
        if p.exists():
            shutil.rmtree(p)
            status_ok("Remove plugin dir", str(p))
            # Clean up empty parent directories up to ~/.hermes.
            parent = p.parent
            hermes_home = expand(HERMES_HOME)
            while parent != Path(hermes_home) and parent.exists():
                try:
                    parent.rmdir()
                    parent = parent.parent
                except OSError:
                    break

        # Phase 2: Strip env keys from .env.
        strip_env_keys(env_path, [ENV_API_KEY, ENV_SPACE_ID, ENV_REGION])
        status_ok("Strip .env", env_path)

        # Phase 3: Deactivate hermes memory provider in config.yaml.
        config_yaml_path = expand(CONFIG_YAML)
        set_yaml_key(config_yaml_path, "memory", "provider", "")
        status_ok("Deactivate memory provider", config_yaml_path)

        # Clean up empty directories.
        remove_if_empty(expand(HERMES_HOME))
