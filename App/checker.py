from App.models import CheckResult
from App.algebra import (
    can_form_equation_system,
    solve_system_from_steps,
    step_holds_under_assignment,
    step_signature,
)

def detect_first_error(steps: list[str]) -> CheckResult:
    if len(steps) < 2:
        return CheckResult(passed=False, 
                           message = "Not enough steps to check.", 
                           first_error_index=None
                           )

    system_assignment = None
    if can_form_equation_system(steps):
        system_assignment = solve_system_from_steps(steps)

    if system_assignment is None:
        system_assignment = solve_system_from_steps(steps[:2])

    if system_assignment is not None:
        for i, current in enumerate(steps):
            current = current.strip()

            if current == "":
                return CheckResult(
                    passed=False,
                    message=f"Step {i + 1} is empty.",
                    first_error_index=i,
                )

            try:
                if not step_holds_under_assignment(current, system_assignment):
                    return CheckResult(
                        passed=False,
                        message=f"Step {i + 1} looks wrong.",
                        first_error_index=i,
                    )
            except Exception as exc:
                return CheckResult(
                    passed=False,
                    message=f"Step {i + 1} could not be read: {exc}",
                    first_error_index=i,
                )

        return CheckResult(
            passed=True,
            message="No obvious errors detected.",
            first_error_index=None,
        )

    try: 
        previous_signature = step_signature(steps[0])
    except Exception as exc: 
        return CheckResult(
            passed=False,
            message=f"Step 1 could not be read: {exc}",
            first_error_index=0,
        )

    for i in range(1, len(steps)):
        current=steps[i].strip()

        if current == "":
            return CheckResult(passed=False, message=f"Step {i + 1} is empty.", first_error_index=i)

        try:
            current_signature = step_signature(current)
        except Exception as exc:
            return CheckResult(
                passed=False,
                message=f"Step {i + 1} could not be read: {exc}",
                first_error_index=i,
            )
        
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
