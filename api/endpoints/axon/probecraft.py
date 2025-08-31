# api/endpoints/axon/probecraft.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from systems.axon.dependencies import (
    get_driver_registry,
    get_lifecycle_manager,
    get_scorecard_manager,
)
from systems.axon.mesh.lifecycle import DriverLifecycleManager, DriverState, DriverStatus
from systems.axon.mesh.registry import DriverRegistry
from systems.axon.mesh.scorecard import DriverScorecard, ScorecardManager

probecraft_router = APIRouter()


class SynthesisRequest(BaseModel):
    driver_name: str = Field(
        ...,
        description="A unique name for the new driver, e.g., 'weather_api_driver'.",
    )
    api_spec_url: str = Field(
        ...,
        description="URL to the OpenAPI/Swagger JSON specification for the target API.",
    )


class StatusUpdateRequest(BaseModel):
    new_status: DriverStatus


def _driver_name_to_class_name(driver_name: str) -> str:
    name_with_spaces = driver_name.replace("_", " ").replace("-", " ")
    return "".join(word.capitalize() for word in name_with_spaces.split())


@probecraft_router.post("/synthesize", response_model=DriverState)
async def request_driver_synthesis(
    request: SynthesisRequest,
    manager: DriverLifecycleManager = Depends(get_lifecycle_manager),
):
    try:
        return await manager.request_synthesis(
            driver_name=request.driver_name,
            api_spec_url=request.api_spec_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate synthesis: {e}")


@probecraft_router.post("/drivers/{driver_name}/status", response_model=DriverState)
async def update_driver_status(
    driver_name: str,
    request: StatusUpdateRequest,
    manager: DriverLifecycleManager = Depends(get_lifecycle_manager),
    registry: DriverRegistry = Depends(get_driver_registry),
):
    try:
        updated_state = manager.update_driver_status(driver_name, request.new_status)
        registry.update_driver_status(driver_name, request.new_status)

        # Load driver code only when the Enum is one of the active states
        if request.new_status in {DriverStatus.testing, DriverStatus.shadow, DriverStatus.live}:
            if updated_state.artifact_path:
# highlight-start
                # Prioritize the class name from the spec, fall back to derivation
                class_name = updated_state.spec.class_name or _driver_name_to_class_name(driver_name)
# highlight-end
                registry.load_and_register_driver(
                    driver_name=driver_name,
                    module_path=updated_state.artifact_path,
                    class_name=class_name,
                )
            else:
                # Inconsistent state; surface loudly while keeping server healthy
                print(
                    f"CRITICAL: Driver '{driver_name}' promoted but has no artifact path. Cannot load.",
                )

        return updated_state
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update status: {e}")


@probecraft_router.get("/drivers", response_model=list[DriverState])
async def list_driver_states(manager: DriverLifecycleManager = Depends(get_lifecycle_manager)):
    return manager.get_all_states()


@probecraft_router.get("/scorecards", response_model=list[DriverScorecard])
async def get_all_scorecards(scorecard_manager: ScorecardManager = Depends(get_scorecard_manager)):
    return scorecard_manager.get_all_scorecards()