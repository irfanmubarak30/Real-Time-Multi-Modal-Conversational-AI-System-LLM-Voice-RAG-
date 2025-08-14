#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple GIF Test for Twilio WhatsApp - Manual Testing
Run this with your phone number as argument: python simple_gif_test.py +1234567890
"""

import sys
import os
from dotenv import load_dotenv
from twilio.rest import Client

def test_gif_sending(phone_number):
    """Test sending a GIF to WhatsApp"""
    load_dotenv()
    
    # Twilio credentials
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
    
    if not all([account_sid, auth_token, twilio_phone]):
        print("ERROR: Missing Twilio credentials in .env file")
        return False
    
    try:
        client = Client(account_sid, auth_token)
        
        # Test with a public GIF that works
        test_gif_url = "https://media.giphy.com/media/3o7abKhOpu0NwenH3O/giphy.gif"
        
        print(f"Sending test GIF to {phone_number}...")
        
        message = client.messages.create(
            from_=f'whatsapp:{twilio_phone}',
            to=f'whatsapp:{phone_number}',
            body="Test GIF from LevelX Bot!",
            media_url=[test_gif_url]
        )
        
        print(f"SUCCESS: Message sent! SID: {message.sid}")
        print(f"Status: {message.status}")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_multiple_images(phone_number):
    """Test sending multiple images sequentially"""
    load_dotenv()
    
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
    
    try:
        client = Client(account_sid, auth_token)
        
        # Your placement images
        images = [
            ('https://drive.google.com/uc?export=download&id=1gQNOJ3YJQ5U9kavxkxoux2M2bcfSRuMH', 'Placement Success #1'),
            ('https://drive.google.com/uc?export=download&id=1Itx5xPA05mSCdTDbbm9SylYY4II1_E_t', 'Top Companies #2'),
            ('https://drive.google.com/uc?export=download&id=1ekO_EeK5xZjgfBNKojFy7Xa73RKS09lC', 'Salary Stats #3')
        ]
        
        print(f"Sending {len(images)} images to {phone_number}...")
        
        for i, (url, caption) in enumerate(images, 1):
            message = client.messages.create(
                from_=f'whatsapp:{twilio_phone}',
                to=f'whatsapp:{phone_number}',
                body=f"{caption} ({i}/{len(images)})",
                media_url=[url]
            )
            print(f"Sent image {i}: {message.sid}")
            
            # Small delay
            import time
            time.sleep(2)
        
        print("All images sent successfully!")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python simple_gif_test.py +1234567890")
        sys.exit(1)
    
    phone = sys.argv[1]
    if not phone.startswith('+'):
        phone = '+' + phone
    
    print("=== LevelX WhatsApp Media Test ===")
    print(f"Testing with: {phone}")
    print()
    
    choice = input("Choose test: (1) Single GIF, (2) Multiple Images, (3) Both: ")
    
    if choice == '1':
        test_gif_sending(phone)
    elif choice == '2':
        test_multiple_images(phone)
    elif choice == '3':
        test_gif_sending(phone)
        print("\nWaiting 5 seconds before sending images...")
        import time
        time.sleep(5)
        test_multiple_images(phone)
    else:
        print("Invalid choice")
