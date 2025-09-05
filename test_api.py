#!/usr/bin/env python3
"""
API Testing Script for FastAPI WhatsApp Bot
Run this to test your endpoints automatically
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_health_endpoint():
    """Test the health check endpoint"""
    print("🔍 Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")

def test_webhook_verification():
    """Test webhook verification"""
    print("\n🔍 Testing webhook verification...")
    try:
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "your_verify_token_here",  # Replace with actual token
            "hub.challenge": "test_challenge_123"
        }
        response = requests.get(f"{BASE_URL}/webhook", params=params)
        if response.status_code == 200:
            print("✅ Webhook verification passed")
        else:
            print(f"❌ Webhook verification failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Webhook verification error: {e}")

def test_webhook_message():
    """Test webhook message processing"""
    print("\n🔍 Testing webhook message processing...")
    
    # Test message payload
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "1234567890",
                        "type": "text",
                        "text": {"body": "hello test"}
                    }]
                }
            }]
        }]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/webhook",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            print("✅ Webhook message processing passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Webhook message processing failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Webhook message processing error: {e}")

def test_survey_flow():
    """Test survey message flow"""
    print("\n🔍 Testing survey flow...")
    
    # Simulate survey responses
    survey_messages = [
        "english",  # Language selection
        "1",        # Q1: Student
        "2",        # Q2: No tech background
        "career growth",  # Q3: Motivation
        "1"         # Q4: Web Development
    ]
    
    phone_number = "test_user_123"
    
    for i, message in enumerate(survey_messages):
        print(f"   Sending survey message {i+1}: {message}")
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": phone_number,
                            "type": "text",
                            "text": {"body": message}
                        }]
                    }
                }]
            }]
        }
        
        try:
            response = requests.post(f"{BASE_URL}/webhook", json=payload)
            if response.status_code == 200:
                print(f"   ✅ Survey step {i+1} processed")
            else:
                print(f"   ❌ Survey step {i+1} failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Survey step {i+1} error: {e}")
        
        time.sleep(1)  # Small delay between messages

def main():
    """Run all tests"""
    print("🧪 Starting FastAPI WhatsApp Bot Tests")
    print("=" * 50)
    
    # Check if server is running
    try:
        requests.get(BASE_URL, timeout=5)
    except requests.exceptions.ConnectionError:
        print("❌ Server not running! Start with: python start_fastapi.py")
        return
    
    test_health_endpoint()
    test_webhook_verification()
    test_webhook_message()
    test_survey_flow()
    
    print("\n" + "=" * 50)
    print("🏁 Testing completed!")
    print("\nNext steps:")
    print("1. Set up ngrok for WhatsApp webhook testing")
    print("2. Test with real WhatsApp messages")
    print("3. Verify Google Sheets integration")

if __name__ == "__main__":
    main()
