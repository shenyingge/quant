from __future__ import annotations

import json
from collections.abc import Sequence

from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger


def run_cms_check(args: Sequence[str], *, logger_obj=logger) -> int:
    """Output CMS health snapshot as JSON."""
    from src.infrastructure.runtime.cms_server import ProjectCmsChecker

    del logger_obj

    snapshot = ProjectCmsChecker(scope="project").build_snapshot().to_dict()
    pretty = not args or "--compact" not in args
    print(json.dumps(snapshot, ensure_ascii=False, indent=2 if pretty else None))
    return 0 if snapshot["status"] != "down" else 1


def sync_account_positions(
    args: Sequence[str],
    *,
    logger_obj=logger,
) -> int:
    """Refresh account positions snapshot from QMT into Meta DB."""
    from src.trading.account.account_position_sync import sync_account_positions_via_qmt

    source = "manual_cli"
    for arg in args:
        if arg.startswith("--source="):
            source = arg.split("=", 1)[1].strip() or source

    logger_obj.info("正在从 QMT 刷新账户持仓快照, source={}", source)
    synced_rows = sync_account_positions_via_qmt(source=source)
    if synced_rows is None:
        logger_obj.error("账户持仓快照刷新失败")
        return 1

    logger_obj.info("账户持仓快照刷新完成, rows={}", synced_rows)
    return 0


def run_cms_server(
    args: Sequence[str],
    *,
    settings_obj: object = settings,
    logger_obj=logger,
) -> int:
    """Start CMS HTTP service."""
    from src.infrastructure.runtime.cms_server import serve_cms_server

    host = getattr(settings_obj, "cms_server_host")
    port = getattr(settings_obj, "cms_server_port")

    for arg in args:
        if arg.startswith("--host="):
            host = arg.split("=", 1)[1].strip() or host
        elif arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1].strip())
            except ValueError:
                logger_obj.warning("无效的 CMS server 端口参数: {}", arg)

    serve_cms_server(host=host, port=port, scope="project")
    return 0


def run_watchdog(args: Sequence[str]) -> int:
    """Start watchdog service."""
    from src.infrastructure.runtime.watchdog_service import run_watchdog_service

    once = False
    dry_run = False

    for arg in args:
        if arg == "--once":
            once = True
        elif arg == "--dry-run":
            dry_run = True

    run_watchdog_service(once=once, dry_run=dry_run)
    return 0
