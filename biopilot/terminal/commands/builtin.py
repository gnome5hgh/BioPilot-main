# biopilot/terminal/commands/builtin.py
"""内置斜杠命令：handler 实现 + 默认注册表。

每条 handler 的签名是 (args, ctx) -> None，退出用 SlashCommand.exits 标志表达
而不是 return 值——handler 无法 break 主循环。输出一律经 ctx.renderer，需要
读输入/确认的经 ctx.io。
"""

from .registry import CommandContext, CommandRegistry, SlashCommand


def _exit_handler(args: list[str], ctx: CommandContext) -> None:
    """退出命令的占位 handler（退出由 SlashCommand.exits 标志表达）。

    Args:
        args: list[str]，命令参数（未使用）
        ctx: CommandContext，依赖袋（未使用）
    """
    pass  # 退出由 SlashCommand.exits 标志表达，handler 无事可做


def _version_handler(args: list[str], ctx: CommandContext) -> None:
    """/version：打印已安装的 biopilot 版本。

    Args:
        args: list[str]，命令参数（未使用）
        ctx: CommandContext，依赖袋
    """
    from importlib.metadata import PackageNotFoundError, version
    try:
        v = version("biopilot")
    except PackageNotFoundError:
        v = "unknown（开发环境：见 pyproject.toml）"
    ctx.renderer.print(f"biopilot {v}")


def _help_handler(args: list[str], ctx: CommandContext,
                  registry: CommandRegistry) -> None:
    """/help：按注册顺序列出可用命令。

    Args:
        args: list[str]，命令参数（未使用）
        ctx: CommandContext，依赖袋
        registry: CommandRegistry，命令来源
    """
    lines = ["可用命令："]
    for cmd in registry.all_commands():
        lines.append(f"  {cmd.usage}  {cmd.help}")
    ctx.renderer.print("\n".join(lines))


def build_default_registry(context: CommandContext) -> CommandRegistry:
    """内置命令注册表；/help 收尾注册以闭包持有 registry 自身。

    Args:
        context: CommandContext，handler 共用的依赖袋

    Returns:
        注册好全部内置命令的 CommandRegistry。
    """
    registry = CommandRegistry(context)
    registry.register(SlashCommand("exit", "/exit", "退出 REPL",
                                   _exit_handler, exits=True))
    registry.register(SlashCommand("version", "/version", "显示版本号",
                                   _version_handler))
    registry.register(SlashCommand(
        "help", "/help", "列出全部命令",
        lambda args, ctx: _help_handler(args, ctx, registry)))
    return registry
