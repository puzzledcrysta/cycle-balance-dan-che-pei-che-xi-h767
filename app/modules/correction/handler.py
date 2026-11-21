from fastapi import APIRouter
from app.inputs import Correction
from .service import lineage, register

router = APIRouter()


@router.post('/api/runs/{run_id}/corrections')
def create(run_id: str, correction: Correction):
    return register(run_id, correction.raw(), correction.ledger())


@router.get('/api/runs/{run_id}/corrections')
def related(run_id: str):
    return lineage(run_id)
