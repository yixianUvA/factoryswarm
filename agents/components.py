from __future__ import annotations

from core.cerebras_client import CerebrasClient
from core.schemas import SpecialistReport

from agents.common import run_specialist


AGENT_NAME = "Component and Layout Inspector"


async def run(
    client: CerebrasClient,
    reference_data_uri: str,
    inspection_data_uri: str,
    asset_type: str | None = None,
    inspection_stage: str | None = None,
    reported_symptom: str | None = None,
) -> SpecialistReport:
    return await run_specialist(
        client=client,
        agent_name=AGENT_NAME,
        prompt_name="components",
        reference_data_uri=reference_data_uri,
        inspection_data_uri=inspection_data_uri,
        asset_type=asset_type,
        inspection_stage=inspection_stage,
        reported_symptom=reported_symptom,
    )
