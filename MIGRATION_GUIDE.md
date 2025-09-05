# Flask to FastAPI Migration Guide

## Overview
This guide walks you through migrating your LevelX WhatsApp Bot from Flask to FastAPI.

## Key Changes

### 1. Framework Differences
- **Flask**: Synchronous by default
- **FastAPI**: Async-first with automatic API documentation
- **Type Safety**: FastAPI uses Pydantic models for request/response validation
- **Performance**: FastAPI is generally faster due to async capabilities

### 2. Dependencies Updated
```bash
# Removed
flask

# Added
fastapi
uvicorn[standard]
python-multipart
pydantic
aiohttp
```

### 3. Route Conversion
**Flask:**
```python
@app.route('/webhook', methods=['GET'])
def whatsapp_webhook_verify():
    mode = request.args.get('hub.mode')
    return challenge or '', 200

@app.route('/webhook', methods=['POST'])
def whatsapp_webhook():
    data = request.get_json()
    return jsonify({'status': 'ok'}), 200
```

**FastAPI:**
```python
@app.get("/webhook")
async def whatsapp_webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"), 
    hub_challenge: str = Query(alias="hub.challenge")
):
    if hub_mode == 'subscribe' and hub_verify_token == whatsapp_bot.whatsapp_verify_token:
        return PlainTextResponse(content=hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Forbidden")

@app.post("/webhook")
async def whatsapp_webhook(
    webhook_data: WhatsAppWebhookData,
    background_tasks: BackgroundTasks
):
    # Process in background for better performance
    background_tasks.add_task(process_whatsapp_message, ...)
    return WebhookResponse(status="ok")
```

## Migration Steps

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Complete WhatsAppBot Methods
You need to copy the remaining methods from your original `src/main.py` into `src/main_fastapi.py`. 

Key methods to copy and convert to async:
- `detect_placement_intent()`
- `detect_fees_intent()`
- `detect_flutter_intent()`
- `send_placement_images()` → `async def send_placement_images()`
- `send_fees_images()` → `async def send_fees_images()`
- `send_flutter_reel()` → `async def send_flutter_reel()`
- `send_survey_poll()`
- `process_poll_response()`
- `transcribe_audio_whisper()` → `async def transcribe_audio_whisper()`
- `download_media_file_by_id()` → `async def download_media_file_by_id()`
- `handle_language_selection()`
- `send_language_selection_buttons()`
- `reset_user_session()`
- `get_whatsapp_profile_name()`
- `_check_followup_reply()`
- `_schedule_followup()`
- `_send_followup_message()`
- `_check_inactive_users()`

### Step 3: Update HTTP Calls
Replace `requests` with `aiohttp` for async operations:

**Before (Flask/requests):**
```python
resp = requests.post(url, headers=headers, json=payload)
```

**After (FastAPI/aiohttp):**
```python
async with aiohttp.ClientSession() as session:
    async with session.post(url, headers=headers, json=payload) as resp:
        # handle response
```

### Step 4: Complete Message Processing
Update the `process_whatsapp_message()` function to include all the logic from your original Flask webhook handler:

1. Language selection handling
2. Survey processing
3. Poll responses
4. Voice message processing
5. Intent detection (placement, fees, flutter)
6. Follow-up message scheduling

### Step 5: Test the Application
```bash
python start_fastapi.py
```

## Key Benefits of Migration

### 1. **Better Performance**
- Async/await support for concurrent request handling
- Background tasks for long-running operations
- Better resource utilization

### 2. **Automatic API Documentation**
- Visit `http://localhost:8000/docs` for interactive Swagger UI
- OpenAPI schema generation
- Built-in request/response validation

### 3. **Type Safety**
- Pydantic models ensure data validation
- Better IDE support with type hints
- Reduced runtime errors

### 4. **Modern Python Features**
- Native async/await support
- Dependency injection system
- Better error handling with HTTP exceptions

## Testing Your Migration

### 1. Health Check
```bash
curl http://localhost:8000/health
```

### 2. Webhook Verification
```bash
curl "http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=test"
```

### 3. API Documentation
Visit `http://localhost:8000/docs` to see the interactive API documentation.

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed
2. **Async/Sync Mixing**: Make sure to use `await` with async functions
3. **Request Parsing**: FastAPI automatically parses JSON with Pydantic models

### Environment Variables
Make sure your `.env` file contains:
```
WHATSAPP_PHONE_NUMBER_ID=your_id
WHATSAPP_ACCESS_TOKEN=your_token
WHATSAPP_VERIFY_TOKEN=your_verify_token
OPENAI_API_KEY=your_openai_key
PINECONE_API_KEY=your_pinecone_key
# ... other variables
```

## Manual Method Migration

Since you need to manually copy methods, here's the process:

1. Open both `src/main.py` and `src/main_fastapi.py`
2. Find each method in the original WhatsAppBot class
3. Copy the method to the FastAPI version
4. For HTTP-related methods, add `async` and use `await` with `aiohttp`
5. Update any `self._graph_post()` calls to `await self._graph_post()`

## Performance Comparison

| Aspect | Flask | FastAPI |
|--------|-------|---------|
| Request Handling | Synchronous | Asynchronous |
| Documentation | Manual | Automatic |
| Type Validation | Manual | Automatic |
| Performance | Good | Excellent |
| Learning Curve | Easy | Moderate |

## Next Steps

1. **Complete Method Migration**: Copy all missing methods from original file
2. **Test Functionality**: Verify all features work (surveys, voice, media)
3. **Monitor Performance**: Use FastAPI's built-in metrics
4. **Add More Endpoints**: Leverage FastAPI's features for additional APIs
5. **Database Integration**: Consider async database drivers
6. **Deployment**: Use ASGI servers like Uvicorn or Gunicorn with Uvicorn workers

## Support

If you encounter issues during migration:
1. Check the logs for specific error messages
2. Verify all environment variables are set
3. Test individual components separately
4. Use the health check endpoint to verify the app is running
