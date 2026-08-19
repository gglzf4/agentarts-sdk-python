"""Entry point to launch the AgentArts Memory adapter server."""

from __future__ import annotations

import logging
import os
import sys

# Configure logger
logger = logging.getLogger("agentarts_memory_code_agent")

# Server version
SERVER_VERSION = "1.0.0"

# Required environment variables for AgentArts Memory
REQUIRED_ENV_VARS = {
    "AGENTARTS_MEMORY_SPACE_ID": "Huawei Cloud AgentArts Memory Space ID",
    "HUAWEICLOUD_SDK_MEMORY_API_KEY": "Huawei Cloud AgentArts Memory API Key",
}

OPTIONAL_ENV_VARS = {
    "HUAWEICLOUD_SDK_REGION": ("Huawei Cloud AgentArts Memory Region", "cn-southwest-2"),
}


def validate_space_id(value: str) -> tuple[bool, str]:
    """Validate Space ID format."""
    if not value or not value.strip():
        return False, "Space ID cannot be empty"
    value = value.strip()
    if len(value) < 8:
        return False, "Space ID must be at least 8 characters"
    return True, value


def validate_api_key(value: str) -> tuple[bool, str]:
    """Validate API Key format."""
    if not value or not value.strip():
        return False, "API Key cannot be empty"
    value = value.strip()
    if len(value) < 16:
        return False, "API Key must be at least 16 characters"
    return True, value


def validate_region(value: str) -> tuple[bool, str]:
    """Validate region format."""
    if not value or not value.strip():
        return True, "cn-southwest-2"
    value = value.strip()
    parts = value.split("-")
    if len(parts) != 3:
        return False, "Region format should be like 'cn-southwest-2'"
    return True, value


VALIDATORS = {
    "AGENTARTS_MEMORY_SPACE_ID": validate_space_id,
    "HUAWEICLOUD_SDK_MEMORY_API_KEY": validate_api_key,
    "HUAWEICLOUD_SDK_REGION": validate_region,
}


def mask_sensitive(value: str, var_name: str) -> str:
    """Mask sensitive values for display."""
    if not value:
        return ""
    if "API_KEY" in var_name or "SECRET" in var_name or "SK" in var_name:
        return "*" * min(len(value), 8)
    if len(value) <= 8:
        return value
    return f"{value[:4]}...{value[-4:]}"


