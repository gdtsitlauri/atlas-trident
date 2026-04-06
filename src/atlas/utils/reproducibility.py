from __future__ import annotations

import os
import random
from typing import Any


def configure_global_seed(seed: int, deterministic_mode: bool = True) -> dict[str, Any]:
    """Configure best-effort global reproducibility across optional libraries."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

    status: dict[str, Any] = {
        "seed": seed,
        "deterministic_mode": deterministic_mode,
        "numpy": False,
        "torch": False,
    }

    try:
        import numpy as np

        np.random.seed(seed)
        status["numpy"] = True
    except Exception:  # noqa: BLE001
        status["numpy"] = False

    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        if deterministic_mode:
            torch.use_deterministic_algorithms(True, warn_only=True)
            if hasattr(torch.backends, "cudnn"):
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False
        status["torch"] = True
    except Exception:  # noqa: BLE001
        status["torch"] = False

    return status
