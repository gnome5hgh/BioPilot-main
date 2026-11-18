"""skills 域的端口定义（领域层）：技能清单与技能包的读取契约。

技能管理真相在平台侧（Java 写 ``bio_skill`` + OSS），引擎只做只读消费：
应用层（用户技能物化）只依赖本端口，MySQL 实现与平台包客户端在 adapters
按结构化类型满足，测试传内存假件即可。
"""
from typing import Protocol

__all__ = ["SkillSource", "SkillPackageSource"]


class SkillSource(Protocol):
    """启用技能清单的只读契约。"""

    def read_enabled_skills(self, user_id: str) -> dict[str, str]:
        """读该用户全部启用技能的 name → content_sha 清单。

        Args:
            user_id: 归属用户（行级隔离键）。

        Returns:
            dict[str, str]：启用技能的 name → content_sha。
        """
        ...


class SkillPackageSource(Protocol):
    """技能包字节的获取契约（平台内部端点客户端按结构化类型满足）。"""

    def skill_package(self, user_id: str, name: str) -> tuple[bytes, str]:
        """取一个技能包的字节与头部 sha。

        Args:
            user_id: 归属用户。
            name: 技能名。

        Returns:
            (zip 字节, 包头 sha)；sha 为空串表示端点未回传。
        """
        ...
