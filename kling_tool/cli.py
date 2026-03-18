"""CLI for Kling Tool — account management, task creation, server control."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from . import config as cfg
from .accounts import AccountManager, NoAvailableAccountError
from .database import Database
from .models import AccountStatus, Task, TaskStatus


def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _json_out(data, indent=2):
    click.echo(json.dumps(data, indent=indent, ensure_ascii=False))


def _table(headers, rows):
    """Print a simple table."""
    widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0)) + 2
              for i, h in enumerate(headers)]
    fmt = "".join(f"{{:<{w}}}" for w in widths)
    click.echo(fmt.format(*headers))
    click.echo("-" * sum(widths))
    for row in rows:
        click.echo(fmt.format(*[str(c) for c in row]))


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Debug logging.")
def main(verbose: bool):
    """Kling Tool — Web UI automation + REST API proxy for Motion Control."""
    _setup_logging(verbose)
    cfg.ensure_dirs()


# ═══════════════════════════════════════════════════════════════
# Account commands
# ═══════════════════════════════════════════════════════════════

@main.group()
def account():
    """Manage Kling web accounts."""


@account.command("add")
@click.option("--name", "-n", required=True, help="Account label.")
@click.option("--email", "-e", required=True, help="Kling login email.")
@click.option("--password", "-p", prompt=True, hide_input=True, help="Login password.")
@click.option("--proxy", default="", help="Proxy URL (http:// or socks5://).")
@click.option("--credits", "-c", default=66.0, type=float, help="Initial credits.")
def account_add(name, email, password, proxy, credits):
    """Add a single account."""
    mgr = AccountManager()
    try:
        mgr.add(name, email, password, proxy, credits)
        click.echo(f"Added: {name} ({email}) — credits: {credits}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@account.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--credits", "-c", default=66.0, type=float, help="Default credits per account.")
def account_import(file, credits):
    """Import accounts from file.

    Formats supported:
      email:password
      email:password:proxy
      name|email|password|proxy|credits
    """
    lines = Path(file).read_text(encoding="utf-8").splitlines()
    mgr = AccountManager()
    count = mgr.add_bulk(lines, default_credits=credits)
    click.echo(f"Imported {count} accounts from {file}")


@account.command("list")
def account_list():
    """List all accounts with status."""
    mgr = AccountManager()
    stats = mgr.pool_stats()

    click.echo(f"\nTotal: {stats['total_accounts']}  |  "
               f"Active: {stats['active_accounts']}  |  "
               f"Credits: {stats['total_credits_remaining']:.0f} remaining, "
               f"{stats['total_credits_used']:.0f} used\n")

    headers = ["NAME", "EMAIL", "STATUS", "CREDITS", "USED", "PROXY", "LAST USED"]
    rows = [
        (a["name"], a["email"][:25], a["status"],
         f"{a['credits_remaining']:.0f}", f"{a['credits_used']:.0f}",
         a["proxy"][:20], a["last_used"][:19] if a["last_used"] != "never" else "—")
        for a in stats["accounts"]
    ]
    _table(headers, rows)


@account.command("remove")
@click.option("--name", "-n", required=True)
@click.confirmation_option(prompt="Remove this account?")
def account_remove(name):
    """Remove an account."""
    mgr = AccountManager()
    if mgr.remove(name):
        click.echo(f"Removed: {name}")
    else:
        click.echo(f"Not found: {name}", err=True)


@account.command("set-credits")
@click.option("--name", "-n", required=True)
@click.option("--credits", "-c", required=True, type=float)
def account_set_credits(name, credits):
    """Set credit balance for an account."""
    mgr = AccountManager()
    if mgr.set_credits(name, credits):
        click.echo(f"Credits set: {name} = {credits}")
    else:
        click.echo(f"Not found: {name}", err=True)


@account.command("enable")
@click.option("--name", "-n", required=True)
def account_enable(name):
    """Re-enable a disabled account."""
    mgr = AccountManager()
    mgr.set_status(name, AccountStatus.ACTIVE)
    click.echo(f"Enabled: {name}")


@account.command("disable")
@click.option("--name", "-n", required=True)
def account_disable(name):
    """Disable an account."""
    mgr = AccountManager()
    mgr.set_status(name, AccountStatus.DISABLED)
    click.echo(f"Disabled: {name}")


@account.command("login-test")
@click.option("--name", "-n", required=True, help="Account to test.")
@click.option("--headless/--no-headless", default=True, help="Run browser headless.")
def account_login_test(name, headless):
    """Test login for an account (opens browser)."""
    from .browser import KlingBrowser

    mgr = AccountManager()
    acc = mgr.get(name)
    if not acc:
        click.echo(f"Not found: {name}", err=True)
        sys.exit(1)

    click.echo(f"Testing login for {acc['email']}...")
    browser = KlingBrowser(name, proxy=acc.get("proxy") or None, headless=headless)

    with browser:
        success = browser.login(acc["email"], acc["password"])
        if success:
            click.echo("Login SUCCESS")
            credits = browser.get_credits()
            if credits >= 0:
                click.echo(f"Credits detected: {credits}")
                mgr.set_credits(name, credits)

            # Show intercepted APIs
            apis = browser.get_intercepted_apis()
            if apis:
                click.echo(f"\nIntercepted {len(apis)} internal API calls:")
                for api in apis[:10]:
                    click.echo(f"  {api['method']} {api['url']}")
        else:
            click.echo("Login FAILED")


# ═══════════════════════════════════════════════════════════════
# Task commands
# ═══════════════════════════════════════════════════════════════

@main.group()
def task():
    """Create and manage video tasks."""


@task.command("create")
@click.option("--image", "-i", required=True, help="Character image URL or local path.")
@click.option("--video", "-V", required=True, help="Motion video URL or local path.")
@click.option("--prompt", "-p", default="", help="Text prompt.")
@click.option("--mode", type=click.Choice(["std", "pro"]), default="pro")
@click.option("--model", default="kling-v2-6")
@click.option("--orientation", type=click.Choice(["image", "video"]), default="image")
@click.option("--keep-sound", type=click.Choice(["yes", "no"]), default="yes")
@click.option("--task-id", default="", help="External tracking ID.")
def task_create(image, video, prompt, mode, model, orientation, keep_sound, task_id):
    """Queue a new Motion Control task."""
    db = Database()
    t = Task(
        external_task_id=task_id or f"cli-{__import__('uuid').uuid4().hex[:8]}",
        image_url=image,
        video_url=video,
        prompt=prompt,
        model_name=model,
        mode=mode,
        character_orientation=orientation,
        keep_original_sound=keep_sound,
    )
    tid = db.add_task(t)
    click.echo(f"Task #{tid} queued (ext: {t.external_task_id})")
    click.echo("Start the server to process: kling-tool server start")


@task.command("status")
@click.argument("task_id", type=int)
def task_status(task_id):
    """Check task status."""
    db = Database()
    t = db.get_task(task_id)
    if not t:
        click.echo("Task not found", err=True)
        sys.exit(1)
    _json_out(t)


@task.command("list")
@click.option("--status", "-s", default=None, help="Filter by status.")
@click.option("--page", default=1, type=int)
@click.option("--size", default=20, type=int)
def task_list(status, page, size):
    """List tasks."""
    db = Database()
    tasks = db.get_tasks(status=status, page=page, size=size)
    if not tasks:
        click.echo("No tasks found.")
        return

    headers = ["ID", "STATUS", "ACCOUNT", "MODE", "CREATED", "VIDEO URL"]
    rows = [
        (t["id"], t["status"], t["account_name"] or "—", t["mode"],
         t["created_at"][:19], (t["result_video_url"] or "—")[:40])
        for t in tasks
    ]
    _table(headers, rows)


# ═══════════════════════════════════════════════════════════════
# Server command
# ═══════════════════════════════════════════════════════════════

@main.group()
def server():
    """REST API server control."""


@server.command("start")
@click.option("--host", default=cfg.API_HOST, help="Bind host.")
@click.option("--port", default=cfg.API_PORT, type=int, help="Bind port.")
@click.option("--reload", "do_reload", is_flag=True, help="Auto-reload on code change.")
def server_start(host, port, do_reload):
    """Start the REST API server + background worker."""
    import uvicorn

    click.echo(f"Starting Kling Tool server on {host}:{port}")
    click.echo(f"Dashboard: http://localhost:{port}")
    click.echo(f"API docs:  http://localhost:{port}/docs")
    click.echo(f"Health:    http://localhost:{port}/health")
    click.echo()
    uvicorn.run(
        "kling_tool.server:app",
        host=host,
        port=port,
        reload=do_reload,
        log_level="info",
    )


@server.command("dashboard")
@click.option("--host", default="127.0.0.1", help="Bind host.")
@click.option("--port", default=8686, type=int, help="Bind port.")
@click.option("--reload", "do_reload", is_flag=True, help="Auto-reload.")
def server_dashboard(host, port, do_reload):
    """Start the web dashboard with upload UI + task management."""
    import uvicorn

    click.echo(f"\n  Kling Tool Dashboard")
    click.echo(f"  http://{host}:{port}\n")
    click.echo(f"  Folder structure:")
    click.echo(f"    Images:   {cfg.DATA_DIR / 'inputs' / 'images'}")
    click.echo(f"    Videos:   {cfg.DATA_DIR / 'inputs' / 'videos'}")
    click.echo(f"    Accounts: {cfg.DATA_DIR / 'accounts'}")
    click.echo(f"    Outputs:  {cfg.DATA_DIR / 'outputs'}")
    click.echo()
    uvicorn.run(
        "kling_tool.dashboard:app",
        host=host,
        port=port,
        reload=do_reload,
        log_level="info",
    )


# ═══════════════════════════════════════════════════════════════
# Quick status
# ═══════════════════════════════════════════════════════════════

@main.command("status")
def show_status():
    """Show pool + task summary."""
    mgr = AccountManager()
    db = Database()
    stats = mgr.pool_stats()

    click.echo(f"""
╔══════════════════════════════════════╗
║       KLING TOOL STATUS              ║
╠══════════════════════════════════════╣
║  Accounts: {stats['total_accounts']:<5} (active: {stats['active_accounts']})     ║
║  Credits:  {stats['total_credits_remaining']:<8.0f} remaining       ║
║  Used:     {stats['total_credits_used']:<8.0f} total            ║
╠══════════════════════════════════════╣""")

    for status_name in ["queued", "processing", "succeed", "failed"]:
        count = len(db.get_tasks(status=status_name))
        click.echo(f"║  {status_name.upper():<12} tasks: {count:<14} ║")

    click.echo("╚══════════════════════════════════════╝")


@main.command("config")
def show_config():
    """Show configuration paths."""
    click.echo(f"Data dir:      {cfg.DATA_DIR}")
    click.echo(f"Database:      {cfg.DB_PATH}")
    click.echo(f"Sessions:      {cfg.SESSIONS_DIR}")
    click.echo(f"Downloads:     {cfg.DOWNLOADS_DIR}")
    click.echo(f"Screenshots:   {cfg.SCREENSHOTS_DIR}")


if __name__ == "__main__":
    main()