def prompt_for_config(var_name: str, description: str, is_optional: bool = False, default: str = "") -> str:
    """Prompt user for a configuration value with validation."""
    validator = VALIDATORS.get(var_name)

    while True:
        prompt_text = f"\n{description}"
        if is_optional and default:
            prompt_text += f" (default: {default})"
        prompt_text += ": "

        try:
            value = input(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            log_config("\nConfiguration cancelled.")
            sys.exit(1)

        if is_optional and not value:
            value = default

        if validator:
            is_valid, result = validator(value)
            if not is_valid:
                log_config("  ✗ %s", result)
                continue
            value = result

        if not value and not is_optional:
            log_config("  ✗ Value cannot be empty")
            continue

        display_value = mask_sensitive(value, var_name)
        log_config("  ✓ Configured: %s", display_value)
        return value


def check_env_configured() -> tuple[bool, dict[str, str]]:
    """Check if all required environment variables are configured."""
    config = {}

    for var_name in REQUIRED_ENV_VARS:
        value = os.getenv(var_name)
        if not value:
            return False, {}

        validator = VALIDATORS.get(var_name)
        if validator:
            is_valid, result = validator(value)
            if not is_valid:
                return False, {}
            config[var_name] = result
        else:
            config[var_name] = value

    for var_name, (_, default) in OPTIONAL_ENV_VARS.items():
        value = os.getenv(var_name)
        if value:
            validator = VALIDATORS.get(var_name)
            if validator:
                is_valid, result = validator(value)
                config[var_name] = result if is_valid else default
            else:
                config[var_name] = value
        else:
            config[var_name] = default

    return True, config


def interactive_config() -> dict[str, str]:
    """Interactive configuration prompt for missing values."""
    config = {}
    missing_required = []

    log_config("")
    log_config("=" * 60)
    log_config("AgentArts Memory Server Configuration")
    log_config("=" * 60)

    for var_name, description in REQUIRED_ENV_VARS.items():
        value = os.getenv(var_name)
        if value:
            validator = VALIDATORS.get(var_name)
            if validator:
                is_valid, result = validator(value)
                if is_valid:
                    config[var_name] = result
                    continue
                log_config("Invalid %s: %s", description, result)
                value = None

        if not value:
            missing_required.append((var_name, description))

    for var_name, (_, default) in OPTIONAL_ENV_VARS.items():
        value = os.getenv(var_name)
        if value:
            validator = VALIDATORS.get(var_name)
            if validator:
                is_valid, result = validator(value)
                if is_valid:
                    config[var_name] = result
                    continue

        config[var_name] = value or default

    if not missing_required:
        log_config("")
        log_config("✓ All required environment variables are configured.")
        return config

    log_config("")
    log_config("Missing required configuration:")
    for var_name, description in missing_required:
        config[var_name] = prompt_for_config(var_name, description)

    for var_name, (description, default) in OPTIONAL_ENV_VARS.items():
        if not os.getenv(var_name):
            log_config("")
            log_config("ℹ Optional: %s", description)
            try:
                configure = input(f"  Configure {description}? [y/N]: ").strip().lower()
                if configure in ("y", "yes"):
                    config[var_name] = prompt_for_config(var_name, description, is_optional=True, default=default)
            except (EOFError, KeyboardInterrupt):
                log_config("")
                config[var_name] = default

    return config


def apply_config(config: dict[str, str]) -> None:
    """Apply configuration to environment variables."""
    for var_name, value in config.items():
        if value:
            os.environ[var_name] = value


def save_config_to_shell_rc(config: dict[str, str]) -> None:
    """Optionally save configuration to shell rc file."""
    if not config:
        return

    log_config("")
    log_config("-" * 60)
    try:
        save = input("Save configuration to ~/.zshrc for persistence? [y/N]: ").strip().lower()
        if save not in ("y", "yes"):
            return
    except (EOFError, KeyboardInterrupt):
        log_config("")
        return

    rc_file = os.path.expanduser("~/.zshrc")
    if not os.path.exists(rc_file):
        log_config("%s not found, skipping save.", rc_file)
        return

    config_lines = ["\n# AgentArts Memory Server Configuration"]
    for var_name in REQUIRED_ENV_VARS:
        if var_name in config:
            config_lines.append(f'export {var_name}="{config[var_name]}"')

    for var_name in OPTIONAL_ENV_VARS:
        if var_name in config and config[var_name]:
            config_lines.append(f'export {var_name}="{config[var_name]}"')

    config_lines.append("")

    try:
        with open(rc_file, "a") as f:
            f.write("\n".join(config_lines))
        log_config("✓ Configuration saved to %s", rc_file)
        log_config("  Run 'source ~/.zshrc' or restart terminal to apply.")
    except Exception as e:
        log_config("Failed to save: %s", e)


def setup_logging(log_level: str = "info") -> None:
    """Configure logging for the application.

    Runtime logs (API requests, SDK calls) include timestamp with milliseconds and level.
    Startup config logs remain plain for better readability.
    """
    import time

    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create a custom formatter for runtime logs with milliseconds
    class MillisecondFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            ct = self.converter(record.created)
            if datefmt:
                s = time.strftime(datefmt, ct)
            else:
                s = time.strftime("%Y-%m-%d %H:%M:%S", ct)
            return "%s,%03d" % (s, int((record.created - int(record.created)) * 1000))

    formatter = MillisecondFormatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Configure root logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [handler]

    # Set our logger
    logger.setLevel(level)

    if log_level.lower() != "debug":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def log_config(message: str, *args) -> None:
    """Log startup configuration messages without timestamp (plain format)."""
    if args:
        message = message % args
    print(message)


def log_startup_info(config: dict[str, str], log_level: str, host: str, port: int) -> None:
    """Log server startup information (plain format, no timestamp)."""
    log_config("")
    log_config("=" * 60)
    log_config("AgentArts Memory Server v%s", SERVER_VERSION)
    log_config("=" * 60)
    log_config("  Address: %s:%s", host, port)
    log_config("  Space ID: %s", mask_sensitive(config.get("AGENTARTS_MEMORY_SPACE_ID", ""), "SPACE_ID"))
    log_config("  Region: %s", config.get("HUAWEICLOUD_SDK_REGION", "cn-southwest-2"))
    log_config("  Log Level: %s", log_level)
    log_config("=" * 60)
    log_config("")


def run_server(log_level: str) -> None:
    """Run the uvicorn server."""
    import uvicorn

    host = os.getenv("AGENTARTS_MEMORY_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("AGENTARTS_MEMORY_SERVER_PORT", "8719"))

    uvicorn.run(
        "agentarts.toolkit.plugins.memory.server.app:app",
        host=host,
        port=port,
        log_level=log_level,
    )


def main() -> None:
    """Main entry point with configuration check."""
    log_level = os.getenv("AGENTARTS_MEMORY_LOG_LEVEL", "info")
    setup_logging(log_level)

    is_configured, config = check_env_configured()

    if is_configured:
        log_config("")
        log_config("=" * 60)
        log_config("AgentArts Memory Server v%s", SERVER_VERSION)
        log_config("=" * 60)
        log_config("✓ Environment variables detected, starting server...")
        log_config("  Space ID: %s", mask_sensitive(config.get("AGENTARTS_MEMORY_SPACE_ID", ""), "SPACE_ID"))
        log_config("  Region: %s", config.get("HUAWEICLOUD_SDK_REGION", "cn-southwest-2"))
        log_config("  Log Level: %s", log_level)
        log_config("")

        apply_config(config)

        try:
            run_server(log_level)
        except Exception as e:
            logger.error("Server failed to start: %s", e)
            log_config("Entering interactive configuration...")

            config = interactive_config()
            apply_config(config)
            save_config_to_shell_rc(config)

            host = os.getenv("AGENTARTS_MEMORY_SERVER_HOST", "127.0.0.1")
            port = int(os.getenv("AGENTARTS_MEMORY_SERVER_PORT", "8719"))
            log_startup_info(config, log_level, host, port)

            run_server(log_level)
    else:
        config = interactive_config()
        apply_config(config)
        save_config_to_shell_rc(config)

        host = os.getenv("AGENTARTS_MEMORY_SERVER_HOST", "127.0.0.1")
        port = int(os.getenv("AGENTARTS_MEMORY_SERVER_PORT", "8719"))
        log_startup_info(config, log_level, host, port)

        run_server(log_level)


if __name__ == "__main__":
    main()
