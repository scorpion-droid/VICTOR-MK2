from App.models import CheckResult
from App.parser import equation_splitter, evaluate_expression

def normalize_string(step: str) -> str:
    return step.replace(" ", "").strip()

def solve_simple_equation(equation: str) -> float:
    equation = normalize_string(equation)
    parts = equation_splitter(equation)

    if parts is None:
        raise ValueError("Not an equation.")

    left, right = parts

    if left == "x":
        return float(right)

    if right == "x":
        return float(left)

    if left.endswith("x") and "+" not in left and "-" not in left[1:]:
        coeff = left[:-1]
        coeff = 1.0 if coeff == "" else float(coeff)
        return float(right) / coeff

    if left.endswith("x") and "+" in left:
        coeff_part, const_part = left.split("x", 1)
        coeff = 1.0 if coeff_part == "" else float(coeff_part)
        const = float(const_part.replace("+", ""))
        return (float(right) - const) / coeff

    raise ValueError(f"Unsupported equation: {equation}")


def equations_match(prev: str, curr: str) -> bool:
    try:
        prev_solution = solve_simple_equation(prev)
        curr_solution = solve_simple_equation(curr)
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