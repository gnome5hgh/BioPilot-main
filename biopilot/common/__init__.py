"""跨层共享基础设施：无业务语义、被 core/tools/webapi 共同消费的叶子能力。

本包对应后端工程里的 common 层：常量、通用工具、存储原语等。它不得 import
`core` / `tools` / `webapi`，也不承载 BioPilot 业务规则。
"""
