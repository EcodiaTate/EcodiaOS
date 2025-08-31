from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv

from core.utils.neo.cypher_query import cypher_query

# Robust .env loading
_DOTENV = find_dotenv() or os.getenv("ENV_FILE") or "D:/config/.env"
try:
    load_dotenv(_DOTENV)
except Exception:
    pass

PROMOTE_EXPECTED = float(os.getenv("IDENTITY_PROMOTE_EXPECTED", "0.15"))
PROMOTE_CONF = float(os.getenv("IDENTITY_PROMOTE_CONF", "0.60"))
RETIRE_EXPECTED = float(os.getenv("IDENTITY_RETIRE_EXPECTED", "0.02"))


async def run():
    promote_q = """
    MATCH (f:IdentityFacet)
    WHERE coalesce(f.expected_reward,0) >= $exp
      AND coalesce(f.confidence,0)     >= $conf
      AND coalesce(f.status,'candidate') <> 'active'
    SET f.status = 'active',
        f.updated_at = datetime()
    RETURN count(f) AS promoted
    """

    retire_q = """
    MATCH (f:IdentityFacet)
    WHERE coalesce(f.expected_reward,0) < $ret
      AND coalesce(f.status,'candidate') <> 'retired'
    SET f.status = 'retired',
        f.updated_at = datetime()
    RETURN count(f) AS retired
    """

    res1 = await cypher_query(promote_q, {"exp": PROMOTE_EXPECTED, "conf": PROMOTE_CONF})
    res2 = await cypher_query(retire_q, {"ret": RETIRE_EXPECTED})
    print(
        f"[PROMOTER] promoted={res1[0]['promoted'] if res1 else 0} retired={res2[0]['retired'] if res2 else 0}",
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
