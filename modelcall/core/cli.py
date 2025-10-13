"""
向后兼容的 CLI 导入文件

注意：此文件保留用于向后兼容，实际 CLI 实现已迁移到 modelcall.cli 模块
如果你的代码中有 `from modelcall.core.cli import main`，它仍然可以工作
但建议更新为 `from modelcall.cli import main`
"""

from __future__ import annotations

import warnings

# 从新的 CLI 模块导入所有内容
from ..cli import main
from ..cli.common import build_fs, run_response_generation as _run_response_generation
from ..cli.pipeline import cmd_pipeline
from ..cli.preprocess import cmd_preprocess_github, cmd_preprocess_repomix
from ..cli.api_call import cmd_api_call
from ..cli.task import cmd_run_task
from ..cli.distillation import cmd_distillation_generate

# 发出弃用警告
warnings.warn(
    "Importing from 'modelcall.core.cli' is deprecated. "
    "Please update your imports to 'from modelcall.cli import main'",
    DeprecationWarning,
    stacklevel=2
)

__all__ = [
    "main",
    "build_fs",
    "_run_response_generation",
    "cmd_pipeline",
    "cmd_preprocess_github",
    "cmd_preprocess_repomix",
    "cmd_api_call",
    "cmd_run_task",
    "cmd_distillation_generate",
]
