import typing as t


def stringify(v: t.Any):
    if type(v) is str:
        return f"'{str(v)}'"
    else:
        return str(v)


def stringify_array(vec: t.List[t.Any]) -> str:
    if len(vec) == 0:
        return ["[]"]
    else:
        return [stringify(a) for a in vec]


class MagicResponder:
    def __init__(self, parent_string: str) -> None:
        self.parent_string = parent_string

    def __call__(self, *args: t.Any, **kwargs: t.Any) -> "MagicResponder":
        name = f"{self.parent_string}({', '.join(stringify_array(args))})"
        return MagicResponder(name)

    def get(self, *args: t.Any, **kwargs: t.Any) -> "MagicResponder":
        name = f"{self.parent_string}.get({', '.join(stringify_array(args))})"
        return MagicResponder(name)

    def __getattr__(self, attr) -> "MagicResponder":
        name = f"{self.parent_string}.{attr}"
        return MagicResponder(name)

    def __getitem__(self, attr) -> "MagicResponder":
        name = f"{self.parent_string}[{stringify(attr)}]"
        return MagicResponder(name)

    def __str__(self):
        return f'"{self.parent_string}"'
