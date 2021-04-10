import re
import math
import copy
from typing import List, Union, Callable
from sly.lex import Token
from .lex import ArgLexer
from .errors import *

FUNCTION_RE = re.compile(r"([a-zA-Z]*)\(([a-zA-Z,\s]*)\)\s*=\s*([a-zA-Z0-9^*/\-+() ]*)") # P(x) = expr
FUNCTIONCALL_RE = re.compile(r"([a-zA-Z]*)\((.*)\)") # P(x[, y,...])

MAX_ALLOWABLE_NUMBER = 99999999

class Builtins:
    def __init__(self):
        _num = ["num"]
        _num2 = ["num", "num2"]
        def _unwrap(func: Callable):
            def call(_, **kwargs):
                return func(*kwargs.values())
            return call
        self.builtins = {
            "rad": BuiltinFunction("rad", _num, _unwrap(math.radians)),
            "sin": BuiltinFunction("sin", _num, _unwrap(math.sin)),
            "cos": BuiltinFunction("cos", _num, _unwrap(math.cos)),
            "tan": BuiltinFunction("tan", _num, _unwrap(math.tan)),
            "asin": BuiltinFunction("asin", _num2, _unwrap(lambda x, y: math.asin(x/y))),
            "acos": BuiltinFunction("acos", _num2, _unwrap(lambda x, y: math.acos(x/y))),
            "atan": BuiltinFunction("atan", _num2, _unwrap(lambda x, y: math.atan(x/y))),
            "log": BuiltinFunction("log", _num2, _unwrap(math.log)),
            "π": math.pi,
            "pi": math.pi,
            "E": math.e,
        }

