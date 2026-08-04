import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Liveness check, plus enough build detail to tell what is actually running.

    `fly deploy` is a manual step, so "is this fix live yet?" has repeatedly
    been unanswerable from outside the machine. GIT_SHA is baked in at build
    time (see Dockerfile); the Fly-provided values still identify the image if
    a deploy skipped the build arg.
    """
    return {
        "status": "ok",
        "gitSha": os.getenv("GIT_SHA", "unknown"),
        "flyImageRef": os.getenv("FLY_IMAGE_REF", "unknown"),
        "flyMachineVersion": os.getenv("FLY_MACHINE_VERSION", "unknown"),
    }
