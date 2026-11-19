from .muscriptor import MuscriptorEngine
from .basicpitch import BasicPitchEngine

_ENGINES: dict[str, object] = {
    "muscriptor": MuscriptorEngine(),
    "basic-pitch": BasicPitchEngine(),
}


def get_engine(name: str):
    eng = _ENGINES.get(name)
    if eng is None or not eng.is_available():
        raise RuntimeError(f"后端 '{name}' 不可用, 请先安装对应依赖")
    return eng


def available_backends() -> list[dict]:
    return [{"name": k, "desc": type(v).__doc__.splitlines()[0]
             if v.__doc__ else "", "available": v.is_available()}
            for k, v in _ENGINES.items()]
