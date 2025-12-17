from __future__ import annotations

from enum import Enum


class ModelTier(str, Enum):
    ANY = "any"
    STANDARD = "standard"
    PREMIUM = "premium"

