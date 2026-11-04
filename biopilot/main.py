"""BioPilot 引擎进程入口：配置管理子命令或启动 Web 适配层。

`biopilot` / `python -m biopilot` 都走这里；配置子命令与 Web 服务都按需导入，
`--help` 不拉起 FastAPI、数据库或模型客户端。
"""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    """解析命令行并分派到配置子命令或 Web 适配层。

    Args:
        argv: 命令行参数；None 时读 ``sys.argv``。

    Returns:
        进程退出码：0 成功，1 失败。
    """
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "config":
        from biopilot.config.cli import config_main
        return config_main(raw[1:])

    parser = argparse.ArgumentParser(
        prog="biopilot",
        description="BioPilot 引擎 Web 适配层（HTTP/SSE）",
        epilog="配置管理：biopilot config import|export|history|rollback")
    # 只为 --help 与参数校验；入口不接受业务旗标，结果不参与分派
    _ = parser.parse_args(raw)

    from biopilot.api import run_server
    run_server()
    return 0


__all__ = ["main"]
