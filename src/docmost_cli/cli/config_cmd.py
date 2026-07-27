"""Config management subcommands: init, show, set, test, logout."""

import sys

import typer
from rich.console import Console
from rich.table import Table

from docmost_cli.api.auth import AuthError
from docmost_cli.config.store import (
    get_cache_dir,
    get_config_path,
    read_config,
    set_config_value,
    write_config,
)
from docmost_cli.output.formatter import print_error

__all__ = ["config_app"]

config_app: typer.Typer = typer.Typer(name="config", help="Manage configuration.")
_console = Console(stderr=True)


def _get_effective_config_path() -> str | None:
    """Get the config path from global state (set via --config global option)."""
    from docmost_cli.cli.main import state

    return str(state.config_path) if state.config_path else None


def _mask(value: str) -> str:
    """Mask a secret value, showing only the first 4 chars."""
    if len(value) <= 4:
        return "****"
    return value[:4] + "*" * (len(value) - 4)


@config_app.command("init")
def config_init(
    profile: str = typer.Option("default", "--profile", "-p", help="Profile to configure"),
) -> None:
    """Interactive setup wizard for Docmost CLI configuration."""
    _console.print("[bold]Docmost CLI Configuration[/bold]\n")

    url = typer.prompt("Docmost URL (e.g., https://docs.example.com)")
    url = url.rstrip("/")

    _console.print("\nAuthentication method:")
    _console.print("  1. API key (Enterprise edition)")
    _console.print("  2. Email + password (Community/AGPL edition)")
    auth_choice = typer.prompt("Choose", type=int, default=1)

    config_values: dict[str, str] = {"url": url}

    if auth_choice == 1:
        api_key = typer.prompt("API key")
        config_values["api_key"] = api_key
    else:
        email = typer.prompt("Email")
        password = typer.prompt("Password", hide_input=True)
        config_values["email"] = email
        config_values["password"] = password

    path = get_config_path(_get_effective_config_path())
    config = read_config(path)
    config[profile] = config_values
    write_config(config, path)

    _console.print(f"\n[green]Configuration saved to {path}[/green]")
    _console.print(f"Profile: [bold]{profile}[/bold]")
    _console.print("\nRun [bold]docmost-cli config test[/bold] to verify connectivity.")


@config_app.command("show")
def config_show() -> None:
    """Show current configuration (secrets are masked)."""
    from docmost_cli.cli.main import state

    if state.settings:
        values: dict[str, str] = {
            "url": state.settings.url or "",
            "api_key": state.settings.api_key or "",
            "email": state.settings.email or "",
            "password": state.settings.password or "",
            "profile": state.settings.profile,
            "no_session_cache": "true" if state.settings.no_session_cache else "false",
        }
    else:
        values = {"profile": "default"}

    table = Table(title=f"Configuration — profile '{values.get('profile', 'default')}'")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    secret_keys = {"api_key", "password"}
    for key, value in values.items():
        if not value:
            continue
        display = _mask(value) if key in secret_keys else value
        table.add_row(key, display)

    console = Console()
    console.print(table)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Config key to set"),
    value: str = typer.Argument(help="Value to set"),
    profile: str = typer.Option("default", "--profile", "-p", help="Profile to update"),
) -> None:
    """Set a configuration value."""
    valid_keys = {"url", "api_key", "email", "password", "no_session_cache"}
    bool_keys = {"no_session_cache"}
    if key not in valid_keys:
        print_error(f"Unknown config key '{key}'. Valid keys: {', '.join(sorted(valid_keys))}")

    stored: str | bool = value
    if key in bool_keys:
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            stored = True
        elif lowered in {"false", "0", "no", "off"}:
            stored = False
        else:
            print_error(
                f"Invalid boolean value '{value}' for '{key}'. Use 'true' or 'false'.",
                exit_code=2,
            )

    path = get_config_path(_get_effective_config_path())
    set_config_value(key, stored, profile, path)
    _console.print(f"Set [bold]{key}[/bold] in profile '{profile}'")


@config_app.command("logout")
def config_logout() -> None:
    """Delete the cached session token.

    --no-session-cache deliberately does not remove an existing cache file;
    use this to purge one.
    """
    cache = get_cache_dir() / "session.json"
    if cache.exists():
        cache.unlink()
        _console.print(f"Removed cached session token: {cache}")
    else:
        _console.print("No cached session token to remove.")


@config_app.command("test")
def config_test() -> None:
    """Test connectivity and authentication."""
    from docmost_cli.cli.main import get_client

    _console.print("Testing connection...\n")

    try:
        client = get_client()
    except (AuthError, SystemExit) as exc:
        print_error(f"Configuration error: {exc}", exit_code=3)

    try:
        from docmost_cli.api.users import get_current_user

        result = get_current_user(client)
    except SystemExit:
        sys.exit(3)

    name = result.get("name", result.get("email", "Unknown"))
    _console.print("[green]Connected successfully![/green]")
    _console.print(f"Authenticated as: [bold]{name}[/bold]")
    _console.print(f"URL: {client._base_url}")
