from App.models import CheckResult
from App.parser import equation_splitter, evaluate_expression

def normalize_string(step: str) -> str:
    return step.replace(" ", "").strip()

def solve_linear_equation(equation: str) -> float:
    equation = normalize_string(equation)
    parts = equation_splitter(equation)

    if parts is None:
        raise ValueError("Not an equation.")

    left, right = parts

    def residual(x_value: float) -> float: 
        return evaluate_expression(left, x_value) - evaluate_expression(right, x_value)
    
    f0=residual(0.0)
    f1=residual(1.0)
    slope = f1 - f0

    if slope == 0:
        if f0 == 0:
            raise ValueError("Infinite solutions.")
        raise ValueError("No solution.")
    return -f0 / slope


def equations_match(prev: str, curr: str) -> bool:
    try:
        prev_solution = solve_linear_equation(prev)
        curr_solution = solve_linear_equation(curr)
    except ValueError:
        return False

    return prev_solution == curr_solution


def detect_first_error(steps: list[str]) -> CheckResult:
    if len(steps) < 2:
        return CheckResult(
            passed=False,
            message="Not enough steps to check.",
            first_error_index=None,
        )

    previous = normalize_string(steps[0])

    for i in range(1, len(steps)):
        current = normalize_string(steps[i])

        if current == "":
            return CheckResult(
                passed=False,
                message=f"Step {i + 1} is empty.",
                first_error_index=i,
            )

        if not equations_match(previous, current):
            return CheckResult(
                passed=False,
                message=f"Step {i + 1} looks wrong.",
                first_error_index=i,
            )

        previous = current

    return CheckResult(
        passed=True,
        message="No obvious errors detected.",
        first_error_index=None,
    )