from typing import Annotated, Any

from pydantic import PlainSerializer, WithJsonSchema

from systems.nova.proof.pcc import ProofVM


def _vm_serialize(v: Any) -> dict[str, Any]:
    if hasattr(v, "to_dict"):
        return v.to_dict()
    if hasattr(v, "dict"):
        return v.dict()
    return {"repr": repr(v)}


ProofVMField = Annotated[
    ProofVM,
    PlainSerializer(_vm_serialize, return_type=dict),
    WithJsonSchema({"type": "object", "title": "ProofVM"}),
]
