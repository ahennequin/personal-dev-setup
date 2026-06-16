import hashlib
import hmac

from fastapi import HTTPException, Request

from config.settings import settings


async def verify_github_signature(request: Request) -> bytes:
    """
    Verify the GitHub webhook HMAC signature.
    Returns the raw body on success, raises 401 on failure.
    """
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    body = await request.body()

    expected = "sha256=" + hmac.new(
        key=settings.github_webhook_secret.encode(),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    return body
