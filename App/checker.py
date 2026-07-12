import os
import re
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

def _clean_category_name(category: str) -> str:
    category = re.sub(r"\s+", " ", str(category or "")).strip()
    category = re.sub(r"[^A-Za-z0-9 &/\-]", "", category)
    return category[:60].strip() or "General Misconception"


def get_ai_error_category(
    prev_step: str,
    incorrect_step: str,
    diagnostic: str,
    known_categories: list[str] | None = None,
    class_code: str | None = None,
) -> str:
    """
    Ask Gemini for a short reusable category name for the mistake.
    If existing categories for this class are available, Gemini should prefer reusing one.
    """
    category_hint = ", ".join(known_categories[:20]) if known_categories else "None yet"
    class_text = class_code or "unassigned"
    prompt = f"""
    You are labeling a student's math mistake for analytics in class {class_text}.

    Previous step:
    {prev_step}

    Incorrect step:
    {incorrect_step}

    Teacher diagnostic:
    {diagnostic}

    Existing categories for this class:
    {category_hint}

    Task:
    - Return ONE short category name only.
    - Prefer reusing an existing category if it is a close match.
    - If none fit well, invent a new reusable label.
    - Keep it 2 to 6 words.
    - Use Title Case.
    - Do not include punctuation or extra explanation.
    """
    client = _get_gemini_client()
    if client is None:
        return "General Misconception"

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
        )
        return _clean_category_name(response.text)
    except Exception:
        return "General Misconception"


def get_ai_word_problem_evaluation(
    problem_text: str,
    known_categories: list[str] | None = None,
    class_code: str | None = None,
) -> tuple[bool, str, str]:
    """
    Holistically evaluates a word problem (prose reasoning + setup + final
    answer), rather than checking algebraic step-to-step equivalence.
    Returns (passed, feedback, category). Only ever reveals the FIRST issue
    found, preserving the same "productive struggle" philosophy as the
    step-by-step checker - never the full solution.
    """
    category_hint = ", ".join(known_categories[:20]) if known_categories else "None yet"
    class_text = class_code or "unassigned"

    prompt = f"""
    You are a supportive math teacher's assistant reviewing a student's handwritten
    answer to a word problem in class {class_text}. This may include their reasoning,
    an equation they set up from the words, working, and a final answer - not just
    clean algebra steps.

    Student's submitted work:
    {problem_text}

    Task:
    - Judge whether the reasoning AND final answer are correct overall.
    - If correct, say so plainly.
    - If incorrect, find the FIRST place their reasoning or setup goes wrong
      (e.g. misreading the problem, setting up the wrong equation, a units
      mistake, an arithmetic slip). Do NOT solve the rest of the problem for
      them or reveal the correct final answer - just point at the first issue
      and give a short hint toward fixing it.
    - Keep feedback to 1-3 encouraging sentences.

    Existing mistake categories used in this class: {category_hint}
    Prefer reusing an existing category if it's a close match; otherwise invent
    a new short reusable one (2-6 words, Title Case, no punctuation).

    Respond in exactly this format, with no extra commentary:
    STATUS: PASS or FAIL
    FEEDBACK: <your feedback here>
    CATEGORY: <category name, or NONE if STATUS is PASS>
    """

    client = _get_gemini_client()
    if client is None:
        return False, "Word problem checking is temporarily unavailable. Please try again shortly.", "General Misconception"

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
        )
        text = (response.text or "").strip()
    except Exception:
        return False, "Word problem checking is temporarily unavailable. Please try again shortly.", "General Misconception"

    status_match = re.search(r"STATUS:\s*(PASS|FAIL)", text, re.IGNORECASE)
    feedback_match = re.search(r"FEEDBACK:\s*(.+?)(?:\nCATEGORY:|$)", text, re.IGNORECASE | re.DOTALL)
    category_match = re.search(r"CATEGORY:\s*(.+)", text, re.IGNORECASE)

    passed = bool(status_match and status_match.group(1).upper() == "PASS")
    feedback = feedback_match.group(1).strip() if feedback_match else text or "Could not evaluate this response clearly. Please try again."
    category_raw = category_match.group(1).strip() if category_match else ""
    category = "N/A" if passed else _clean_category_name(category_raw or "General Misconception")

    return passed, feedback, category


def detect_word_problem_error(
    problem_text: str,
    class_code: str | None = None,
    known_categories: list[str] | None = None,
) -> CheckResult:
    if not problem_text or not problem_text.strip():
        return CheckResult(
            passed=False,
            message="There's no written answer to check yet.",
            first_error_index=None,
            error_category="Incomplete Step",
        )

    passed, feedback, category = get_ai_word_problem_evaluation(
        problem_text.strip(),
        known_categories=known_categories,
        class_code=class_code,
    )

    if passed:
        return CheckResult(
            passed=True,
            message=feedback,
            first_error_index=None,
        )

    return CheckResult(
        passed=False,
        message=feedback,
        first_error_index=0,
        error_category=category,
    )


def detect_first_error(
    steps: list[str],
    class_code: str | None = None,
    known_categories: list[str] | None = None,
) -> CheckResult:
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
                    error_category="Incomplete Step",
                )

            try:
                if not step_holds_under_assignment(current, system_assignment):
                    prev_context = steps[i - 1] if i > 0 else "Initial Equation"
                    ai_reason = get_ai_error_diagnostic(prev_context, current)
                    ai_category = get_ai_error_category(prev_context, current, ai_reason, known_categories, class_code)
                    
                    return CheckResult(
                        passed=False,
                        message=f"Error on Step {i + 1}: {ai_reason}",
                        first_error_index=i,
                        error_category=ai_category,
                    )
            except Exception as exc:
                return CheckResult(
                    passed=False,
                    message=f"Step {i + 1} could not be read: {exc}",
                    first_error_index=i,
                    error_category="OCR Or Parsing",
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
            error_category="OCR Or Parsing",
        )

    for i in range(1, len(steps)):
        current = steps[i].strip()

        if current == "":
            return CheckResult(
                passed=False,
                message=f"Step {i + 1} is empty.",
                first_error_index=i,
                error_category="Incomplete Step",
            )

        try:
            current_signature = step_signature(current)
        except Exception as exc:
            return CheckResult(
                passed=False,
                message=f"Step {i + 1} could not be read: {exc}",
                first_error_index=i,
                error_category="OCR Or Parsing",
            )
        
        if current_signature != previous_signature:
            ai_reason = get_ai_error_diagnostic(steps[i - 1], current)
            ai_category = get_ai_error_category(steps[i - 1], current, ai_reason, known_categories, class_code)
            return CheckResult(
                passed=False,
                message=f"Error on Step {i + 1}: {ai_reason}",
                first_error_index=i,
                error_category=ai_category,
            )
        
        previous_signature = current_signature

    return CheckResult(
        passed=True,
        message="No obvious errors detected.",
        first_error_index=None,
    )