"""通用网络基础设施：与具体业务无关的出网约束。

`endpoint_binding` 是 HTTP 客户端的端点不变量：把客户端绑死在创建时声明的端点
host 上，越界即配置漂移或跨 host 重定向。它不决定「要不要用户点头」——那是
`core/security` 中间件的职责；这里只提供纯函数与请求钩子。外部 URL（搜索结果、
文献链接）的 SSRF 校验归 Java `bio-common-net`，Python 不再直接抓外部地址。
"""
from biopilot.common.net.endpoint_binding import (
    EndpointBindingError,
    assert_endpoint_binding,
    endpoint_guard,
)

__all__ = ["EndpointBindingError", "assert_endpoint_binding", "endpoint_guard"]
