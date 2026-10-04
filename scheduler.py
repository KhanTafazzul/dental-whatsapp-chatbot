import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import get_today_appointments
from waha_client import send_waha_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler()

async def send_morning_appointment_reminders():
    """
    Automated Morning Reminder Job:
    100% Dynamic: Queries today's appointments from Supabase and sends WhatsApp reminders.
    """
    logger.info("[Scheduler] Executing daily morning appointment reminders job...")
    
    today_appts = get_today_appointments()
    if not today_appts:
        logger.info("[Scheduler] No appointments scheduled for today.")
        return {"count": 0, "sent": []}

    sent_list = []
    
    for appt in today_appts:
        patient = appt.get("patients") or {}
        doctor = appt.get("doctors") or {}
        branch = appt.get("branches") or {}
        
        patient_name = patient.get("name", "Valued Patient")
        patient_phone = patient.get("mobile")
        doctor_name = doctor.get("name", "Our Dental Specialist")
        branch_name = branch.get("name", "Dental Care Clinic")
        branch_address = branch.get("address") or "Main Clinic"
        time_slot = appt.get("appointment_time", "Scheduled Time")
        token_id = str(appt.get("id", ""))[:6].upper()

        if not patient_phone:
            logger.warning(f"[Scheduler] Skipping appointment {appt.get('id')}: No phone number.")
            continue

        reminder_msg = (
            f"🌅 *TODAY IS YOUR DENTAL APPOINTMENT!* 🦷\n"
            f"─────────────────────────────\n"
            f"Dear *{patient_name}*,\n\n"
            f"This is a gentle reminder for your scheduled dental visit today:\n\n"
            f"👨‍⚕️ *Doctor:* {doctor_name}\n"
            f"🏢 *Branch:* {branch_name}\n"
            f"⏰ *Time Slot:* {time_slot}\n"
            f"🎟️ *Booking ID:* #{token_id}\n"
            f"─────────────────────────────\n"
            f"📍 *Location:* {branch_address}\n"
            f"📌 Please arrive 10-15 minutes prior to your time slot.\n"
            f"📞 Need to update? Reply *@appointment* or call +91 8418878491."
        )

        res = await send_waha_message(patient_phone, reminder_msg)
        if res.get("success"):
            sent_list.append(patient_name)
            logger.info(f"[Scheduler Success] Reminder sent to {patient_name} ({patient_phone})")

    return {"count": len(sent_list), "sent": sent_list}

def start_scheduler():
    """Starts the APScheduler background worker."""
    # Run daily at 08:00 AM
    scheduler.add_job(send_morning_appointment_reminders, 'cron', hour=8, minute=0, id='morning_reminders')
    scheduler.start()
    logger.info("[Scheduler Worker Started] Daily morning reminders active for 08:00 AM IST.")
