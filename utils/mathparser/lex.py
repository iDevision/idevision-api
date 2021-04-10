from sly.lex import Lexer, Token

from .errors import TokenizedUserInputError

__all__ = "MathLexer", "ArgLexer"

def __token_eq(self, other):
    return self.index == other.index

Token.__eq__ = __token_eq


class MathLexer(Lexer):
    tokens = { FUNCTION, FUNCTION_CALL, NAME, NUMBER, NEWLINE }
    ignore = ' \t'
    literals = { '=', '(', ')' }

    # Tokens
    FUNCTION = r'([a-zA-Z]+)\(([a-zA-Z,\s]*)\)\s*=\s*([a-zA-Z0-9^*/\-+\(\) \t]*)'
    FUNCTION_CALL = r'([a-zA-Z]+)\((.*)\)'
    NAME = r'[a-zA-Z_][a-zA-Z0-9_]*'

    @_(r'[+\-*/^]')
    def OPERATOR(self, t: Token):
        return t

    @_(r'(\d|\.)+')
    def NUMBER(self, t: Token):
        if len(t.value) > 8:
            raise TokenizedUserInputError(self.text, t, "Number is too large or too precise")

        try:
            t.value = float(t.value)
        except:
            raise TokenizedUserInputError(self.text, t, f"Invalid number: '{t.value}'")
        return t

    @_(r'\n+')
    def NEWLINE(self, t):
        self.lineno += t.value.count('\n')
        return t

    def error(self, t):
        raise TokenizedUserInputError(self.text, t, f"Invalid syntax: {t.value}")

class ArgLexer(Lexer):
    #def __init__(self, source: str):
    #    self.source = source
    #    super(ArgLexer, self).__init__()

    tokens = { FUNCTION, FUNCTION_CALL, NAME, NUMBER}
    ignore = ' \t'
    literals = {'(', ')', ','}

    @_(r"([a-zA-Z]+)\(([a-zA-Z,\s]*)\)\s*=\s*([a-zA-Z0-9^*/\-+\(\) \t]*)")
    def FUNCTION(self, t: Token):
        raise TokenizedUserInputError(self.text, t, "Functions are not allowed here")

    # Tokens
    FUNCTION_CALL = r'([a-zA-Z]+)\((.*)\)'
    NAME = r'[a-zA-Z_][a-zA-Z0-9_]*'

    @_(r'[+\-*/^]')
    def OPERATOR(self, t: Token):
        return t

    @_(r'(\d|\.)+')
    def NUMBER(self, t: Token):
        if len(t.value) > 8:
            raise TokenizedUserInputError(self.text, t, "Number is too large or too precise")

        try:
            t.value = float(t.value)
        except:
            raise TokenizedUserInputError(self.text, t, f"Invalid number: '{t.value}'")
        return t

    @_(r'\n+')
    def newline(self, t):
        self.lineno += t.value.count('\n')
        return t

    def error(self, t):
        raise TokenizedUserInputError(self.text, t, f"Invalid syntax: {t.value}")