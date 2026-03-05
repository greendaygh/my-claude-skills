from __future__ import annotations
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Any


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FlexModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def coerce_null_to_empty_string(cls, values: Any) -> Any:
        """LLM agents sometimes emit null for str fields. Coerce to ''."""
        if not isinstance(values, dict):
            return values
        for field_name, field_info in cls.model_fields.items():
            if field_name in values and values[field_name] is None:
                # Only coerce if the field annotation is pure str (not Optional)
                annotation = field_info.annotation
                if annotation is str:
                    values[field_name] = ""
        return values


class DetailedViolation(BaseModel):
    file: str
    field: str
    message: str
    severity: str
    value: Any = None
