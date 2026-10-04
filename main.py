import logging
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from config import BREVO_API_KEY, BREVO_SENDER_EMAIL
from chatbot_engine import process_incoming_message
from waha_client import send_waha_message
from scheduler import start_scheduler, send_morning_appointment_reminders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start APScheduler for morning reminders
    start_scheduler()
    logger.info("🚀 Back4App Dental WhatsApp Chatbot Service Online!")
    yield
    # Shutdown logic if any
    logger.info("🛑 Back4App Chatbot Service Shutting Down...")

app = FastAPI(
    title="Dental Clinic WhatsApp Chatbot (Back4App Engine)",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
@app.get("/health")
async def health_check():
    """Liveness probe for Back4App hosting platform."""
    return {
        "status": "online",
        "service": "Dental Care Clinic WhatsApp Chatbot",
        "version": "1.0.0"
    }

@app.post("/webhook")
@app.post("/api/whatsapp/webhook")
async def waha_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    WAHA Webhook Listener:
    Receives incoming WhatsApp messages forwarded by WAHA GOWS engine on Render.
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"status": "invalid_json"}, status_code=400)

    # Extract payload data structure matching WAHA spec
    msg_data = payload.get("payload") or payload.get("data") or payload
    body_text = msg_data.get("body") or msg_data.get("text") or ""
    from_chat_id = msg_data.get("from") or msg_data.get("chatId") or ""

    # Ignore messages sent by bot itself
    from_me = msg_data.get("fromMe", False)
    if from_me:
        return {"status": "ignored_self"}

    if not body_text or not from_chat_id:
        return {"status": "no_content"}

    # Process message in background task
    background_tasks.add_task(process_incoming_message, from_chat_id, body_text)

    return {"status": "received", "chatId": from_chat_id}

@app.post("/trigger-reminders")
async def trigger_reminders_manual():
    """Endpoint to trigger today's morning appointment reminders manually or via cron."""
    result = await send_morning_appointment_reminders()
    return {"status": "success", "result": result}

@app.post("/notify-reschedule")
async def notify_reschedule(request: Request):
    """
    Endpoint called when doctor or admin reschedules an appointment:
    Sends WhatsApp message via WAHA AND Email notification via Brevo/Resend.
    """
    try:
        body = await request.json()
        patient_name = body.get("patientName", "Valued Patient")
        patient_phone = body.get("patientPhone", "")
        patient_email = body.get("patientEmail", "")
        doctor_name = body.get("doctorName", "Doctor")
        branch_name = body.get("branchName", "Dental Clinic")
        old_date = body.get("oldDate", "N/A")
        new_date = body.get("newDate", "")
        new_time = body.get("newTime", "")

        results = {"whatsapp": "skipped", "email": "skipped"}

        # 1. WhatsApp Reschedule Notification via WAHA
        if patient_phone:
            wa_text = (
                f"🔔 *APPOINTMENT RESCHEDULED NOTICE* 🦷\n"
                f"─────────────────────────────\n"
                f"Dear *{patient_name}*,\n\n"
                f"Your appointment with *{doctor_name}* at *{branch_name}* has been rescheduled:\n\n"
                f"❌ *Previous Date:* {old_date}\n"
                f"✅ *New Date:* {new_date}\n"
                f"⏰ *New Time Slot:* {new_time}\n"
                f"─────────────────────────────\n"
                f"📍 If this slot does not work, please reply *@appointment* or call +91 8418878491."
            )
            wa_res = await send_waha_message(patient_phone, wa_text)
            results["whatsapp"] = "sent" if wa_res.get("success") else wa_res.get("error", "failed")

        # 2. Email Reschedule Notification via Brevo API
        if patient_email and BREVO_API_KEY:
            try:
                email_payload = {
                    "sender": {"email": BREVO_SENDER_EMAIL, "name": "Dental Care Clinic"},
                    "to": [{"email": patient_email, "name": patient_name}],
                    "subject": "🔔 Your Dental Appointment Has Been Rescheduled",
                    "htmlContent": f"""
                        <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                            <h2 style="color: #0f766e;">🦷 Dental Care Clinic - Reschedule Notice</h2>
                            <p>Dear <strong>{patient_name}</strong>,</p>
                            <p>Your appointment with <strong>{doctor_name}</strong> has been rescheduled:</p>
                            <ul>
                                <li><strong>Clinic Branch:</strong> {branch_name}</li>
                                <li><strong>New Date:</strong> {new_date}</li>
                                <li><strong>New Time:</strong> {new_time}</li>
                            </ul>
                            <p>If you need to make changes, please contact us at +91 8418878491 or reply to WhatsApp desk.</p>
                        </div>
                    """
                }
                async with httpx.AsyncClient() as client:
                    email_res = await client.post(
                        "https://api.brevo.com/v3/smtp/email",
                        headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
                        json=email_payload
                    )
                    results["email"] = "sent" if email_res.status_code < 300 else f"HTTP {email_res.status_code}"
            except Exception as e:
                results["email"] = f"error ({e})"

        return {"success": True, "results": results}

    except Exception as err:
        logger.error(f"Error in notify-reschedule endpoint: {err}")
        return JSONResponse({"success": False, "error": str(err)}, status_code=500)
