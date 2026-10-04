# 🤖 Dental Clinic WhatsApp Chatbot (Back4App Engine)

Production Python Chatbot backend for Dental Care Clinic. Powered by **FastAPI**, **WAHA GOWS Engine**, and **Supabase Database**.

---

## 🌟 Key Features

1. **Case-Insensitive Command Parser**:
   - `help` / `@help` → Displays interactive patient command menu (`@appointment`, `@reports`, `@branches`, `@doctors`, `@myappointments`).
   - `@appointment` / `appointment` / `@book` → Triggers the 6-step dynamic appointment booking flow.
   - `@branches` → Lists all active clinic branches and working hours dynamically from Supabase.
   - `@doctors` → Lists specialists per branch dynamically from Supabase.
   - `@myappointments` → Lists patient's upcoming bookings.
   - `@reports` → Provides direct link to patient prescriptions & X-Ray reports.

2. **100% Dynamic Server Data Integration**:
   - Registered patients & family members matching the mobile number are queried dynamically from Supabase `public.patients`.
   - If no account exists under the phone number, sends direct registration link: `https://dental.flynx.site/register`.
   - Available time slots are calculated dynamically by taking clinic operating slots and excluding existing booked appointments in Supabase `public.appointments`.

3. **Automated Reminders & Reschedule Alerts**:
   - **Morning Reminders**: APScheduler cron job runs daily at 08:00 AM IST to send WhatsApp reminders for today's appointments.
   - **Reschedule Alerts**: `/notify-reschedule` endpoint dispatches both a WhatsApp message via WAHA and an Email via Brevo when a doctor or admin changes an appointment date/time.

---

## 🚀 How to Deploy on Back4App.com

### Step 1: Create New Web App on Back4App
1. Log in to [Back4App Containers](https://www.back4app.com/products/containers).
2. Click **Create New App** → Select **GitHub**.
3. Select your repository (`KhanTafazzul/dental` or `back4app-chatbot` subfolder).

### Step 2: Configure Build & Deployment Settings
- **Name**: `dental-whatsapp-chatbot`
- **Environment**: `Docker` (Uses the included `Dockerfile`)
- **Port**: `8080`

### Step 3: Add Environment Variables in Back4App
Add the following Environment Variables in the Back4App App Dashboard:

| Key | Example Value |
|---|---|
| `WAHA_ENDPOINT` | `https://waha-latest-7jqm.onrender.com/api/sendText` |
| `WAHA_API_KEY` | `your_waha_api_key_here` |
| `WAHA_SESSION` | `session_01m405rneta0hy0bbp77y1ejyx` |
| `SUPABASE_URL` | `https://jmifnlqtcfdctvldukdw.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | `your-supabase-service-role-key` |
| `REGISTER_URL` | `https://dental.flynx.site/register` |
| `BREVO_API_KEY` | `your-brevo-api-key` |
| `PORT` | `8080` |

### Step 4: Configure Webhook in WAHA
After Back4App deploys your application, copy your Back4App App URL (e.g. `https://dental-chatbot.b4a.run`).

Set your WAHA webhook endpoint URL to:
`https://dental-chatbot.b4a.run/webhook`

---

## 🧪 Local Testing

To run locally:
```bash
cd back4app-chatbot
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```
Then test health check at `http://localhost:8080/health`.
