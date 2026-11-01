from dataclasses import dataclass, field


@dataclass
class ModuleMeta:
    name: str
    author: str = ""
    description: str = ""
    version: str = "1.0.0"
    default_enabled: bool = True
    tags: tuple = ()
    requires: tuple = ()
    config_schema: dict = field(default_factory=dict)
    readme: str = ""