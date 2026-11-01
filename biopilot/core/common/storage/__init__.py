"""用户数据文件的统一存取（pool 模式：共享桶 + users/<uid>/ 前缀）。

被 webapi（文档编辑器/上传）、tools（save_document/run_python 产物持久化）
多包消费——归属见 core/common/AGENTS.md 的「第二个消费方」判据。
"""
from biopilot.core.common.storage.user_files import (
    NullUserFileStore,
    UserFileStore,
    make_user_file_store,
    user_file_prefix,
)

__all__ = [
    "NullUserFileStore",
    "UserFileStore",
    "make_user_file_store",
    "user_file_prefix",
]
