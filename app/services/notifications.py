from app.clients.onesignal import send_push


async def notify_candidates_ready() -> None:
    await send_push("New candidates are ready for review")


async def notify_publish_warning() -> None:
    await send_push("Auto-publishing in 15 minutes — review now or it picks for you")


async def notify_published(question: str) -> None:
    await send_push(f"Published: {question}")


async def notify_nothing_to_publish() -> None:
    await send_push("Nothing to publish today")
