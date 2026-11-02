from fastapi import APIRouter, Depends
from app.core.auth_deps import verify_admin_api_key
from app.services.attack_simulator import run_simulation

router = APIRouter(prefix="/attack-simulator", tags=["attack-simulator"], dependencies=[Depends(verify_admin_api_key)])

@router.post("/run")
def run_attack_simulation():
    return run_simulation()
