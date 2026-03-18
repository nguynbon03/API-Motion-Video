"""CLI interface for Kling Proxy — multi-account Motion Control API tool."""

from __future__ import annotations

import json
import logging
import sys

import click

from .config import CONFIG_DIR, CONFIG_FILE, Config
from .pool import AccountPool, AllAccountsFailedError, NoCreditsError


def _json_out(data, indent=2):
    click.echo(json.dumps(data, indent=indent, ensure_ascii=False))


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def main(verbose: bool):
    """Kling Proxy — Multi-account credit pool for Kling AI Motion Control API."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


# ========== Account commands ==========

@main.group()
def account():
    """Manage Kling API accounts."""


@account.command("add")
@click.option("--name", "-n", required=True, help="Human-readable account label.")
@click.option("--access-key", "-ak", required=True, help="Kling Access Key.")
@click.option(
    "--secret-key",
    "-sk",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Kling Secret Key (hidden input).",
)
@click.option("--credits", "-c", default=0.0, type=float, help="Initial credit balance.")
def account_add(name: str, access_key: str, secret_key: str, credits: float):
    """Add a new Kling API account."""
    cfg = Config()
    try:
        acc = cfg.add_account(name, access_key, secret_key, credits)
        click.echo(f"Account '{acc.name}' added (credits: {acc.credits_remaining})")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@account.command("list")
def account_list():
    """List all accounts and credit status."""
    pool = AccountPool()
    status = pool.pool_status()
    click.echo(f"\nTotal accounts: {status['total_accounts']}")
    click.echo(f"Enabled: {status['enabled_accounts']}")
    click.echo(f"Credits remaining: {status['total_credits_remaining']:.1f}")
    click.echo(f"Credits used: {status['total_credits_used']:.1f}")
    click.echo("\n{:<20} {:<8} {:<15} {:<15}".format("NAME", "ENABLED", "REMAINING", "USED"))
    click.echo("-" * 60)
    for a in status["accounts"]:
        click.echo(
            "{:<20} {:<8} {:<15.1f} {:<15.1f}".format(
                a["name"],
                "yes" if a["enabled"] else "NO",
                a["credits_remaining"],
                a["credits_used"],
            )
        )


@account.command("remove")
@click.option("--name", "-n", required=True, help="Account name to remove.")
@click.confirmation_option(prompt="Are you sure you want to remove this account?")
def account_remove(name: str):
    """Remove an account."""
    cfg = Config()
    if cfg.remove_account(name):
        click.echo(f"Account '{name}' removed.")
    else:
        click.echo(f"Account '{name}' not found.", err=True)
        sys.exit(1)


@account.command("set-credits")
@click.option("--name", "-n", required=True, help="Account name.")
@click.option("--credits", "-c", required=True, type=float, help="New credit balance.")
def account_set_credits(name: str, credits: float):
    """Manually set credit balance for an account."""
    cfg = Config()
    if cfg.update_credits(name, credits):
        click.echo(f"Account '{name}' credits set to {credits:.1f}")
    else:
        click.echo(f"Account '{name}' not found.", err=True)
        sys.exit(1)


@account.command("enable")
@click.option("--name", "-n", required=True, help="Account name.")
def account_enable(name: str):
    """Re-enable a disabled account."""
    cfg = Config()
    if cfg.toggle_account(name, True):
        click.echo(f"Account '{name}' enabled.")
    else:
        click.echo(f"Account '{name}' not found.", err=True)
        sys.exit(1)


@account.command("disable")
@click.option("--name", "-n", required=True, help="Account name.")
def account_disable(name: str):
    """Disable an account (skip during rotation)."""
    cfg = Config()
    if cfg.toggle_account(name, False):
        click.echo(f"Account '{name}' disabled.")
    else:
        click.echo(f"Account '{name}' not found.", err=True)
        sys.exit(1)


# ========== Task commands ==========

@main.group()
def task():
    """Create and query Motion Control tasks."""


@task.command("create")
@click.option("--image", "-i", required=True, help="Character image URL or local path.")
@click.option("--video", "-V", required=True, help="Motion reference video URL or local path.")
@click.option("--model", "-m", default="kling-v2-6", help="Model name (kling-v2-6 / kling-v3).")
@click.option("--prompt", "-p", default="", help="Optional text prompt.")
@click.option("--mode", type=click.Choice(["std", "pro"]), default="pro", help="Quality mode.")
@click.option(
    "--orientation",
    type=click.Choice(["image", "video"]),
    default="image",
    help="Character orientation priority.",
)
@click.option("--keep-sound", type=click.Choice(["yes", "no"]), default="no", help="Keep original video sound.")
@click.option("--callback-url", default="", help="Webhook callback URL.")
@click.option("--task-id-ext", default="", help="External task ID for tracking.")
@click.option("--cost", type=float, default=None, help="Override estimated credit cost.")
def task_create(
    image: str,
    video: str,
    model: str,
    prompt: str,
    mode: str,
    orientation: str,
    keep_sound: str,
    callback_url: str,
    task_id_ext: str,
    cost: float,
):
    """Create a Motion Control video task."""
    payload = {
        "model_name": model,
        "image_url": image,
        "video_url": video,
        "character_orientation": orientation,
        "mode": mode,
        "keep_original_sound": keep_sound,
    }
    if prompt:
        payload["prompt"] = prompt
    if callback_url:
        payload["callback_url"] = callback_url
    if task_id_ext:
        payload["external_task_id"] = task_id_ext

    pool = AccountPool()
    try:
        result = pool.create_motion_task(payload, cost_override=cost)
        proxy_info = result.pop("_proxy", {})
        click.echo(f"\nTask created via account: {proxy_info.get('account', '?')}")
        click.echo(f"Estimated cost: {proxy_info.get('estimated_cost', '?')}")
        click.echo(f"Account credits remaining: {proxy_info.get('credits_remaining', '?')}")
        click.echo("\nAPI Response:")
        _json_out(result)
    except (NoCreditsError, AllAccountsFailedError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@task.command("status")
@click.argument("task_id")
def task_status(task_id: str):
    """Check status of a Motion Control task."""
    pool = AccountPool()
    try:
        result = pool.get_task(task_id)
        _json_out(result)
    except NoCreditsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@task.command("list")
@click.option("--page", default=1, type=int, help="Page number.")
@click.option("--size", default=30, type=int, help="Page size.")
def task_list(page: int, size: int):
    """List Motion Control tasks."""
    pool = AccountPool()
    try:
        result = pool.list_tasks(page, size)
        _json_out(result)
    except NoCreditsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ========== Config commands ==========

@main.group("config")
def config_group():
    """Configuration info."""


@config_group.command("path")
def config_path():
    """Show config file locations."""
    click.echo(f"Config dir:  {CONFIG_DIR}")
    click.echo(f"Config file: {CONFIG_FILE}")
    click.echo(f"Exists: {CONFIG_FILE.exists()}")


@main.command("status")
def pool_status():
    """Show pool status summary."""
    pool = AccountPool()
    status = pool.pool_status()
    _json_out(status)


if __name__ == "__main__":
    main()
