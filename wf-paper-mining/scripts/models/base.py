from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from typing import Any


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FlexModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class DetailedViolation(BaseModel):
    file: str
    field: str
    message: str
    severity: str
    value: Any = None
