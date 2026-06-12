from platform import node
import re
import ast

def equation_splitter(step:str): 
    step= step.replace(" ", "").strip()

    if "=" not in step:
        return None
    
    left, right = step.split("=", 1)
    return left, right

def clean_expression(expr: str) -> str:
    expr = expr.replace(" ", "").strip()
    expr = expr.replace("^", "**")
    expr = re.sub(r"(\d)(x|\()",r"\1*\2", expr)
    expr = re.sub(r"(x)\(", r"\1*(", expr)
    expr = re.sub(r"\)(\d|x|\()", r")*\1", expr)
    return expr

def evaluate_expression(expr: str, x_value: float) -> float:
    expr = clean_expression(expr)
    tree = ast.parse(expr, mode='eval')
    return _eval_node(tree.body, x_value)

def _eval_node(node, x_value: float) -> float:
    
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id != "x":
            raise ValueError("Only x is supported right now.")
        return x_value
   
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, x_value)
        right = _eval_node(node.right, x_value)

        if isinstance(node.op, ast.Add):
            return left + right
        
        if isinstance(node.op, ast.Sub):
            return left - right
        
        if isinstance(node.op, ast.Mult):
            return left * right
        
        if isinstance(node.op, ast.Div):
            return left / right
        
        if isinstance(node.op, ast.Pow):
            return left ** right
        
        if isinstance(node, ast.UnaryOp): 
            value = _eval_node(node.operand, x_value)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return value
            
        raise ValueError("Unsupported operation.")
