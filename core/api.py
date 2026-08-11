"""
[ko]
기존 코드 이동 없음. 아래 심볼들을 각 모듈에서 import 해 re-export. __all__을
명시적으로 선언. 이 파일이 validate_config.py 와 플러그인이 의존하는 공개 계약이다.

[en]
No existing code moved here. Re-exports the symbols below, imported from each module.
__all__ is declared explicitly. This file is the public contract that validate_config.py and plugins depend on.
"""
from core.contract import CONTRACT_VERSION, PluginInfo, plugin
from core.models import (ResolvedJob, FileSession, BatchSession,
                           ExecResult, BatchResult, PresetOption, JobParam,
                           FileContext, GlobalContext)
from core.config import (ConfigLoader,
                           _JOB_STANDARD_KEYS as JOB_STANDARD_KEYS,
                           _validate_param_presets as validate_param_presets)
from core.plugins import load_plugin
from core.context import ContextBuilder, substitute, load_file_list

# [ko] validate_config.py 하위 호환: _ 이름도 함께 노출
# [en] backward compatibility for validate_config.py: also expose the underscore-prefixed names
_JOB_STANDARD_KEYS       = JOB_STANDARD_KEYS
_validate_param_presets  = validate_param_presets

__all__ = [
    "PluginInfo", "plugin", "CONTRACT_VERSION",
    "ResolvedJob", "FileSession", "BatchSession",
    "ExecResult", "BatchResult", "PresetOption", "JobParam",
    "FileContext", "GlobalContext",
    "ConfigLoader", "JOB_STANDARD_KEYS", "validate_param_presets", "load_plugin",
    "ContextBuilder", "substitute", "load_file_list",
    "_JOB_STANDARD_KEYS", "_validate_param_presets",
]
