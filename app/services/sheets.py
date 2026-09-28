import logging
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_to_sheets(order: dict) -> bool:
    """Send order data to Google Sheets webhook. Returns True if successful."""
    settings = get_settings()

    if not settings.google_sheets_webhook_url:
        logger.warning("Google Sheets webhook URL not configured, skipping")
        return False

    payload = {
        "secret": settings.google_sheets_webhook_secret,
        "order": order,
    }

    try:
        # Google Apps Script runs doPost, then answers 302 -> script.googleusercontent.com with the script's output.
        # Not following it logged every order as "HTTP 302" / sheet_failed although the row had been written.
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.post(settings.google_sheets_webhook_url, json=payload)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    data = None
                if isinstance(data, dict) and (data.get("ok") is False or data.get("error")):
                    logger.error("Sheets webhook returned not-ok: %s", data)
                    return False
                logger.info("Sheets webhook OK: %s", str(data)[:120])
                return True
            logger.error("Sheets webhook HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        logger.error("Sheets webhook exception: %s", str(e))
        return False
