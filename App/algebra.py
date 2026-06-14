from __future__ import annotations

import ast 
from fractions import Fraction
from platform import node
from turtle import poly

from matplotlib import scale
from matplotlib.pyplot import step
from App.parser import clean_expression, equation_splitter

Polynomial = dict[int, Fraction]

def _normalize(poly: Polynomial) -> Polynomial:
    return {degree: coeff for degree, coeff in poly.items() if coeff != 0}

def _constant(value: int | float | Fraction) -> Polynomial:
    if isinstance(value, Fraction): 
        coeff = value 
    elif isinstance(value, int):
        coeff = Fraction(value, 1)
    elif isinstance(value, float):
        coeff = Fraction(str(value))
    else:
        raise TypeError(f"Unsupported constant type: {type(value)!r}")
    return {0: coeff}

def _x() -> Polynomial: 
    return {1: Fraction(1, 1)}

def _scale(poly: Polynomial, scalar: Fraction) -> Polynomial:
    return _normalize({degree: coeff * scalar for degree, coeff in poly.items()})

def _add(left: Polynomial, right: Polynomial) -> Polynomial:
    result: Polynomial = dict(left)
    for degree, coeff in right.items():
        result[degree] = result.get(degree, Fraction(0,1)) + coeff
    return _normalize(result)

def _sub(left: Polynomial, right: Polynomial) -> Polynomial:
    result: Polynomial = dict(left)
    for degree, coeff in right.items():
        result[degree] = result.get(degree, Fraction(0,1)) - coeff
    return _normalize(result)

def _mul(left: Polynomial, right: Polynomial) -> Polynomial:
    result: Polynomial = {}
    for left_degree, left_coeff in left.items():
        for right_degree, right_coeff in right.items():
            degree = left_degree + right_degree
            coeff = left_coeff * right_coeff
            result[degree] = result.get(degree, Fraction(0,1)) + coeff
    return _normalize(result)

def _pow(poly: Polynomial, exponent: int) -> Polynomial: 
    if exponent < 0:
        raise ValueError("Negative exponents not supported.")  
    result = _constant(1) 
    for _ in range(exponent):
        result = _mul(result, poly)
    return result

def _const_int(poly: Polynomial) -> int: 
    poly = _normalize(poly)
    if set (poly) != {0}:
        raise ValueError("Polynomial is not a constant.")
    coeff = poly[0]
    if coeff.denominator != 1:
        raise ValueError("Polynomial is not an integer constant.")
    return coeff.numerator

def expression_to_poly(expression: str) -> Polynomial:
    tree = ast.parse(clean_expression(expression), mode="eval")
    return _node_to_poly(tree.body)

def _node_to_poly(node: ast.AST) -> Polynomial:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool): 
            raise ValueError("Boolean values are not supported.")
        if isinstance(node.value, (int, float)):
            return _constant(node.value)
        raise ValueError("Only numeric constants are supported.")
    
    if isinstance(node, ast.Name):
        if node.id != "x":
            raise ValueError("Only x is supported right now.")
        return _x()
    
    if isinstance(node, ast.UnaryOp):
        value = _node_to_poly(node.operand)
        if isinstance(node.op, ast.USub):
            return _scale(value, Fraction(-1, 1))
        if isinstance(node.op, ast.UAdd):
            return value
        raise ValueError("Unsupported unary operation.")

    if isinstance(node, ast.BinOp):
        left = _node_to_poly(node.left)
        right = _node_to_poly(node.right)

        if isinstance(node.op, ast.Add):
            return _add(left, right)
        
        if isinstance(node.op, ast.Sub):
            return _sub(left, right)
        
        if isinstance(node.op, ast.Mult):
            return _mul(left, right)
        
        if isinstance(node.op, ast.Div):
            divisor = _const_int(right)
            if divisor == 0:
                raise ValueError("Division by zero.")
            return _scale(left, Fraction(1, divisor))
        
        if isinstance(node.op, ast.Pow):
            exponent = _const_int(right)
            return _pow(left, exponent)
        
        raise ValueError("Unsupported binary operation.")

    raise ValueError("Unsupported expression.")

def normalize_signature (poly: Polynomial) -> tuple[tuple[int, Fraction], ...]:
    poly = _normalize(poly)
    if not poly: 
        return ((0, Fraction(0)),)
    lead_degree = max(poly[lead_degree])
    lead_coeff = poly[lead_degree]
    normalised = scale(poly, Fraction(1,1) / lead_coeff)
    return tuple(sorted(normalised.items()))

def equation_signature(left: str, right: str) -> tuple[tuple[int, Fraction], ...]: 
    left_poly= expression_to_poly(left)
    right_poly= expression_to_poly(right)
    diff = _sub(left_poly, right_poly)
    return normalize_signature(diff)

def step_signature(step: str) -> tuple[tuple[int, Fraction], ...]:
    cleaned = step.replace(" ", "").strip()
    parts = equation_splitter(cleaned)

    if parts is None:
        return ("expression", normalize_signature(expression_to_poly(cleaned)))

    left, right = parts
    return ("equation", equation_signature(left, right))