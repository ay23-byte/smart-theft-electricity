# SmartTheft Environment Setup Guide

## 🔐 Environment Variables Configuration

Your SmartTheft application now uses environment variables for secure credential management.

---

## 📋 Setup Instructions

### Step 1: Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

This will install `python-dotenv` which is required to load environment variables.

---

### Step 2: Create .env File

Copy the example environment file:

```bash
cd backend
cp .env.example .env
```

Or create a new `.env` file manually in the `backend/` folder.

---

### Step 3: Fill in Your Credentials

Open `backend/.env` and add your actual credentials:

```env
# Twilio Configuration
TWILIO_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_actual_auth_token
TWILIO_PHONE_FROM=+1234567890
TWILIO_PHONE_TO=+91XXXXXXXXXX

# Cesium Ion Token
CESIUM_ION_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

```

---

## 📚 Getting Your Credentials

### Twilio Setup
1. Go to https://www.twilio.com/console
2. Sign in to your Twilio account
3. Find your **Account SID** and **Auth Token**
4. Get a **Twilio Phone Number** at https://www.twilio.com/console/phone-numbers/incoming
5. Get a **Verified Number** to send SMS to

### Cesium Ion Token
1. Go to https://cesium.com/ion/tokens
2. Sign in with your Cesium Ion account
3. Create a new token
4. Copy the token and paste it into `.env`

## ⚙️ Environment Variables Reference

```
TWILIO_SID              Twilio Account SID (start with AC)
TWILIO_AUTH_TOKEN       Twilio Auth Token
TWILIO_PHONE_FROM       Your Twilio phone number
TWILIO_PHONE_TO         Recipient phone number for alerts

CESIUM_ION_TOKEN        Cesium Ion API token for 3D Earth

FLASK_ENV               development / production
FLASK_DEBUG             True / False
SECRET_KEY              Secret key for Flask sessions

DATABASE_PATH           Path to SQLite database
MAX_CITIES              Maximum cities to track (default: 10)
API_TIMEOUT             API request timeout in seconds (default: 30)
```

---

## 🚨 Security Best Practices

### ✅ DO:
- ✅ Keep `.env` file **private and never commit it**
- ✅ Use `.env.example` to show required variables
- ✅ Add `.env` to `.gitignore` (already done)
- ✅ Rotate credentials regularly
- ✅ Use environment-specific tokens

### ❌ DON'T:
- ❌ Commit `.env` to version control
- ❌ Share `.env` file in emails or chats
- ❌ Hard-code credentials in source code
- ❌ Use same credentials across environments
- ❌ Log sensitive information

---

## ▶️ Running the Application

```bash
cd backend
python app.py
```

The app will automatically load variables from `.env` file.

---

## 🐛 Troubleshooting

### "TWILIO_SID not found" error
- ✅ Make sure `.env` file exists in `backend/` folder
- ✅ Check spelling and format exactly match the example
- ✅ Restart the Flask server after creating/updating `.env`

### "ImportError: No module named 'dotenv'" error
- ✅ Install python-dotenv: `pip install python-dotenv`
- ✅ Or: `pip install -r requirements.txt`

### SMS not sending
- ✅ Verify Twilio credentials are correct
- ✅ Check that phone numbers include country code (+1 or +91)
- ✅ Ensure recipient number is verified in Twilio console
- ✅ Check account has enough credits

### Map/3D Earth not loading
- ✅ Cesium Ion token may be missing or invalid
- ✅ Check `.env` file has `CESIUM_ION_TOKEN` set
- ✅ Verify token is active on https://cesium.com/ion/tokens

---

## 🔄 Accessing Variables in Code

In `app.py`, variables are loaded like this:

```python
from dotenv import load_dotenv
import os

load_dotenv()

# Access variables
TWILIO_SID = os.getenv('TWILIO_SID', 'default_value')
CESIUM_ION_TOKEN = os.getenv('CESIUM_ION_TOKEN', '')
```

---

## 📁 File Structure

```
backend/
├── .env              ← Your actual credentials (NEVER commit)
├── .env.example      ← Template with example values
├── app.py            ← Updated to use environment variables
├── requirements.txt  ← Now includes python-dotenv
└── data/
    └── theft.db      ← Database (ignored in .gitignore)

.gitignore           ← Prevents .env from being committed
```

---

## ✨ All Set!

Your SmartTheft application is now configured for secure credential management. All sensitive data is now loaded from environment variables instead of being hard-coded. 🎉
