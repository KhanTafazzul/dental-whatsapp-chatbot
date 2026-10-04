import os
from dotenv import load_dotenv

load_dotenv()

# WAHA WhatsApp API Configuration
WAHA_ENDPOINT = os.getenv("WAHA_ENDPOINT", "")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY", ""))

# Email Configuration (Brevo / Resend)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "")

# Web Application Registration Link
REGISTER_URL = os.getenv("REGISTER_URL", "https://dental.flynx.site/register")

# Port for FastAPI Server
PORT = int(os.getenv("PORT", "8080"))
