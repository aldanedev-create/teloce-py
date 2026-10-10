"""Compile the supported JavaScript expression subset to safe render instructions."""

from __future__ import annotations

import math
from decimal import Decimal
from dataclasses import fields

from teloce.expressions.ast import ExpressionNode
from teloce.expressions.lexer import ExpressionLexer
from teloce.expressions.parser import ExpressionParser

UNDEFINED = object()
BLOCKED = {"__proto__", "prototype", "constructor", "caller", "callee", "arguments"}
METHODS = {
    "toUpperCase",
    "toLowerCase",
    "trim",
    "includes",
    "startsWith",
    "endsWith",
    "join",
}
BINARY = {
    "+",
    "-",
    "*",
    "/",
    "%",
    "**",
    "===",
    "!==",
    "==",
    "!=",
    "<",
    ">",
    "<=",
    ">=",
    "&&",
    "||",
    "??",
}


def compile_expression(source):
    if len(source) > 4096:
        raise ValueError("SSR expression exceeds its size limit")
    lexer = ExpressionLexer(source)
    parser = ExpressionParser()
    node = parser.parse(lexer.tokenize())
    if lexer.errors or parser.errors or node is None:
        raise ValueError("; ".join(lexer.errors + parser.errors) or "Empty expression")

    budget = [512]

    def encode(value):
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError("SSR expression exceeds its node limit")
        if isinstance(value, ExpressionNode):
            kind = type(value).__name__
            if kind == "AssignmentNode":
                raise ValueError("Assignments are browser-only")
            if kind == "BinaryNode" and value.operator not in BINARY:
                raise ValueError(f"Unsupported SSR operator: {value.operator}")
            if kind == "UnaryNode" and value.operator not in {"!", "+", "-", "typeof"}:
                raise ValueError(f"Unsupported SSR unary operator: {value.operator}")
            if kind == "CallNode" and (
                type(value.callee).__name__ != "MemberNode"
                or value.callee.computed
                or value.callee.property not in METHODS
            ):
                raise ValueError(
                    "SSR calls support only documented string/array methods"
                )
            if kind == "CallNode":
                maximum = (
                    0
                    if value.callee.property in {"toUpperCase", "toLowerCase", "trim"}
                    else 1
                )
                if len(value.arguments) > maximum or value.callee.optional:
                    raise ValueError(
                        "SSR methods accept only documented arguments and nonoptional receivers"
                    )
            if kind == "MemberNode" and not value.optional:
                owner = value.object
                while type(owner).__name__ == "MemberNode":
                    if owner.optional:
                        raise ValueError(
                            "Mixed optional chains are not supported in SSR; use explicit conditionals"
                        )
                    owner = owner.object
            if (
                kind == "MemberNode"
                and not value.computed
                and value.property in BLOCKED
            ):
                raise ValueError("Unsafe property access")
            return {
                "kind": kind,
                **{
                    field.name: encode(getattr(value, field.name))
                    for field in fields(value)
                    if field.name not in {"line", "column"}
                },
            }
        if isinstance(value, (list, tuple)):
            return [encode(item) for item in value]
        return value

    return encode(node)


def truthy(value):
    if value is UNDEFINED or value is None or value is False:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0 and not math.isnan(value)
    return value != "" if isinstance(value, str) else True


def string(value):
    if value is UNDEFINED:
        return "undefined"
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, list):
        return ",".join(
            "" if item is None or item is UNDEFINED else string(item) for item in value
        )
    if isinstance(value, dict):
        return "[object Object]"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        if value == 0:
            return "0"
        if 1e-6 <= abs(value) < 1e21:
            return (
                format(Decimal(str(value)), "f").rstrip("0").rstrip(".")
                if "." in format(Decimal(str(value)), "f")
                else format(Decimal(str(value)), "f")
            )
        mantissa, exponent = str(value).lower().split("e")
        return (
            mantissa.removesuffix(".0")
            + "e"
            + ("+" if int(exponent) >= 0 else "-")
            + str(abs(int(exponent)))
        )
    return str(value)


def number(value):
    if value is UNDEFINED:
        return float("nan")
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(string(value).strip() or "0")
    except ValueError:
        return float("nan")


def primitive(value):
    return string(value) if isinstance(value, (list, dict)) else value


def strict_equal(left, right):
    if isinstance(left, (dict, list)) or isinstance(right, (dict, list)):
        return left is right
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def loose_equal(left, right):
    if (left is None or left is UNDEFINED) and (right is None or right is UNDEFINED):
        return True
    if strict_equal(left, right):
        return True
    if isinstance(left, bool):
        return loose_equal(number(left), right)
    if isinstance(right, bool):
        return loose_equal(left, number(right))
    if isinstance(left, (list, dict)) and not isinstance(right, (list, dict)):
        return loose_equal(primitive(left), right)
    if isinstance(right, (list, dict)) and not isinstance(left, (list, dict)):
        return loose_equal(left, primitive(right))
    if (
        isinstance(left, (int, float))
        and isinstance(right, str)
        or isinstance(right, (int, float))
        and isinstance(left, str)
    ):
        return number(left) == number(right)
    return False


