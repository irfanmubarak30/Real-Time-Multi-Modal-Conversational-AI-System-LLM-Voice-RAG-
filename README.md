# AI-Powered WhatsApp Bot for Tech Education

A comprehensive WhatsApp chatbot powered by FastAPI that automates student engagement, conducts intelligent surveys, processes voice messages, and provides personalized course recommendations with advanced follow-up automation.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **AI Chat Engine** | LangChain + OpenAI/Google Gemini for intelligent responses with RAG |
| 🎙️ **Voice Processing** | OpenAI Whisper for voice-to-text transcription & transcription |
| 📊 **Interactive Surveys** | 4-step survey with conditional logic & multi-language support |
| 📸 **Content Distribution** | Auto-send placement images, fees structures, Flutter reels on intent |
| 🔍 **Intent Detection** | Smart keyword matching for placement, fees, Flutter queries |
| 📱 **Bilingual Support** | Full English & Malayalam language switching |
| 👥 **Session Management** | Per-user state tracking with conversation history |
| 📅 **Follow-up Automation** | Intelligent follow-up messages (2-4 min intervals) with reply tracking |
| 💾 **Google Sheets Integration** | Auto-sync user data, survey responses, engagement scores |
| ⏱️ **Inactivity Detection** | Background task checks inactive users, sends smart re-engagement |
| 🌐 **Meta/Twilio Support** | Works with both Meta Cloud API & Twilio WhatsApp |
| 📈 **Engagement Scoring** | Calculates interest scores from survey progress + follow-up replies |

---

## 🛠️ Tech Stack

**Backend:**
- FastAPI (async web framework)
- Uvicorn (ASGI server)
- Python 3.8+

**AI/ML:**
- OpenAI (GPT, Whisper for transcription)
- Google Generative AI
- LangChain (RAG chains)
- Pinecone (vector database)

**Messaging:**
- Meta WhatsApp Cloud API
- Twilio WhatsApp API

**Audio Processing:**
- pydub (audio format conversion)
- SpeechRecognition (fallback transcription)

**Data Integration:**
- Google Sheets API
- Google Drive
- Aiohttp (async HTTP)

---

## 📋 Installation

### Prerequisites
- Python 3.8+
- Twilio or Meta WhatsApp Business Account
- OpenAI API Key
- Google Workspace (for Sheets integration)

### Setup

1. **Clone the Repository**
```bash
git clone https://github.com/irfanmubarak30/levelx.git
cd levelx
```

2. **Create Virtual Environment**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure Environment Variables**
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
# Twilio (Legacy Flask version)
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=whatsapp:+1234567890

# Meta WhatsApp Cloud API (FastAPI version)
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_VERIFY_TOKEN=your_verify_token

# AI APIs
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key

# Google Services
GOOGLE_SHEETS_ID=your_sheet_id
GOOGLE_DRIVE_FOLDER_ID=your_folder_id

# Pinecone
PINECONE_API_KEY=your_pinecone_key
PINECONE_ENVIORNMENT=your_environment
```

5. **Run the Server**

**FastAPI Version (Recommended):**
```bash
python start_fastapi.py
# API available at http://localhost:8001
# Docs at http://localhost:8001/docs
```

**Flask Version (Legacy):**
```bash
python whatsapp.py
# Bot running at http://localhost:5000
```

---

## 🏗️ Project Structure

```
levelx/
├── start_fastapi.py           # FastAPI server startup
├── whatsapp.py                # Flask app (Twilio version)
├── main_fastapi_backup.py     # FastAPI core (Meta Cloud API)
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
│
├── backend/
│   ├── config.py            # Configuration management
│   ├── cv_parser.py         # CV analysis (if used)
│   └── ...
│
├── credentials/              # Google service accounts
│   ├── gmail_credentials.json
│   └── sheets_credentials.json
│
└── src/
    └── main.py              # Core chat logic
```

---

## 🔄 How It Works

### Message Flow

```
User Message → WhatsApp Webhook → Session Lookup
    ↓
Language Selected? → Yes → Intent Detection
    ↓ No
Language Selection
    ↓
Intent Detection
├── Placement Intent? → Send 7 placement images
├── Fees Intent? → Send 3 fees structure images
├── Flutter Intent? → Send Flutter reel + response
└── General Query → RAG Chain + ChatBot Response
    ↓
Survey Triggered? → Send Q1 Poll
    ↓
