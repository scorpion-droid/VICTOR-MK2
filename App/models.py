from dataclasses import dataclass

@dataclass
class CheckResult:
    passed: bool
    message: str
    first_error_index: int | None = None
    error_category: str | None = None
