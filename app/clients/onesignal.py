import httpx

from app.config import get_settings

ONESIGNAL_API = "https://onesignal.com/api/v1"


async def send_push(message: str) -> None:
    """Send a push notification to all subscribers via OneSignal."""
    s = get_settings()
    if not s.onesignal_app_id:
        return

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{ONESIGNAL_API}/notifications",
            headers={"Authorization": f"Basic {s.onesignal_api_key}"},
            json={
                "app_id": s.onesignal_app_id,
                "included_segments": ["All"],
                "contents": {"en": message},
            },
        )