class Parser:
    def __init__(self, user_input, lex):
        self.input = user_input
        self.lex = lex
        self.state = BUILTINS.builtins.copy()
        self.tokens = None # type: List[Token]

    def parse(self, tokens: List[Token]):
        self.tokens = tokens
        expr = self.traverse_tokens(allow_functions=True)
        return expr

    def traverse_tokens(self, tokens: List[Token]=None, allow_functions=True):
        exprs = [Expression()]
        functioncalls = []
        bracket = None
        depth = 0
        tokens = tokens or self.tokens
        last_token = None
        skip = 0

        for index, token in enumerate(tokens):
            if skip:
                skip -= 1
                continue

            if token.type == "FUNCTION":
                if not allow_functions:
                    raise TokenizedUserInputError(self.input, token, "Functions are not allowed here")

                groups = FUNCTION_RE.match(token.value)
                name, args, value = groups.groups()
                f = Function(name, args, self.traverse_tokens(
                    list(self.lex.tokenize(
                        value, #lineno=token.lineno, index=token.index+offset
                    )), allow_functions=False)[0].chunks
                )

                self.state[f.name] = f
                last_token = f
                if tokens[index+1].value == "\n":
                    skip += 1

                continue

            elif token.type == "(":
                depth += 1
                if depth == 1:
                    last_token = token
                    bracket = Bracket(token)
                    continue

            elif token.type == ")":
                depth -= 1
                if depth == 0:
                    last_token = token
                    exprs[-1].add_chunk(bracket)
                    bracket = None
                    continue

                if depth < 0:
                    raise TokenizedUserInputError(self.input, token, "Unexpected closing bracket")

            elif token.type == "OPERATOR":
                if not last_token and token.value != "-":
                    raise TokenizedUserInputError(self.input, token, "Unexpected operator")

                if token.value == "-" and last_token and last_token.value == "-":
                    _token = copy.copy(token)
                    _token.value = "+"
                    if bracket:
                        bracket.tokens.pop()
                        bracket.tokens.append(Operator(_token))
                    else:
                        exprs[-1].chunks.pop()
                        exprs[-1].chunks.append(Operator(_token))

                    last_token = token
                    continue

                elif last_token and last_token.value == token.value:
                    raise TokenizedUserInputError(self.input, token, f"Unexpected '{token.value}'")

                last_token = token
                token = Operator(token)

            elif token.type == "FUNCTION_CALL":
                toks = FUNCTIONCALL_RE.match(token.value)
                name, args = toks.groups()
                args = self.parse_args(token, token.value.find("("), args)
                f = FunctionCall(token, name, args)
                last_token = f
                exprs[-1].add_chunk(f)
                functioncalls.append(f)
                continue

            elif token.value == "\n":
                exprs.append(Expression())

            else:
                last_token = token

            if bracket:
                bracket.tokens.append(token)
            else:
                exprs[-1].add_chunk(token)

        for call in functioncalls:
            call.validate(self)

        if allow_functions:
            for x in self.state.values():
                try:
                    x.validate(self)
                except AttributeError:
                    pass

        return exprs

    def parse_args(self, _, __, args: str):
        tokens = list(ArgLexer().tokenize(args))
        v = self.traverse_tokens(tokens, allow_functions=False)[0].chunks
        args = [x for x in v if (isinstance(x, Token) and x.type != ",") or not isinstance(x, Token)]
        return args

    def get_var_with_state(self, var: Token, namespace: dict=None):
        if namespace and var.value in namespace:
            return namespace[var.value]

        if var.value in self.state.keys():
            v = self.state[var.value]
            if isinstance(v, (int, float)):
                return v

        raise TokenizedUserInputError(self.input, var, f"Variable '{var.value}' does not exist")

    def get_var(self, var: str, namespace: dict=None):
        if namespace and var in namespace:
            return namespace[var]
        elif var in self.state:
            return self.state[var]

        raise UserInputError(f"Variable '{var}' does not exist")

    def _quick_call(self, seq: List[Union["Bracket", Token, "Operator", "FunctionCall"]], namespace: dict):
        v = seq[-1]
        if isinstance(v, (int, float)):
            return v
        elif isinstance(v, str):
            return self.get_var(v, namespace)
        elif isinstance(v, Token):
            return self.get_var_with_state(v, namespace)
        elif isinstance(v, FunctionCall):
            return v.execute(self, namespace)

        raise RuntimeError(f"unable to determine types. {v!r}")

    def do_math(self, seq: List[Union["Bracket", Token, "Operator", "FunctionCall"]], namespace: dict):
        print("----START-----")
        print(namespace, seq)
        if len(seq) < 3:
            print("----QUICKCALL-END----")
            return self._quick_call(seq, namespace)

        ops = _ops = []
        # loop one, solve brackets/function calls, abstract down to numbers
        for i in seq:
            if isinstance(i, Bracket):
                ops.append(self.do_math(i.tokens, namespace))
            elif isinstance(i, FunctionCall):
                ops.append(i.execute(self, namespace))
            elif isinstance(i, Token):
                ops.append(i.value)
            else:
                ops.append(i)

        # loop through for each operator to apply bedmas
        print(ops)
        for operator in ("^", "/", "*", "+", "-"):
            it = iter(enumerate(ops))
            new = []
            for i, left in it:
                if isinstance(left, Operator):
                    if left.op == operator:
                        op = left
                        left = new.pop()
                    else:
                        print(i, left, new, ops, _ops)
                        new.append(left)
                        continue
                else:
                    try:
                        _, op = next(it)
                    except StopIteration:
                        if isinstance(left, str):  # variable
                            left = self.get_var(left, namespace)

                        new.append(left)
                        continue

                    assert isinstance(op, Operator), AssertionError(left, op, new, ops, _ops)
                    if op.op != operator:
                        new.append(left)
                        new.append(op)
                        continue

                _, right = next(it)
                if isinstance(right, str): #variable
                    right = self.get_var(right, namespace)

                if isinstance(left, str): #variable
                    left = self.get_var(left, namespace)

                print(left, right)
                value = op.execute(self, left, right)
                new.append(value)

            print(new, ops)
            ops = new
            if len(ops) == 1:
                break

        print(ops)
        print("----END----")
        return ops[0]


class Operator:
    __slots__ = "op", "token"
    value = None
    OPS = {
        "+": lambda l, r: l + r,
        "-": lambda l, r: l - r,
        "*": lambda l, r: l * r,
        "/": lambda l, r: l / r,
        "^": lambda l, r: math.pow(l, r),
    }
    def __init__(self, token: Token):
        self.op = token.value
        self.token = token

    def __repr__(self):
        return f"<Operator {self.op}>"

    def execute(self, parser: Parser, left: Union[int, float], right: Union[int, float]):
        if left > MAX_ALLOWABLE_NUMBER:
            raise EvaluationError(parser.tokens, self.token, left, right,
                                  "Number (left) is larger than the permissible values")
        if right > MAX_ALLOWABLE_NUMBER:
            raise EvaluationError(parser.tokens, self.token, left, right,
                                  "Number (right) is larger than the permissible values")
        return self.OPS[self.op](left, right)

