from fastapi import APIRouter, Depends

from app.auth import verify_token

router = APIRouter(dependencies=[Depends(verify_token)])


@router.post("/choose")
async def choose() -> dict:
    """Full 'choose for me': top candidate + resources + style."""
    # TODO: implement — pick top candidate from current run,
    #        retrieve resources, run styling pass, publish
    raise NotImplementedError
