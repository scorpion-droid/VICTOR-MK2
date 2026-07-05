from __future__ import annotations

import re

from sympy import Eq, Poly, Symbol, expand, simplify, srepr, solve
from sympy.parsing.sympy_parser import parse_expr

from App.parser import LOCAL_DICT, TRANSFORMATIONS, clean_expression

RELATION_OPERATORS = ("<=", ">=", "=", "<", ">")


def _parse_math_expression(expression: str):
    try:
        return parse_expr(
            clean_expression(expression),
            transformations=TRANSFORMATIONS,
            local_dict=LOCAL_DICT,
            evaluate=True,
        )
    except Exception as exc:
        raise ValueError(f"Could not parse expression: {expression}") from exc


def _canonicalize_symbols(expr):
    free_symbols = sorted(expr.free_symbols, key=lambda symbol: symbol.name)
    if not free_symbols:
        return expr

    replacements = {
        symbol: Symbol(f"v{i}") for i, symbol in enumerate(free_symbols)
    }
    return expr.xreplace(replacements)


def _canonicalize_expression(expr):
    expr = simplify(expr)
    expr = expand(expr)
    expr = _canonicalize_symbols(expr)
    return expr


def _expression_signature(expr) -> str:
    return srepr(_canonicalize_expression(expr))


def _equation_difference_signature(diff) -> str:
    diff = simplify(diff)

    try:
        free_symbols = sorted(diff.free_symbols, key=lambda symbol: symbol.name)
        poly = Poly(diff, *free_symbols) if free_symbols else Poly(diff)
        if not poly.is_zero:
            diff = _canonicalize_expression(poly.monic().as_expr())
            return srepr(diff)
    except Exception:
        pass

    return _expression_signature(diff)


def _split_step_parts(step: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;\n]+", step) if part.strip()]


def split_step_parts(step: str) -> list[str]:
    return _split_step_parts(step)


def _split_relation(part: str):
    for operator in ("<=", ">=", "=", "<", ">"):
        if operator in part:
            left, right = part.split(operator, 1)
            return left, operator, right
    return None


def _flip_relation(operator: str) -> str:
    return {
        "<": ">",
        ">": "<",
        "<=": ">=",
        ">=": "<=",
    }[operator]


def _normalize_inequality(left, operator: str, right):
    diff = simplify(left - right)
    diff = _canonicalize_expression(diff)

    try:
        free_symbols = sorted(diff.free_symbols, key=lambda symbol: symbol.name)
        poly = Poly(diff, *free_symbols) if free_symbols else Poly(diff)
        lead_coeff = poly.LC()
        if getattr(lead_coeff, "is_number", False):
            if lead_coeff.is_negative:
                operator = _flip_relation(operator)
    except Exception:
        pass

    return operator, diff


def _part_signature(part: str):
    relation = _split_relation(part)
    if relation is None:
        try:
            return ("expression", _expression_signature(_parse_math_expression(part)))
        except Exception:
            return ("expression", "parse_error")

    left_text, operator, right_text = relation
    try:
        left = _parse_math_expression(left_text)
        right = _parse_math_expression(right_text)
    except Exception:
        return ("equation", "parse_error")

    if operator == "=":
        return ("equation", _equation_difference_signature(left - right))

    normalized_operator, diff = _normalize_inequality(left, operator, right)
    return ("inequality", normalized_operator, _expression_signature(diff))


def _parse_relation(part: str):
    relation = _split_relation(part)
    if relation is None:
        return None

    left_text, operator, right_text = relation
    left = _parse_math_expression(left_text)
    right = _parse_math_expression(right_text)
    return left, operator, right


def parse_step_relation(step: str):
    parts = _split_step_parts(step)
    if len(parts) != 1:
        return None
    return _parse_relation(parts[0])


def is_single_symbol(expr) -> bool:
    return getattr(expr, "is_Symbol", False)


def simplify_with_assignment(expr, assignment: dict):
    return simplify(expr.subs(assignment))


