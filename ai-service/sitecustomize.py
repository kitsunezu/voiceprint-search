"""Runtime shims for third-party packages used in subprocess tools.

This file is loaded only when ``PYTHONPATH`` includes ``/app``. We use it to
make audio-separator tolerant of torchvision builds that omit optional custom
ops such as ``torchvision::nms`` on CPU-only images.
"""

from __future__ import annotations


def _patch_torchvision_register_fake() -> None:
    try:
        import torch.library as torch_library
    except Exception:
        return

    original = getattr(torch_library, "register_fake", None)
    if original is None or getattr(original, "_voiceprint_safe", False):
        return

    def safe_register_fake(op_name: str, *args, **kwargs):
        decorator = original(op_name, *args, **kwargs)

        def wrapped(fn):
            try:
                return decorator(fn)
            except RuntimeError as exc:
                if op_name.startswith("torchvision::") and "does not exist" in str(exc):
                    return fn
                raise

        return wrapped

    safe_register_fake._voiceprint_safe = True  # type: ignore[attr-defined]
    torch_library.register_fake = safe_register_fake


_patch_torchvision_register_fake()