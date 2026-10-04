import re
import httpx
import logging
from config import WAHA_ENDPOINT, WAHA_API_KEY, WAHA_SESSION

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("waha_client")

def format_waha_chat_id(phone: str) -> str:
    """
    Formats raw phone number to standard WAHA chatId:
    - Strips all non-digit characters.
    - If 10 digits provided, prepends India country code 91.
    - Appends '@c.us' suffix.
    """
    if not phone:
        return ""
    
    digits = re.sub(r'\D', '', str(phone))
    
    if len(digits) == 10:
        digits = f"91{digits}"
        
    if not digits.endswith("@c.us"):
        return f"{digits}@c.us"
        
    return digits

async def send_waha_message(phone: str, text: str, session: str = WAHA_SESSION) -> dict:
    """
    Dispatches a WhatsApp text message via WAHA API endpoint.
    Safely handles response body text parsing to avoid stream double-read errors.
    """
    formatted_chat_id = format_waha_chat_id(phone)
    if not formatted_chat_id:
        logger.error("Invalid phone number provided to send_waha_message.")
        return {"success": False, "error": "Invalid recipient phone number"}

    headers = {
        "X-Api-Key": WAHA_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "chatId": formatted_chat_id,
        "text": text,
        "session": session
    }

    logger.info(f"[WAHA Dispatcher] Sending message to {formatted_chat_id} via {WAHA_ENDPOINT}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(WAHA_ENDPOINT, json=payload, headers=headers)
            status = response.status_code
            
            # Read response text once to avoid double-read error
            response_text = response.text
            res_data = {}
            if response_text:
                try:
                    res_data = response.json()
                except Exception:
                    res_data = {"rawText": response_text}

            if status >= 400:
                err_msg = res_data.get("message") or res_data.get("error") or f"WAHA HTTP Error {status}"
                logger.error(f"[WAHA Error {status}]: {err_msg}")
                return {"success": False, "status": status, "error": err_msg, "data": res_data}

            logger.info(f"[WAHA Success] Message dispatched to {formatted_chat_id}")
            return {"success": True, "status": status, "data": res_data, "chatId": formatted_chat_id}

        except Exception as err:
            logger.error(f"[WAHA Exception]: {err}")
            return {"success": False, "error": str(err)}
