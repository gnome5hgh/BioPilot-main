"""配置运维命令：导入旧 YAML、导出有效配置、查看历史与回滚。

用法::

    biopilot config import config.yaml
    biopilot config export [--json]
    biopilot config history [--limit 20]
    biopilot config rollback <version>

这些命令只在数据库配置源下工作；DSN 与工作区仍由环境变量/引导文件提供。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from biopilot.config import BioPilotConfig, enable_db_source
from biopilot.config.services import store as config_store
from biopilot.config.services.export import export_json, export_yaml


def _store(config: BioPilotConfig):
    """按当前配置取共享的存储实例。"""
    return config_store.get_store(
        config.runtime.memory_dsn, config.runtime.workspace)


def _updated_by() -> str:
    """命令行操作人：优先取终端注入的用户，否则记为 cli。"""
    return os.environ.get("BIOPILOT_USER_ID") or "cli"


def config_main(argv: list[str] | None = None) -> int:
    """配置子命令入口。

    Args:
        argv: 去掉 ``config`` 之后的参数；None 时读 ``sys.argv``。

    Returns:
        进程退出码：0 成功，1 失败。
    """
    parser = argparse.ArgumentParser(
        prog="biopilot config",
        description="BioPilot 配置管理（数据库为真相源）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="把旧 config.yaml 导入数据库")
    p_import.add_argument("path", help="旧配置文件路径")
    p_import.add_argument("--force", action="store_true",
                          help="库中已有配置时覆盖")
    p_import.add_argument("--no-rewrite", action="store_true",
                          help="导入后不改写原文件（默认改写为只含引导层）")

    p_export = sub.add_parser("export", help="导出当前有效配置（不含密钥）")
    p_export.add_argument("--json", action="store_true", help="输出 JSON 而不是 YAML")

    p_history = sub.add_parser("history", help="查看保存历史")
    p_history.add_argument("--limit", type=int, default=20)

    p_rollback = sub.add_parser("rollback", help="回滚到某个历史版本")
    p_rollback.add_argument("version", type=int)

    args = parser.parse_args(argv)
    enable_db_source()
    try:
        config = BioPilotConfig.from_env()
        store = _store(config)
        if args.command == "import":
            version = store.import_legacy(
                args.path, updated_by=_updated_by(),
                rewrite=not args.no_rewrite, force=args.force)
            print(f"已导入，当前版本 {version}")
            return 0
        if args.command == "export":
            print(export_json() if args.json else export_yaml())
            return 0
        if args.command == "history":
            rows = store.history(args.limit)
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
            return 0
        if args.command == "rollback":
            version = store.rollback(args.version, updated_by=_updated_by())
            print(f"已回滚，当前版本 {version}")
            return 0
        parser.print_help()
        return 1
    except Exception as exc:
        print(f"配置命令失败：{exc}", file=sys.stderr)
        return 1


__all__ = ["config_main"]
