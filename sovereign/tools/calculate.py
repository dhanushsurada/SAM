"""
calculate() agent tool — ast-based safe arithmetic, NOT eval()/exec().

Only numeric literals, + - * / % ** // , parentheses, and unary +/- are
permitted. Names, calls, attribute access, subscripts, comprehensions,
and anything else are rejected outright. This matters because the
expression string can be built from, or influenced by, untrusted
document content (Document Security) — a document-derived value should
never be able to reach arbitrary code execution.
"""

import ast
import operator

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculationError(Exception):
    pass


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalculationError(f"Only numbers are allowed, got {type(node.value).__name__}")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        try:
            return _ALLOWED_BINOPS[type(node.op)](left, right)
        except ZeroDivisionError:
            raise CalculationError("Division by zero")
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand))
    raise CalculationError(f"Expression contains a disallowed element: {type(node).__name__}")


def calculate(expression: str) -> str:
    expression = (expression or "").strip()
    if not expression:
        raise CalculationError("Empty expression")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise CalculationError(f"Could not parse '{expression}' as an arithmetic expression: {e}")
    result = _eval_node(tree)
    return f"{expression} = {result}"
