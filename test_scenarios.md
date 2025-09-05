# WhatsApp Bot Test Scenarios

## 🌍 Language Selection Testing
1. **Initial Contact**
   - Send any message to the bot
   - Verify language selection buttons appear
   - Test both "English" and "മലയാളം" options

2. **Language Switching**
   - Send "switch to malayalam" (from English)
   - Send "switch to english" (from Malayalam)
   - Verify responses are in correct language

## 📊 Survey Flow Testing
1. **Survey Initiation**
   - After language selection, bot should start survey
   - Verify Q1 appears with job role options

2. **Survey Questions (Test Both Languages)**
   - **Q1**: Current job role (Student, Working Professional, Freelancer, Other)
   - **Q2**: Tech background (Yes/No)
   - **Q3**: Career motivation
   - **Q4**: Area of interest (Web Dev, Mobile Dev, Data Science, etc.)

3. **Survey Edge Cases**
   - Select "Other" in Q1 → Should ask for specification
   - Test invalid responses → Should show error with options
   - Test both number responses (1, 2, 3) and text responses

## 🎯 Intent Detection Testing
1. **Placement Intent**
   - Send: "placement", "job", "hiring", "career opportunities"
   - Verify placement images and PDF are sent
   - Should only send once per session

2. **Fees Intent**
   - Send: "fees", "cost", "price", "how much"
   - Verify fees information images are sent
   - Should only send once per session

3. **Flutter Intent**
   - Send: "flutter", "mobile development"
   - Verify Flutter reel is sent
   - Should only send once per session

## 🎤 Voice Message Testing
1. **Voice Transcription**
   - Send voice messages in English
   - Verify transcription works with OpenAI Whisper
   - Test fallback to local speech recognition
   - Verify bot responds to transcribed text

## 💬 General Chat Testing
1. **RAG System**
   - After survey completion, ask questions about courses
   - Test in both English and Malayalam
   - Verify contextual responses

2. **Session Management**
   - Test "reset" or "restart" commands
   - Verify session state is cleared
   - Test multiple users simultaneously

## 🔄 Error Handling
1. **Invalid Input**
   - Send random text during survey
   - Send unsupported media types
   - Test network timeout scenarios

2. **Recovery**
   - Test bot recovery after errors
   - Verify graceful error messages in user's language

## 📈 Performance Testing
1. **Concurrent Users**
   - Test multiple WhatsApp numbers simultaneously
   - Verify no session interference

2. **Media Handling**
   - Test large voice messages
   - Test various audio formats (.ogg, .mp3, .wav)

## ✅ Expected Behaviors
- Language selection works correctly
- Survey progresses through all 4 questions
- Intent detection triggers appropriate media
- Voice messages are transcribed and processed
- Error messages are user-friendly and localized
- Session state is maintained properly
- Google Sheets integration logs survey data
