from inspect import signature

def foo(a, b: int, c, d: str = "default"):
    pass

sig = signature(foo)
print(sig)  # 输出: (a, b: int, c, d: str = "default")
print(len(sig.parameters))  # 输出: 4