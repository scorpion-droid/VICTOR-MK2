from App.models import CheckResult

def normalize_string(step: str) -> str:
    return step.replace(" ", "").strip()

def detect_first_error(steps: list [str]) -> CheckResult: 
    if len(steps)<2: 
        return CheckResult(
            passed=False,
            message="Not enough steps to check.",
            first_error_index=None,
        )

    for i in range(len(steps)):
        current = normalize_string (steps[i])

        if current == "" :
            return CheckResult(
                passed=False,
                message=f"Step {i+1} is empty.",
                first_error_index=i,
            )

    return CheckResult(
        passed=True,
        message="No obvious errors detected.",
        first_error_index=None,
    )   