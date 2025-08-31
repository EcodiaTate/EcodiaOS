from fastapi import Depends, HTTPException

from systems.synk.core.switchboard.runtime import sb


def require_flag_true(key: str, *, default: bool = False):
    async def _dep():
        if not await sb.get_bool(key, default):
            raise HTTPException(status_code=403, detail=f"Feature '{key}' is disabled")
        return True

    return Depends(_dep)