class Expression:
    __slots__ = "chunks",
    value = None

    def __init__(self):
        self.chunks = [] # type: List[Union[Bracket, Token, Operator, FunctionCall]]

    def add_chunk(self, obj: Union["Bracket", Token, Operator, "FunctionCall"]):
        if self.chunks:
            if isinstance(obj, Token) and obj.type in ("NUMBER", "NAME"):
                t = Token()
                t.value = "*"
                t.index = obj.index
                t.lineno = obj.lineno
                t.type = "OPERATOR"
                if isinstance(self.chunks[-1], Token) and self.chunks[-1].type in ("NUMBER", "NAME"):
                    self.chunks.append(Operator(t))

                elif isinstance(self.chunks[-1], Bracket):
                    self.chunks.append(Operator(t))

            elif isinstance(obj, Bracket):
                if isinstance(self.chunks[-1], Token) and self.chunks[-1].type in ("NUMBER", "NAME"):
                    t = Token()
                    t.value = "*"
                    t.index = obj.start.index
                    t.lineno = obj.start.lineno
                    t.type = "OPERATOR"
                    self.chunks.append(Operator(t))

        self.chunks.append(obj)

    def execute(self, parser: Parser, namespace: dict=None):
        return parser.do_math(self.chunks, namespace)

    def __repr__(self):
        return f"<Expression {self.chunks}>"


class Bracket:
    __slots__ = "tokens", "start"
    value = None
    def __init__(self, start: Token):
        self.tokens = []
        self.start = start

    def execute(self, parser: Parser, namespace: dict=None):
        expr = parser.traverse_tokens(self.tokens, allow_functions=False)
        if len(expr) > 1:
            raise TokenizedUserInputError(parser.input, self.start, "Invalid Syntax (multi-expr)")
        expr = expr[0]

        print(expr.chunks)
        return parser.do_math(expr.chunks, namespace)

    def __repr__(self):
        return f"<Bracket {self.tokens}>"

class Function:
    __slots__ = "name", "args", "chunks"
    value = None

    def __init__(self, name: str, args: List[str], chunks: List[Union[Bracket, Token, Operator]]):
        self.name = name
        self.args = args
        self.chunks = chunks

    def validate(self, parser: Parser):
        def validate_chunk(_chunk):
            if isinstance(_chunk, Bracket):
                for c in _chunk.tokens:
                    validate_chunk(c)

            elif isinstance(_chunk, Token):
                if _chunk.type == "NAME":
                    if _chunk.value not in self.args:
                        raise TokenizedUserInputError(parser.input, _chunk, f"Unknown variable: '{_chunk.value}'")

        for chunk in self.chunks:
            validate_chunk(chunk)

    def execute(self, parser: Parser, scope: dict):
        return parser.do_math(self.chunks, scope)

    def __repr__(self):
        return f"<Function name={self.name} args={self.args} chunks={self.chunks}"

class BuiltinFunction(Function):
    def __init__(self, name: str, args: List[str], callback: Callable):
        self.name = name
        self.args = args
        self.chunks = callback

    def validate(self, parser: Parser):
        pass

    def execute(self, parser: Parser, scope: dict):
        return self.chunks(parser, **scope)

    def __repr__(self):
        return f"<BuiltinFunction name={self.name} args={self.args}>"


class FunctionCall:
    __slots__ = "_start", "name", "args"
    value = None

    def __init__(self, t: Token, name: str, tokens: List[Union[Expression, "FunctionCall", Token]]):
        self._start = t
        self.name = name
        self.args = tokens

    def validate(self, parser: Parser, scope: dict=None):
        if self.name not in parser.state:
            raise TokenizedUserInputError(parser.input, self._start, f"Function '{self.name}' not found")

        func = parser.state[self.name]
        print(self.args, func.args)
        if len(func.args) != len(self.args):
            raise TokenizedUserInputError(
                parser.input,
                self._start,
                f"{'Not enough' if len(func.args)>len(self.args) else 'Too many'} arguments passed to {self.name}"
            )

        for arg in self.args:
            if isinstance(arg, (str, int)):
                if not scope and arg not in parser.state:
                    raise TokenizedUserInputError(parser.input, self._start, f"Variable '{arg}' not found")

                elif scope and arg not in scope and arg not in parser.state:
                    raise TokenizedUserInputError(parser.input, self._start, f"Variable '{arg}' not found")

            elif isinstance(arg, FunctionCall):
                arg.validate(parser, scope)

    def execute(self, parser: Parser, scope: dict=None):
        func = parser.state[self.name] # it should already be there, we validated earlier
        if not isinstance(func, Function):
            raise ValueError("function expected. todo: this errror") # TODO

        args = {}
        for index, arg in enumerate(self.args):
            if isinstance(arg, Expression):
                args[func.args[index]] = parser.do_math(arg.chunks, scope)
            else:
                try:
                    args[func.args[index]] = arg.execute(parser, scope)
                except AttributeError:
                    if arg.type == "NAME":
                        args[func.args[index]] = parser.get_var_with_state(arg, scope)
                    else:
                        args[func.args[index]] = arg.value

        return func.execute(parser, args)

BUILTINS = Builtins()
