import os
from google import genai
from App.models import CheckResult
from App.algebra import (
    can_form_equation_system,
    formula_chain_matches,
    solve_system_from_steps,
    step_holds_under_assignment,
    step_signature,
)

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        _gemini_client = genai.Client(api_key=api_key)
    except Exception:
        _gemini_client = None
    return _gemini_client

def get_ai_error_diagnostic(prev_step: str, incorrect_step: str) -> str:
    """
    Calls Gemini to analyze the specific algebraic error between two steps
    when the local numerical checker determines a step is invalid.
    """
    prompt = f"""
    You are an expert algebra teacher's assistant. A student made a mathematical error moving from Step A to Step B.
    
    Step A (Correct): {prev_step}
    Step B (Incorrect): {incorrect_step}
    
    Analyze the transition from Step A to Step B. Identify the exact misconception or mathematical mistake 
    (e.g., Sign Error, Arithmetic Mistake, Incomplete Distribution, Variable Drop).
    
    Provide a concise, encouraging 1-2 sentence explanation directed at the student explaining exactly what they did wrong and how to fix it. Do not solve the entire problem for them.
    """
    client = _get_gemini_client()
    if client is None:
        return "Algebra step validation failed. Check your signs, distribution, or basic calculations."

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt
        )
        return response.text.strip()
    except Exception:
        return "Algebra step validation failed. Check your signs, distribution, or basic calculations."

def detect_first_error(steps: list[str]) -> CheckResult:
    if len(steps) < 2:
        return CheckResult(passed=False, 
                           message = "Not enough steps to check.", 
                           first_error_index=None
                           )

    if formula_chain_matches(steps):
        return CheckResult(
            passed=True,
            message="No obvious errors detected.",
            first_error_index=None,
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
                    prev_context = steps[i - 1] if i > 0 else "Initial Equation"
                    ai_reason = get_ai_error_diagnostic(prev_context, current)
                    
                    return CheckResult(
                        passed=False,
                        message=f"Error on Step {i + 1}: {ai_reason}",
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
        current = steps[i].strip()

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
            ai_reason = get_ai_error_diagnostic(steps[i - 1], current)
            return CheckResult(
                passed=False,
                message=f"Error on Step {i + 1}: {ai_reason}",
                first_error_index=i,
            )
        
        previous_signature = current_signature

    return CheckResult(
        passed=True,
        message="No obvious errors detected.",
        first_error_index=None,
    )
