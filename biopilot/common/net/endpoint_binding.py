"""HTTP 客户端的端点绑定：请求只准打创建客户端时声明的那个 host。

这不是 SSRF 校验——配置里的目的地是用户显式授权的（本地 Ollama / vLLM 跑
127.0.0.1 必须能连）。它只回答一个问题：「配置说 A，这次请求真的去 A 了吗」。
过去没有任何东西保证这一点，审计里的端点 host 只是事后自报；加上绑定后，
配置漂移与跨 host 重定向在请求发出前就被挡下。

本模块只用标准库：钩子接收的请求对象按鸭子类型处理（httpx 传 ``httpx.Request``），
不引入对 httpx 的依赖。
"""
from urllib.parse import urlparse


class EndpointBindingError(RuntimeError):
    """请求目标与配置声明的端点不一致（配置漂移或跨 host 重定向）。"""


def _netloc_ci(url: str) -> str:
    """取 URL 的 netloc 并小写（host 大小写不敏感，端口原样）。"""
    return (urlparse(url).netloc or "").lower()


def assert_endpoint_binding(base_url: str, url: str) -> None:
    """配置化端点绑定：请求目标必须是配置里声明的那个 host。

    Args:
        base_url: str，配置声明的端点地址（如 https://api.deepseek.com/v1）
        url: str，本次请求的实际地址

    Raises:
        EndpointBindingError: 实际地址的 netloc 与配置不一致
    """
    expected = _netloc_ci(base_url)
    actual = _netloc_ci(url)
    if expected and actual and expected != actual:
        raise EndpointBindingError(
            f"请求目标与配置端点不一致：配置 {expected}，实际 {actual}")


def endpoint_guard(base_url: str):
    """产出一个 httpx 请求钩子：每次出网前校验目标 host 与配置一致。

    挂到客户端的 ``event_hooks={"request": [hook]}`` 上，配置化端点的所有请求
    （含 SDK 内部发起的）都过这一道；校验失败即抛异常，请求不会发出去。

    Args:
        base_url: str，配置声明的端点地址

    Returns:
        callable(request) -> None，接收 httpx.Request 的钩子。
    """
    def _guard(request) -> None:
        assert_endpoint_binding(base_url, str(request.url))
    return _guard
