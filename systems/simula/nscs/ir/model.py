from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TypeDecl(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    fqname: str
    kind: str  # class | dataclass | alias | enum
    fields: dict[str, str] = Field(default_factory=dict)


class FuncDecl(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    fqname: str  # file::Class?::func
    params: dict[str, str] = Field(default_factory=dict)
    returns: str = "None"
    contracts: dict[str, str] = Field(default_factory=dict)  # pre/post expr


class ModuleIR(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    path: str
    types: list[TypeDecl] = Field(default_factory=list)
    funcs: list[FuncDecl] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)


class SIMIR(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    modules: dict[str, ModuleIR] = Field(default_factory=dict)

    def ensure_module(self, path: str) -> ModuleIR:
        if path not in self.modules:
            self.modules[path] = ModuleIR(path=path)
        return self.modules[path]