Follow-up Logic:
├── 2 min inactive → First follow-up
├── 4 min inactive (no reply) → Second follow-up
└── 8 min inactive → Session end + interest score logged
```

### Survey Flow

**Q1:** Student / Working Professional / Other
  ↓
**Q2:** Tech background?
  ↓
**Q3:** Motivation to learn tech?
  ↓
**Q4:** Area of interest (Flutter, React, etc.)
  ↓
**Completion:** Name & Email collection

**Scoring:** Each step grants engagement points; follow-up replies boost interest score

---

## 🌐 API Endpoints

### Webhook
- **GET `/webhook`** - Meta webhook verification
- **POST `/webhook`** - Receive messages (text, audio, interactive buttons)

### Health & Monitoring
- **GET `/health`** - Server status
- **GET `/`** - API info

### Manual Testing
- **POST `/send-message`** - Send text message
- **POST `/send-placement-images`** - Trigger placement content
- **POST `/send-flutter-reel`** - Send Flutter reel

---

## 🎯 Intent Detection

### Placement Keywords
`placement`, `job`, `career`, `salary`, `package`, `job guarantee`, etc.

### Fees Keywords
`fees`, `cost`, `price`, `installment`, `emi`, `scholarship`, etc.

### Flutter Keywords
`flutter`, `flutter development`, `flutter course`, `flutter app`, etc.

---

## 📊 Survey & Follow-Up Logic

### Multi-Stage Follow-up
1. **First Follow-up** (2 min): "Hi {name}, did you get admission? Limited seats for {interest}"
2. **Second Follow-up** (4 min): "{name}, don't miss! Seats available. Reply ADMISSION"
3. **Session End** (8 min): Compute interest score, log to Google Sheets

### Interest Score Calculation
- Language selected: +10 pts
- Q2 progress: +5 pts
- Q3 progress: +10 pts
- Q4 progress: +15 pts
- Survey completed: +20 pts
- First follow-up reply: +10 pts
- Second follow-up reply: +5 pts
- **Total Range:** 0-100

---

## 🗣️ Bilingual Support

**Automatic Language Switching:**
```
User types "Malayalam" → All responses in Malayalam
User types "English" → All responses in English
User types "switch to english/malayalam" → Language switched

All surveys, follow-ups, and responses adapt to user language
```

---

## 🔐 Configuration

### Google Sheets Setup
1. Create 2 Google Sheets:
   - **Users Sheet:** Columns: name, number, language, interest_score, interest_summary
   - **Survey Sheet:** Columns: name, number, q1, q2, q3, q4, followup_responses

2. Get Sheet IDs from URLs (string between `/d/` and `/edit`)

3. Place Google service account JSON in `credentials/`

### Twilio/Meta Setup
- Configure webhook URL in Twilio/Meta settings
- Verify webhook token
- Test with sample messages

---

## 🧪 Testing

**Health Check:**
```bash
curl http://localhost:8001/health
```

**Send Message:**
```bash
curl -X POST http://localhost:8001/send-message \
  -H "Content-Type: application/json" \
  -d '{"phone":"919123456789", "message":"Hello!"}'
```

**Send Placement Images:**
```bash
curl -X POST http://localhost:8001/send-placement-images \
  -H "Content-Type: application/json" \
  -d '{"phone":"919123456789"}'
```

---

## 📈 Monitoring & Logs

**Enable Debug Mode (.env):**
```
DEBUG=true
```

**Check Active Sessions:**
- FastAPI Docs: http://localhost:8001/docs
- Filter by phone number in logs

**Track Interest Scores:**
- View Google Sheets integration
- Monitor survey completions & follow-up replies

---

## 🚀 Deployment

### Docker
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "start_fastapi.py"]
```

### Production (Gunicorn + Uvicorn)
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main_fastapi:app --bind 0.0.0.0:8001
```

### Environment
- Use HTTPS only (via reverse proxy like Nginx)
- Set `DEBUG=false`
- Configure proper error logging
- Use Redis for session management (production scale)

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Webhook not triggering | Verify token & URL in Twilio/Meta settings |
| Voice not transcribing | Check OpenAI API key & quota |
| Google Sheets not updating | Verify service account has editor access |
| Images not sending | Check Google Drive links & Twilio daily limits |
| Survey not starting | Enable `DEBUG=true` and check logs |

---

## 📚 Additional Resources

- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - Flask to FastAPI migration
- [test_scenarios.md](test_scenarios.md) - Testing workflows
- [FastAPI Docs](http://localhost:8001/docs) - Interactive API documentation

---

## 🤝 Contributing

Pull requests welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit changes with clear messages
4. Submit a pull request

---

## 📄 License

MIT License - see LICENSE file

---

## 👤 Author

Built by Irfan Mubarak for  Education Platforms

**Contact:** irfanmubarak.k30@gmail.com

---

**Last Updated:** April 2026 | **Status:** Active Development
