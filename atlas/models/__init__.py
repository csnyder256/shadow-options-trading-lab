"""LLM-client layer. Post-pivot (2026-07-10, all-in options): only the transport clients
(`llm_client`, `http_client`) live here - the overnight lab's optional local-LLM stage is
the sole consumer. The equity analyst/auditor pipeline (analyst, auditor, merge, anonymize,
swap_manager, serving, dual_model) is archived under attic\\atlas\\models\\ and resolved
LAZILY below so importing this package never drags it; the names raise ImportError with a
pointer if anything still asks for them."""

from atlas.models.llm_client import FakeLLMClient, LLMClient, strip_think
from atlas.models.http_client import HttpLLMClient, LLMRequestError

_ARCHIVED = {
    "build_anonymized_thesis": "anonymize", "render_auditor_user_prompt": "anonymize",
    "Analyst": "analyst", "Auditor": "auditor",
    "HARD_FLAGS": "merge", "merge_views": "merge",
    "ModelController": "swap_manager", "ResidentModel": "swap_manager",
    "SwapManager": "swap_manager",
    "LlamaSwapController": "serving", "nvidia_free_vram_gb": "serving",
    "CandidateResult": "dual_model", "DualModelAnalyzer": "dual_model",
    "DualModelResult": "dual_model",
}

__all__ = [
    "FakeLLMClient", "LLMClient", "strip_think",
    "HttpLLMClient", "LLMRequestError",
]


def __getattr__(name: str):  # PEP 562 - archived equity pipeline resolves lazily or fails loud
    if name in _ARCHIVED:
        try:
            import importlib

            mod = importlib.import_module(f"atlas.models.{_ARCHIVED[name]}")
            return getattr(mod, name)
        except ImportError as exc:  # module moved to the attic
            raise ImportError(
                f"atlas.models.{name} belongs to the ARCHIVED equity pipeline "
                f"(attic\\atlas\\models\\{_ARCHIVED[name]}.py - see attic\\ARCHIVE_MANIFEST.md)"
            ) from exc
    raise AttributeError(f"module 'atlas.models' has no attribute {name!r}")
