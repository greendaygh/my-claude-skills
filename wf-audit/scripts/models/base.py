"""Common base types for wf-audit Pydantic models."""

from dataclasses import dataclass, field
from pydantic import ConfigDict


ALLOW_EXTRA = ConfigDict(extra="allow")


@dataclass
class DetailedViolation:
    """A single violation with enough context to locate and fix it."""

    file: str = ""
    record: str = ""
    path: str = ""
    error: str = ""
    error_type: str = ""  # "missing" | "wrong_type" | "pattern_mismatch" | "value_error"
    fix_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "record": self.record,
            "path": self.path,
            "error": self.error,
            "error_type": self.error_type,
            "fix_hint": self.fix_hint,
        }


def pydantic_errors_to_violations(
    errors: list[dict],
    source_file: str = "",
    record_id: str = "",
) -> list[DetailedViolation]:
    """Convert Pydantic ValidationError.errors() into DetailedViolation list."""
    violations = []
    for err in errors:
        loc_str = ".".join(str(x) for x in err["loc"])
        err_type = err.get("type", "")

        if "missing" in err_type:
            classified = "missing"
        elif "type" in err_type or "bool" in err_type or "int" in err_type:
            classified = "wrong_type"
        elif "pattern" in err_type or "string_pattern" in err_type:
            classified = "pattern_mismatch"
        else:
            classified = "value_error"

        violations.append(DetailedViolation(
            file=source_file,
            record=record_id,
            path=loc_str,
            error=err["msg"],
            error_type=classified,
            fix_hint=_build_fix_hint(err, loc_str),
        ))
    return violations


def _build_fix_hint(err: dict, loc_str: str) -> str:
    err_type = err.get("type", "")
    msg = err.get("msg", "")

    if "missing" in err_type:
        return f"'{loc_str}' 필드를 추가하세요"
    if "type" in err_type:
        expected = err.get("ctx", {}).get("expected", "")
        if expected:
            return f"'{loc_str}' 필드의 타입을 {expected}(으)로 변경하세요"
        return f"'{loc_str}' 필드의 타입이 올바르지 않습니다: {msg}"
    if "pattern" in err_type:
        pattern = err.get("ctx", {}).get("pattern", "")
        return f"'{loc_str}' 값이 패턴 {pattern}에 맞지 않습니다"
    return f"'{loc_str}': {msg}"