def property_value(owner, key, optional=False):
    key = string(key)
    if key in BLOCKED:
        raise ValueError("Unsafe property access")
    if owner is None or owner is UNDEFINED:
        if optional:
            return UNDEFINED
        raise ValueError(f"Cannot read property {key!r} of {string(owner)}")
    if isinstance(owner, dict):
        return owner.get(key, UNDEFINED)
    if isinstance(owner, (str, list)):
        if key == "length":
            return (
                len(owner.encode("utf-16-le")) // 2
                if isinstance(owner, str)
                else len(owner)
            )
        if key.isdigit() and (key == "0" or not key.startswith("0")):
            index = int(key)
            if isinstance(owner, str):
                units = owner.encode("utf-16-le", errors="surrogatepass")
                return (
                    units[index * 2 : index * 2 + 2].decode(
                        "utf-16-le", errors="surrogatepass"
                    )
                    if index * 2 < len(units)
                    else UNDEFINED
                )
            return owner[index] if index < len(owner) else UNDEFINED
    return UNDEFINED


def evaluate(node, scope):
    kind = node["kind"]
    if kind == "IdentifierNode":
        name = node["name"]
        if name == "undefined":
            return UNDEFINED
        if name not in scope:
            raise ValueError(f"Missing SSR public value: {name}")
        return scope[name]
    if kind == "LiteralNode":
        return node["value"]
    if kind == "ArrayNode":
        return [evaluate(item, scope) for item in node["elements"]]
    if kind == "ObjectNode":
        result = {}
        for key, value in node["properties"]:
            if key in BLOCKED:
                raise ValueError("Unsafe object key")
            result[key] = evaluate(value, scope)
        return result
    if kind == "MemberNode":
        key = (
            evaluate(node["property"], scope)
            if isinstance(node["property"], dict)
            else node["property"]
        )
        return property_value(
            evaluate(node["object"], scope), key, node.get("optional", False)
        )
    if kind == "TernaryNode":
        return evaluate(
            node["then_expr"]
            if truthy(evaluate(node["condition"], scope))
            else node["else_expr"],
            scope,
        )
    if kind == "UnaryNode":
        op = node["operator"]
        if (
            op == "typeof"
            and node["operand"]["kind"] == "IdentifierNode"
            and node["operand"]["name"] not in scope
        ):
            return "undefined"
        value = evaluate(node["operand"], scope)
        if op == "!":
            return not truthy(value)
        if op == "+":
            return number(value)
        if op == "-":
            return -number(value)
        if op == "typeof":
            return (
                "undefined"
                if value is UNDEFINED
                else "boolean"
                if isinstance(value, bool)
                else "number"
                if isinstance(value, (int, float))
                else "string"
                if isinstance(value, str)
                else "object"
            )
    if kind == "CallNode":
        callee = node["callee"]
        owner = evaluate(callee["object"], scope)
        method = callee["property"]
        args = [evaluate(item, scope) for item in node["arguments"]]
        if method == "join" and isinstance(owner, list):
            return string(args[0] if args else ",").join(
                "" if item is None else string(item) for item in owner
            )
        if method == "includes" and isinstance(owner, list):
            return any(
                strict_equal(item, args[0] if args else UNDEFINED)
                or (
                    isinstance(item, float)
                    and isinstance(args[0] if args else UNDEFINED, float)
                    and math.isnan(item)
                    and math.isnan(args[0])
                )
                for item in owner
            )
        if isinstance(owner, str):
            functions = {
                "toUpperCase": owner.upper,
                "toLowerCase": owner.lower,
                "trim": owner.strip,
                "includes": lambda value: string(value) in owner,
                "startsWith": lambda value: owner.startswith(string(value)),
                "endsWith": lambda value: owner.endswith(string(value)),
            }
            if method in functions:
                return functions[method](
                    *(
                        args
                        or (
                            [UNDEFINED]
                            if method in {"includes", "startsWith", "endsWith"}
                            else []
                        )
                    )
                )
        raise ValueError(f"Unsupported SSR method receiver: {method}")
    if kind == "BinaryNode":
        left = evaluate(node["left"], scope)
        op = node["operator"]
        if op == "&&":
            return evaluate(node["right"], scope) if truthy(left) else left
        if op == "||":
            return left if truthy(left) else evaluate(node["right"], scope)
        if op == "??":
            return (
                evaluate(node["right"], scope)
                if left is None or left is UNDEFINED
                else left
            )
        right = evaluate(node["right"], scope)
        if op in {"===", "!=="}:
            return strict_equal(left, right) != (op == "!==")
        if op in {"==", "!="}:
            return loose_equal(left, right) != (op == "!=")
        left, right = primitive(left), primitive(right)
        if op == "+" and (isinstance(left, str) or isinstance(right, str)):
            return string(left) + string(right)
        if op in {"<", ">", "<=", ">="}:
            if not (isinstance(left, str) and isinstance(right, str)):
                left, right = number(left), number(right)
            return {
                "<": lambda: left < right,
                ">": lambda: left > right,
                "<=": lambda: left <= right,
                ">=": lambda: left >= right,
            }[op]()
        left, right = number(left), number(right)
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return (
                left / right
                if right
                else float("nan")
                if not left
                else math.copysign(float("inf"), left * math.copysign(1, right))
            )
        if op == "%":
            return (
                math.fmod(left, right)
                if right and math.isfinite(left)
                else float("nan")
            )
        if op == "**":
            if abs(right) > 1024:
                raise ValueError("SSR exponent limit exceeded")
            try:
                value = float(left) ** float(right)
                return float("nan") if isinstance(value, complex) else value
            except OverflowError:
                return math.copysign(float("inf"), left if right % 2 else 1)
            except ZeroDivisionError:
                return float("inf")
    raise ValueError(f"Unsupported SSR expression: {kind}")
