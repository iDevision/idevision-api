from typing import List
from sly.lex import Token

__all__ = (
    "UserInputError",
    "TokenizedUserInputError",
    "EvaluationError"
)

class UserInputError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    def __str__(self):
        return self.message


class TokenizedUserInputError(UserInputError):
    def __init__(self, user_input: str, token: Token, message: str):
        self.input = user_input
        self.token = token
        self.message = message
        super().__init__(message)

    def make_traceback(self):
        inp = ""
        ind = 0
        _offset = 0
        ln = 1
        for x in self.input:
            ind += 1
            if x == "\n":
                ln += 1
                if ln == self.token.lineno:
                    _offset = ind

                continue

            if ln == self.token.lineno:
                inp += x

        offset = self.token.index - _offset
        x = str(self.token.value)
        relevant = inp[max(offset-5, 0):max(offset+5, len(x))]
        arrow = f"{' '*min(offset, 4)}{'^'*len(x)}"
        return f">{relevant}\n>{arrow}\n>{'~'*len(arrow)}\n>{self.message}"

    def __str__(self):
        return self.make_traceback()


class EvaluationError(UserInputError):
    def __init__(self, nearby: List[Token], token: Token, left: int, right: int, message: str):
        self.left, self.right = left, right
        self.input = nearby
        self.token = token
        self.message = message
        super().__init__(message)

    def make_traceback(self):
        inp = self.input
        index = self.input.index(self.token)
        close_tokens = [str(x.value) for x in inp[index-1:index+2]]
        print(close_tokens)

        a = ""
        if index - 2 < 0:
            top = ""
        else:
            top = a = str(inp[index-2].value)

        top += " >>" + " ".join(close_tokens) + "<< "
        b = ""
        if index + 2 < len(inp):
            b = str(inp[index+3].value)
            top += b

        lowtok_under = str(self.left) + (" "*(len(str(inp[index-1].value))-len(str(self.left))))
        mid = f"{' '*len(a)}   {lowtok_under}   {self.right}"
        formatted = f">{top}\n>{mid}\n{'~'*len(mid)}\n{self.message}"
        return formatted

    def __str__(self):
        return self.make_traceback()
