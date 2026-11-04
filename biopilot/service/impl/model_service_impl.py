"""模型清单与会话级模型选择实现。"""
from __future__ import annotations

from biopilot.service import state
from biopilot.service.errors import RequestValidationError
from biopilot.service.model_service import ModelService


class ModelServiceImpl(ModelService):
    """读取可用模型并维护会话级选择。"""

    def list(self, user_id: str) -> dict:
        """返回主模型 + runtime.models 配置条目（不回传 key）。"""
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        items = [{"name": m.get("name") or m.get("model", ""),
                  "model": m.get("model", ""),
                  "current": False}
                 for m in cfg.runtime.models]
        items.insert(0, {"name": "默认主模型", "model": cfg.llm.model,
                         "current": True})
        return {"models": items,
                "selected": state.user_models.get(user_id),
                "base_model": cfg.llm.model}

    def select(self, user_id: str, name: str) -> dict:
        """会话级模型选择：本用户后续 run 用所选模型。"""
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        if name and name != "默认主模型":
            if cfg.runtime.find_model_entry(name) is None:
                raise RequestValidationError(f"未知模型：{name}")
            state.user_models[user_id] = name
        else:
            state.user_models[user_id] = None    # 回到主模型
        return {"status": "ok", "selected": state.user_models.get(user_id)}
