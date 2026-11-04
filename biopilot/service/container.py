"""服务容器：按 Web 配置装配全部应用服务。"""
from __future__ import annotations

from dataclasses import dataclass

from biopilot.domain.runtime_state import RuntimeState
from biopilot.domain.web_config import WebConfig
from biopilot.service.assembly_service import AssemblyService
from biopilot.service.attachment_service import AttachmentService
from biopilot.service.chat_service import ChatService
from biopilot.service.kb_service import KbService
from biopilot.service.model_service import ModelService
from biopilot.service.schedule_service import ScheduleService
from biopilot.service.session_service import SessionService
from biopilot.service.settings_service import SettingsService
from biopilot.service.terminal_service import TerminalService
from biopilot.service.user_service import UserService


@dataclass
class ServiceContainer:
    """一次应用实例持有的全部服务。"""

    config: WebConfig
    runtime: RuntimeState
    assembly: AssemblyService
    attachment: AttachmentService
    session: SessionService
    chat: ChatService
    settings: SettingsService
    model: ModelService
    terminal: TerminalService
    kb: KbService
    schedule: ScheduleService
    user: UserService


def build_services(config: WebConfig, runtime: RuntimeState,
                   agent_factory=None) -> ServiceContainer:
    """按配置装配服务容器（重量组件仍按需懒加载）。"""
    from biopilot.service.impl.assembly_service_impl import AssemblyServiceImpl
    from biopilot.service.impl.attachment_service_impl import AttachmentServiceImpl
    from biopilot.service.impl.chat_service_impl import ChatServiceImpl
    from biopilot.service.impl.kb_service_impl import KbServiceImpl
    from biopilot.service.impl.model_service_impl import ModelServiceImpl
    from biopilot.service.impl.schedule_service_impl import ScheduleServiceImpl
    from biopilot.service.impl.session_service_impl import SessionServiceImpl
    from biopilot.service.impl.settings_service_impl import SettingsServiceImpl
    from biopilot.service.impl.terminal_service_impl import TerminalServiceImpl
    from biopilot.service.impl.user_service_impl import UserServiceImpl

    assembly = AssemblyServiceImpl()
    attachments = AttachmentServiceImpl()
    session = SessionServiceImpl(runtime, attachments)
    chat = ChatServiceImpl(
        config, runtime, assembly, attachments, session,
        agent_factory=agent_factory)
    schedule = ScheduleServiceImpl(
        runtime, agent_factory or assembly.default_agent_factory)
    return ServiceContainer(
        config=config,
        runtime=runtime,
        assembly=assembly,
        attachment=attachments,
        session=session,
        chat=chat,
        settings=SettingsServiceImpl(),
        model=ModelServiceImpl(),
        terminal=TerminalServiceImpl(),
        kb=KbServiceImpl(runtime),
        schedule=schedule,
        user=UserServiceImpl(runtime),
    )
