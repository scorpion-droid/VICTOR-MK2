from App.models import CheckResult
from App.algebra import step_signature

def detect_first_error(steps: list[str]) -> CheckResult:
    if len(steps) < 2:
        return CheckResult(passed=False, message = "Not enough steps to check.", first_error_index=None)
    
    previous_signature = step_signature(steps[0])

    for i in range(1, len(steps)):
        current=steps[i].strip()

        if current == "":
            return CheckResult(passed=False, message=f"Step {i + 1} is empty.", first_error_index=i)
        
        current_signature = step_signature(current)

        if current_signature != previous_signature:
            return CheckResult(
                passed=False,
                message=f"Step {i + 1} looks wrong.",
                first_error_index=i,
            )

        previous_signature = current_signature

    return CheckResult(
        passed=True,
        message="No obvious errors detected.",
        first_error_index=None,
    )