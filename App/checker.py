from App.models import CheckResult
from App.parser import equation_splitter

def normalize_string(step: str) -> str:
    return step.replace(" ", "").strip()

def detect_first_error(steps: list [str]) -> CheckResult: 
    if len(steps)<2: 
        return CheckResult(
            passed=False,
            message="Not enough steps to check.",
            first_error_index=None,
        )

    previous=normalize_string(steps[0])

    for i in range(len(steps)):
        current = normalize_string (steps[i])

        if current == "" :
            return CheckResult(
                passed=False,
                message=f"Step {i+1} is empty.",
                first_error_index=i,
            )

        previous_split = equation_splitter(previous)
        current_split = equation_splitter(current)

        if previous_split is None or current_split is None:
            return CheckResult(
                passed=False,
                message=f"Step {i+1} is not a valid equation.",
                first_error_index=i,
            )
        
        if current == previous: 
            previous = current
            continue

        previous = current

    return CheckResult(
        passed=True,
        message="No obvious errors detected.",
        first_error_index=None,
    )   