def formula_chain_matches(steps: list[str]) -> bool:
    if len(steps) < 2:
        return False

    first_relation = parse_step_relation(steps[0])
    if first_relation is None:
        return False

    formula_lhs, formula_operator, formula_rhs = first_relation
    if formula_operator != "=":
        return False

    assignments = {}
    if is_single_symbol(formula_lhs):
        formula_symbol = formula_lhs
        formula_rhs_expr = formula_rhs
    elif is_single_symbol(formula_rhs):
        formula_symbol = formula_rhs
        formula_rhs_expr = formula_lhs
    else:
        return False

    for index, step in enumerate(steps[1:], start=1):
        if "=" not in step:
            if index != len(steps) - 1:
                return False
            try:
                step_expr = _parse_math_expression(step)
                if simplify_with_assignment(step_expr, assignments) != simplify_with_assignment(formula_rhs_expr, assignments):
                    return False
            except Exception:
                return False
            continue

        relation = parse_step_relation(step)
        if relation is None:
            return False

        left, operator, right = relation
        if operator != "=":
            return False

        if is_single_symbol(left) and left != formula_symbol:
            try:
                assignments[left] = simplify_with_assignment(right, assignments)
            except Exception:
                return False
            continue

        if is_single_symbol(right) and right != formula_symbol:
            try:
                assignments[right] = simplify_with_assignment(left, assignments)
            except Exception:
                return False
            continue

        try:
            expected_rhs = simplify_with_assignment(formula_rhs_expr, assignments)
            left_value = simplify_with_assignment(left, assignments)
            right_value = simplify_with_assignment(right, assignments)

            if left_value == formula_symbol and right_value == expected_rhs:
                continue
            if right_value == formula_symbol and left_value == expected_rhs:
                continue
            if simplify(left_value - expected_rhs) == 0:
                continue
            if simplify(right_value - expected_rhs) == 0:
                continue
            if simplify(left_value - formula_symbol) == 0:
                return False
            if simplify(right_value - formula_symbol) == 0:
                return False
            if left_value == right_value:
                continue
            if left_value == expected_rhs or right_value == expected_rhs:
                continue
            return False
        except Exception:
            return False

    return True


def solve_system_from_steps(steps: list[str]):
    equations = []
    symbols = set()

    for step in steps:
        for part in _split_step_parts(step):
            relation = _split_relation(part)
            if relation is None or relation[1] != "=":
                return None

            left_text, _, right_text = relation
            try:
                left = _parse_math_expression(left_text)
                right = _parse_math_expression(right_text)
            except Exception:
                return None
            equations.append(Eq(left, right))
            symbols.update(left.free_symbols)
            symbols.update(right.free_symbols)

    if len(equations) < 2:
        return None

    ordered_symbols = sorted(symbols, key=lambda symbol: symbol.name)
    if not ordered_symbols:
        return None

    try:
        solution = solve(equations, ordered_symbols, dict=True)
    except Exception:
        return None

    if len(solution) != 1:
        return None

    return solution[0]


def can_form_equation_system(steps: list[str]) -> bool:
    equations_seen = 0

    for step in steps:
        for part in _split_step_parts(step):
            relation = _split_relation(part)
            if relation is None or relation[1] != "=":
                return False
            equations_seen += 1

    return equations_seen >= 2


def step_holds_under_assignment(step: str, assignment: dict) -> bool:
    for part in _split_step_parts(step):
        parsed = _parse_relation(part)
        if parsed is None:
            return False

        left, operator, right = parsed
        left_value = simplify(left.subs(assignment))
        right_value = simplify(right.subs(assignment))

        if operator == "=":
            if simplify(left_value - right_value) != 0:
                return False
        elif operator == "<":
            if not bool(left_value < right_value):
                return False
        elif operator == ">":
            if not bool(left_value > right_value):
                return False
        elif operator == "<=":
            if not bool(left_value <= right_value):
                return False
        elif operator == ">=":
            if not bool(left_value >= right_value):
                return False
        else:
            return False

    return True


def _system_signature(parts: list[str]):
    equations = []
    symbols = set()

    for part in parts:
        relation = _split_relation(part)
        if relation is None or relation[1] != "=":
            return tuple(sorted(_part_signature(part) for part in parts))

        left_text, _, right_text = relation
        try:
            left = _parse_math_expression(left_text)
            right = _parse_math_expression(right_text)
        except Exception:
            return tuple(sorted(_part_signature(part) for part in parts))
        equations.append(Eq(left, right))
        symbols.update(left.free_symbols)
        symbols.update(right.free_symbols)

    ordered_symbols = sorted(symbols, key=lambda symbol: symbol.name)
    try:
        solution = solve(equations, ordered_symbols, dict=True)
        if not solution:
            return ("system", "no_solution")

        canonical_solutions = []
        for solution_map in solution:
            canonical_items = []
            for symbol in ordered_symbols:
                value = solution_map.get(symbol, symbol)
                canonical_value = _canonicalize_expression(value)
                canonical_items.append((symbol.name, srepr(canonical_value)))
            canonical_solutions.append(tuple(canonical_items))

        return ("system", tuple(sorted(canonical_solutions)))
    except Exception:
        return tuple(sorted(_part_signature(part) for part in parts))


def step_signature(step: str):
    cleaned = step.replace(" ", "").strip()
    parts = _split_step_parts(cleaned)

    if not parts:
        return ("empty",)

    if len(parts) > 1:
        system_signature = _system_signature(parts)
        if isinstance(system_signature, tuple) and system_signature and system_signature[0] == "system":
            return system_signature
        return ("system", system_signature)

    signatures = tuple(sorted(_part_signature(part) for part in parts))
    if len(signatures) == 1:
        return signatures[0]
    return ("system", signatures)
