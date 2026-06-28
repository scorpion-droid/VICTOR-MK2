from __future__ import annotations

import re

from sympy import Abs, E, pi, simplify, sqrt
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

TRANSFORMATIONS = standard_transformations + (
    convert_xor,
    implicit_multiplication_application,
)

LOCAL_DICT = {
    "Abs": Abs,
    "E": E,
    "pi": pi,
    "sqrt": sqrt,
    "cm": 1,
    "mm": 1,
    "km": 1,
    "ft": 1,
    "inch": 1,
    "yd": 1,
    "mi": 1,
    "L": 1,
    "ml": 1,
}


def equation_splitter(step: str):
    step = step.replace(" ", "").strip()

    if "=" not in step:
        return None

    left, right = step.split("=", 1)
    return left, right


def clean_expression(expr: str) -> str:
    expr = expr.replace(" ", "").strip()
    expr = expr.replace("π", "pi").replace("Π", "pi")
    expr = expr.replace("×", "*").replace("⋅", "*").replace("·", "*").replace("÷", "/")
    expr = expr.replace("−", "-").replace("—", "-").replace("–", "-")
    expr = expr.replace("√", "sqrt")
    expr = expr.replace("²", "**2").replace("³", "**3")
    expr = re.sub(r"pi(?=[A-Za-z0-9(])", "pi*", expr)
    expr = re.sub(r"pi(?=(?:cm|mm|km|ft|in|yd|mi|L|ml))", "pi*", expr)
    expr = re.sub(r"(?<![A-Za-z])in(?![A-Za-z])", "inch", expr)
    return expr


def _parse_expression(expr: str):
    cleaned = clean_expression(expr)
    try:
        return parse_expr(
            cleaned,
            transformations=TRANSFORMATIONS,
            local_dict=LOCAL_DICT,
            evaluate=True,
        )
    except Exception as exc:
        raise ValueError(f"Could not parse expression: {expr}") from exc


def evaluate_expression(expr: str, x_value: float) -> float:
    parsed = _parse_expression(expr)
    free_symbols = sorted(parsed.free_symbols, key=lambda symbol: symbol.name)

    if not free_symbols:
        result = simplify(parsed)
    elif len(free_symbols) == 1:
        result = simplify(parsed.subs(free_symbols[0], x_value))
    else:
        raise ValueError("Only one variable is supported in evaluate_expression.")

    if getattr(result, "is_Integer", False):
        return int(result)

    if getattr(result, "is_Rational", False) and result.q == 1:
        return int(result)

    if getattr(result, "is_number", False):
        return float(result)

    return result
