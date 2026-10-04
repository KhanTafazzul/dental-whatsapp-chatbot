import re
import logging
from datetime import date, timedelta
from database import (
    get_patients_by_phone,
    get_branches,
    get_doctors_by_branch,
    get_available_time_slots,
    create_appointment,
    get_patient_upcoming_appointments
)
from waha_client import send_waha_message
from config import REGISTER_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot_engine")

# Session State Store (Key: clean_phone, Value: dict of state + context data)
user_sessions = {}

def get_session(phone: str) -> dict:
    clean_phone = re.sub(r'\D', '', str(phone or ''))
    if clean_phone not in user_sessions:
        user_sessions[clean_phone] = {"state": "IDLE", "data": {}}
    return user_sessions[clean_phone]

def reset_session(phone: str):
    clean_phone = re.sub(r'\D', '', str(phone or ''))
    if clean_phone in user_sessions:
        user_sessions[clean_phone] = {"state": "IDLE", "data": {}}

async def process_incoming_message(from_phone: str, text_body: str) -> dict:
    """
    Main State Machine & NLP Command Router for WhatsApp Incoming Webhook.
    Case-insensitive matching for help, appointment, reports, branches, doctors, etc.
    """
    text = (text_body or "").strip()
    lower_text = text.lower()
    clean_phone = re.sub(r'\D', '', str(from_phone or ''))
    
    session = get_session(clean_phone)
    current_state = session.get("state", "IDLE")

    logger.info(f"[Chatbot Engine] From: {from_phone} | State: {current_state} | Text: '{text}'")

    # 1. Global Reset / Help Commands (Can interrupt at any state)
    if lower_text in ["help", "@help", "info", "menu", "??", "?", "patient help"]:
        reset_session(clean_phone)
        help_msg = (
            f"🦷 *DENTAL CARE CLINIC - PATIENT ASSISTANT* 🦷\n\n"
            f"Here are the commands you can send anytime:\n\n"
            f"📋 *@appointment* - Book a new dental appointment\n"
            f"📄 *@reports* - View prescriptions & report links\n"
            f"🏢 *@branches* - View clinic locations & timings\n"
            f"👨‍⚕️ *@doctors* - View active dental specialists\n"
            f"📅 *@myappointments* - Check your upcoming bookings\n\n"
            f"Reply with any command (e.g. *@appointment*) to proceed!"
        )
        await send_waha_message(from_phone, help_msg)
        return {"status": "processed", "action": "help"}

    # 2. Command Trigger: @branches
    if lower_text in ["@branches", "branches", "branch", "locations", "clinic location"]:
        reset_session(clean_phone)
        branches = get_branches()
        if branches:
            msg = "🏢 *DENTAL CARE CLINIC LOCATIONS:*\n\n"
            for idx, b in enumerate(branches, 1):
                msg += f"{idx}. *{b.get('name')}*\n"
                if b.get("working_hours"):
                    msg += f"   ⏰ Hours: {b.get('working_hours')}\n"
                msg += "\n"
            msg += "Reply *@appointment* to book at any branch!"
        else:
            msg = "🏢 *Clinic Branches:* Please visit our portal to view branch details:\nhttps://dental.flynx.site"
        await send_waha_message(from_phone, msg)
        return {"status": "processed", "action": "branches"}

    # 3. Command Trigger: @doctors
    if lower_text in ["@doctors", "doctors", "doctor", "specialists"]:
        reset_session(clean_phone)
        branches = get_branches()
        msg = "👨‍⚕️ *OUR DENTAL SPECIALISTS:*\n\n"
        found_any = False
        if branches:
            for b in branches:
                docs = get_doctors_by_branch(b.get("id"))
                if docs:
                    found_any = True
                    msg += f"🏢 *{b.get('name')}:*\n"
                    for d in docs:
                        msg += f"  • *{d.get('name')}* ({d.get('specialty') or 'Dental Specialist'})\n"
                    msg += "\n"
        if not found_any:
            msg = "👨‍⚕️ *Our Dental Specialists:* Please reply *@appointment* to check available doctors for your preferred clinic branch!"
        else:
            msg += "Reply *@appointment* to book an appointment with any doctor!"
        await send_waha_message(from_phone, msg)
        return {"status": "processed", "action": "doctors"}

    # 4. Command Trigger: @myappointments
    if lower_text in ["@myappointments", "my appointments", "my appointment", "my bookings"]:
        reset_session(clean_phone)
        appts = get_patient_upcoming_appointments(from_phone)
        if appts:
            msg = "📅 *YOUR UPCOMING APPOINTMENTS:*\n\n"
            for idx, a in enumerate(appts, 1):
                p_name = a.get("patients", {}).get("name") if isinstance(a.get("patients"), dict) else "Patient"
                d_name = a.get("doctors", {}).get("name") if isinstance(a.get("doctors"), dict) else "Doctor"
                b_name = a.get("branches", {}).get("name") if isinstance(a.get("branches"), dict) else "Clinic"
                date_str = a.get("appointment_date")
                time_str = a.get("appointment_time")
                status = a.get("status", "Confirmed").capitalize()
                
                msg += f"{idx}️⃣ *{p_name}*\n"
                msg += f"   🗓️ Date: {date_str} @ {time_str}\n"
                msg += f"   👨‍⚕️ Doctor: {d_name}\n"
                msg += f"   🏢 Branch: {b_name}\n"
                msg += f"   📌 Status: {status}\n\n"
        else:
            msg = "📋 *No upcoming appointments found for your mobile number.* \n\nReply *@appointment* to schedule a visit now!"
        await send_waha_message(from_phone, msg)
        return {"status": "processed", "action": "my_appointments"}

    # 5. Command Trigger: @reports
    if lower_text in ["@reports", "reports", "report", "prescription", "xray"]:
        reset_session(clean_phone)
        msg = (
            f"📄 *PATIENT MEDICAL REPORTS & PRESCRIPTIONS*\n\n"
            f"You can view and download all your past clinical reports, prescriptions, and X-rays directly on our patient portal:\n\n"
            f"👉 https://dental.flynx.site/family\n\n"
            f"Log in with your registered mobile number to access your records securely!"
        )
        await send_waha_message(from_phone, msg)
        return {"status": "processed", "action": "reports"}

    # 6. Appointment Flow Trigger: @appointment, appointment, @appoint, @book, book
    is_appointment_trigger = any(kw in lower_text for kw in ["@appointment", "appointment", "@appoint", "@book", "book"])
    
    if current_state == "IDLE" and is_appointment_trigger:
        # Step 1: Query registered patient profiles for this phone number from Supabase
        patients = get_patients_by_phone(from_phone)
        
        if not patients:
            # NO account found -> Send registration portal link
            no_acc_msg = (
                f"👋 *Welcome to Dental Care Clinic!*\n\n"
                f"We could not find a registered patient profile for your mobile number (*+{clean_phone}*).\n\n"
                f"Please create your patient profile online to proceed with booking:\n"
                f"👉 {REGISTER_URL}?phone={clean_phone}\n\n"
                f"Once registered, reply *@appointment* anytime to book instantly!"
            )
            await send_waha_message(from_phone, no_acc_msg)
            return {"status": "processed", "action": "no_account_redirect"}

        # 1+ Account(s) found -> List registered family members
        session["state"] = "SELECT_PATIENT"
        session["data"]["patients_list"] = patients

        msg = f"👤 *SELECT PATIENT PROFILE:*\n"
        msg += f"The following profiles are registered under your mobile number:\n\n"
        
        for idx, p in enumerate(patients, 1):
            age_info = f" (Age: {p.get('age')})" if p.get('age') else ""
            msg += f"{idx}️⃣ *{p.get('name')}*{age_info}\n"
        
        reg_idx = len(patients) + 1
        msg += f"{reg_idx}️⃣ *+ Register New Family Member Profile*\n\n"
        msg += f"Please reply with the number (e.g., 1 or 2) to select."
        
        await send_waha_message(from_phone, msg)
        return {"status": "processed", "action": "prompt_patient_select"}

    # State: SELECT_PATIENT
    if current_state == "SELECT_PATIENT":
        patients = session["data"].get("patients_list", [])
        if not lower_text.isdigit():
            await send_waha_message(from_phone, "⚠️ Please reply with a valid number choice (e.g. 1 or 2).")
            return {"status": "retry"}
            
        choice = int(lower_text)
        if choice == len(patients) + 1:
            reset_session(clean_phone)
            reg_msg = f"📝 *Register New Profile:*\nPlease visit our online portal to add a new family member:\n👉 {REGISTER_URL}?phone={clean_phone}"
            await send_waha_message(from_phone, reg_msg)
            return {"status": "processed"}

        if choice < 1 or choice > len(patients):
            await send_waha_message(from_phone, f"⚠️ Invalid choice. Please select a number between 1 and {len(patients) + 1}.")
            return {"status": "retry"}

        selected_patient = patients[choice - 1]
        session["data"]["patient_id"] = selected_patient.get("id")
        session["data"]["patient_name"] = selected_patient.get("name")

        # Step 2: Fetch branches dynamically from Supabase
        branches = get_branches()
        if not branches:
            reset_session(clean_phone)
            await send_waha_message(from_phone, "❌ Sorry, no active clinic branches were found in our database.")
            return {"status": "error"}

        session["state"] = "SELECT_BRANCH"
        session["data"]["branches_list"] = branches

        msg = f"🏢 *SELECT CLINIC BRANCH:*\n"
        msg += f"Selected Patient: *{selected_patient.get('name')}*\n\n"
        for idx, b in enumerate(branches, 1):
            msg += f"{idx}️⃣ *{b.get('name')}*\n"
        msg += f"\nPlease reply with the branch number."

        await send_waha_message(from_phone, msg)
        return {"status": "processed", "action": "prompt_branch_select"}

    # State: SELECT_BRANCH
    if current_state == "SELECT_BRANCH":
        branches = session["data"].get("branches_list", [])
        if not lower_text.isdigit():
            await send_waha_message(from_phone, "⚠️ Please reply with a valid branch number.")
            return {"status": "retry"}

        choice = int(lower_text)
        if choice < 1 or choice > len(branches):
            await send_waha_message(from_phone, f"⚠️ Invalid choice. Please select between 1 and {len(branches)}.")
            return {"status": "retry"}

        selected_branch = branches[choice - 1]
        session["data"]["branch_id"] = selected_branch.get("id")
        session["data"]["branch_name"] = selected_branch.get("name")

        # Step 3: Date Selection
        today_str = date.today().isoformat()
        tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
        
        session["state"] = "SELECT_DATE"
        session["data"]["today_str"] = today_str
        session["data"]["tomorrow_str"] = tomorrow_str

        msg = (
            f"📅 *SELECT APPOINTMENT DATE:*\n"
            f"Branch: *{selected_branch.get('name')}*\n\n"
            f"1️⃣ Today ({today_str})\n"
            f"2️⃣ Tomorrow ({tomorrow_str})\n"
            f"3️⃣ Enter custom date (Format: YYYY-MM-DD)\n\n"
            f"Reply 1, 2, or type date."
        )

        await send_waha_message(from_phone, msg)
        return {"status": "processed", "action": "prompt_date_select"}

    # State: SELECT_DATE
    if current_state == "SELECT_DATE":
        selected_date = ""
        today_str = session["data"].get("today_str", date.today().isoformat())
        tomorrow_str = session["data"].get("tomorrow_str", (date.today() + timedelta(days=1)).isoformat())

        if lower_text == "1" or lower_text == "today":
            selected_date = today_str
        elif lower_text == "2" or lower_text == "tomorrow":
            selected_date = tomorrow_str
        else:
            # Try parsing custom date string YYYY-MM-DD or DD/MM/YYYY
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', text)
            if date_match:
                selected_date = date_match.group(0)
            else:
                await send_waha_message(from_phone, "⚠️ Please select 1 (Today), 2 (Tomorrow), or enter date in format YYYY-MM-DD.")
                return {"status": "retry"}

        session["data"]["date_str"] = selected_date

        # Step 4: Fetch doctors for this branch dynamically from Supabase
        branch_id = session["data"].get("branch_id")
        doctors = get_doctors_by_branch(branch_id)

        if not doctors:
            reset_session(clean_phone)
            await send_waha_message(from_phone, f"❌ No doctors are currently listed for this branch. Please reply *@appointment* to start again.")
            return {"status": "error"}

        session["state"] = "SELECT_DOCTOR"
        session["data"]["doctors_list"] = doctors

        msg = f"👨‍⚕️ *SELECT DENTAL SPECIALIST:*\n"
        msg += f"Date: *{selected_date}*\n\n"
        for idx, d in enumerate(doctors, 1):
            spec = f" ({d.get('specialty')})" if d.get('specialty') else ""
            msg += f"{idx}️⃣ *{d.get('name')}*{spec}\n"
        msg += f"\nPlease reply with the doctor number."

        await send_waha_message(from_phone, msg)
        return {"status": "processed", "action": "prompt_doctor_select"}

    # State: SELECT_DOCTOR
    if current_state == "SELECT_DOCTOR":
        doctors = session["data"].get("doctors_list", [])
        if not lower_text.isdigit():
            await send_waha_message(from_phone, "⚠️ Please reply with a valid doctor number.")
            return {"status": "retry"}

        choice = int(lower_text)
        if choice < 1 or choice > len(doctors):
            await send_waha_message(from_phone, f"⚠️ Invalid choice. Please select between 1 and {len(doctors)}.")
            return {"status": "retry"}

        selected_doctor = doctors[choice - 1]
        session["data"]["doctor_id"] = selected_doctor.get("id")
        session["data"]["doctor_name"] = selected_doctor.get("name")

        # Step 5: Dynamically calculate available slots from Supabase DB
        doctor_id = selected_doctor.get("id")
        date_str = session["data"].get("date_str")
        available_slots = get_available_time_slots(doctor_id, date_str)

        if not available_slots:
            await send_waha_message(from_phone, f"❌ All slots are fully booked for {selected_doctor.get('name')} on {date_str}. Please reply *@appointment* to pick another date/doctor.")
            reset_session(clean_phone)
            return {"status": "fully_booked"}

        session["state"] = "SELECT_SLOT"
        session["data"]["slots_list"] = available_slots

        msg = f"⏰ *SELECT TIME SLOT:*\n"
        msg += f"Doctor: *{selected_doctor.get('name')}*\n"
        msg += f"Date: *{date_str}*\n\n"
        for idx, slot in enumerate(available_slots, 1):
            msg += f"{idx}️⃣ *{slot}*\n"
        msg += f"\nPlease reply with the slot number."

        await send_waha_message(from_phone, msg)
        return {"status": "processed", "action": "prompt_slot_select"}

    # State: SELECT_SLOT
    if current_state == "SELECT_SLOT":
        slots = session["data"].get("slots_list", [])
        if not lower_text.isdigit():
            await send_waha_message(from_phone, "⚠️ Please reply with a valid time slot number.")
            return {"status": "retry"}

        choice = int(lower_text)
        if choice < 1 or choice > len(slots):
            await send_waha_message(from_phone, f"⚠️ Invalid choice. Please select between 1 and {len(slots)}.")
            return {"status": "retry"}

        selected_slot = slots[choice - 1]
        session["data"]["time_str"] = selected_slot

        # Step 6: Create Appointment in Supabase Database!
        p_id = session["data"].get("patient_id")
        d_id = session["data"].get("doctor_id")
        b_id = session["data"].get("branch_id")
        date_val = session["data"].get("date_str")
        p_name = session["data"].get("patient_name")
        d_name = session["data"].get("doctor_name")
        b_name = session["data"].get("branch_name")

        db_res = create_appointment(
            patient_id=p_id,
            doctor_id=d_id,
            branch_id=b_id,
            appointment_date=date_val,
            appointment_time=selected_slot,
            problem_description="Booked via WhatsApp Chatbot"
        )

        reset_session(clean_phone)

        if db_res.get("success"):
            token_id = str(db_res.get("data", {}).get("id", ""))[:6].upper()
            confirm_msg = (
                f"✅ *APPOINTMENT CONFIRMED!* 🦷\n"
                f"─────────────────────────────\n"
                f"🎟️ *Booking Token:* #{token_id}\n"
                f"👤 *Patient:* {p_name}\n"
                f"👨‍⚕️ *Doctor:* {d_name}\n"
                f"🏢 *Branch:* {b_name}\n"
                f"📅 *Date:* {date_val}\n"
                f"⏰ *Time Slot:* {selected_slot}\n"
                f"─────────────────────────────\n"
                f"📍 Please arrive 10-15 minutes prior to your time slot.\n"
                f"📞 Helpline: +91 8418878491"
            )
            await send_waha_message(from_phone, confirm_msg)
            return {"status": "success", "appointment": db_res.get("data")}
        else:
            err_msg = f"❌ Failed to confirm appointment: {db_res.get('error')}. Please reply *@appointment* to try again."
            await send_waha_message(from_phone, err_msg)
            return {"status": "error"}

    # Default Fallback Handler
    fallback_msg = (
        f"Thank you for contacting Dental Care Clinic! 🦷\n"
        f"Reply *@help* to see available commands or *@appointment* to book your visit."
    )
    await send_waha_message(from_phone, fallback_msg)
    return {"status": "processed", "action": "fallback"}
