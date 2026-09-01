from fastapi import APIRouter, HTTPException

from app.services.mission_packs import MISSION_PACKS, get_mission_pack


router = APIRouter(prefix="/mission-packs", tags=["mission-packs"])


@router.get("")
def list_mission_packs():
    return {
        "mission_packs": [
            {
                "id": pack_id,
                "name": pack["name"],
                "domains": pack["domains"],
                "description": pack["description"],
                "weights": pack["weights"],
            }
            for pack_id, pack in MISSION_PACKS.items()
        ]
    }


@router.get("/{pack_id}")
def read_mission_pack(pack_id: str):
    if pack_id not in MISSION_PACKS:
        raise HTTPException(status_code=404, detail="Mission pack not found")
    pack = get_mission_pack(pack_id)
    return {
        "id": pack_id,
        "name": pack["name"],
        "domains": pack["domains"],
        "description": pack["description"],
        "weights": pack["weights"],
        "default_options": pack["default_options"],
    }
