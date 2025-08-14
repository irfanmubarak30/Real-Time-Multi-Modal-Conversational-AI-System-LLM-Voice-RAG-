#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test GIF Sending with Twilio WhatsApp API
This script tests sending GIFs and images to verify media functionality on free trial accounts.
"""

import os
import sys
import logging
from dotenv import load_dotenv
from twilio.rest import Client

# Fix Windows console encoding
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GifTester:
    """Test GIF and media sending functionality"""
    
    def __init__(self):
        """Initialize with Twilio credentials"""
        load_dotenv()
        
        # Twilio credentials
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER')
        
        if not all([self.account_sid, self.auth_token, self.twilio_phone_number]):
            raise ValueError("❌ Twilio credentials are missing from .env file")
            
        # Initialize Twilio client
        self.twilio_client = Client(self.account_sid, self.auth_token)
        logger.info("✅ Twilio client initialized successfully")
        
        # Test media URLs
        self.test_media = {
            'welcome_gif': 'https://drive.google.com/uc?export=download&id=1t_Ey4i83mPFzHAt2k_rkQpC-uvmpyOck',
            'placement_image_1': 'https://drive.google.com/uc?export=download&id=1gQNOJ3YJQ5U9kavxkxoux2M2bcfSRuMH',
            'placement_image_2': 'https://drive.google.com/uc?export=download&id=1Itx5xPA05mSCdTDbbm9SylYY4II1_E_t',
            'test_gif_url': 'https://media.giphy.com/media/3o7abKhOpu0NwenH3O/giphy.gif',  # Public GIF for testing
            'test_image_url': 'https://picsum.photos/800/600'  # Random test image
        }
    
    def send_test_gif(self, to_phone, media_type='welcome_gif'):
        """Send a test GIF to verify media functionality"""
        try:
            media_url = self.test_media.get(media_type)
            if not media_url:
                logger.error(f"❌ Media type '{media_type}' not found")
                return False
            
            logger.info(f"📤 Sending {media_type} to {to_phone}")
            logger.info(f"🔗 Media URL: {media_url}")
            
            # Send GIF with caption
            message = self.twilio_client.messages.create(
                from_=f'whatsapp:{self.twilio_phone_number}',
                to=f'whatsapp:{to_phone}',
                body=f"🎬 Test {media_type.replace('_', ' ').title()}",
                media_url=[media_url]
            )
            
            logger.info(f"✅ GIF sent successfully! Message SID: {message.sid}")
            logger.info(f"📊 Message Status: {message.status}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error sending GIF: {e}")
            return False
    
    def send_multiple_images_sequential(self, to_phone):
        """Send multiple images sequentially to test batch sending"""
        try:
            logger.info(f"📤 Sending multiple images sequentially to {to_phone}")
            
            # Send intro message
            intro_message = self.twilio_client.messages.create(
                from_=f'whatsapp:{self.twilio_phone_number}',
                to=f'whatsapp:{to_phone}',
                body="🖼️ Testing multiple image sending (3 images coming up):"
            )
            logger.info(f"✅ Intro message sent: {intro_message.sid}")
            
            # Test images
            test_images = [
                ('placement_image_1', '🎯 Placement Success #1'),
                ('placement_image_2', '💼 Top Companies #2'),
                ('test_image_url', '📸 Random Test Image #3')
            ]
            
            for i, (media_key, caption) in enumerate(test_images, 1):
                media_url = self.test_media[media_key]
                
                message = self.twilio_client.messages.create(
                    from_=f'whatsapp:{self.twilio_phone_number}',
                    to=f'whatsapp:{to_phone}',
                    body=f"{caption} ({i}/3)",
                    media_url=[media_url]
                )
                
                logger.info(f"✅ Image {i}/3 sent: {message.sid}")
                
                # Small delay to avoid rate limiting
                import time
                time.sleep(1)
            
            # Send completion message
            completion_message = self.twilio_client.messages.create(
                from_=f'whatsapp:{self.twilio_phone_number}',
                to=f'whatsapp:{to_phone}',
                body="✅ All test images sent successfully! Did you receive all 3 images?"
            )
            logger.info(f"✅ Completion message sent: {completion_message.sid}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error sending multiple images: {e}")
            return False
    
    def test_media_accessibility(self):
        """Test if all media URLs are accessible"""
        import requests
        
        logger.info("🔍 Testing media URL accessibility...")
        
        for media_name, url in self.test_media.items():
            try:
                response = requests.head(url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"✅ {media_name}: Accessible (Status: {response.status_code})")
                else:
                    logger.warning(f"⚠️ {media_name}: Status {response.status_code} - {url}")
            except Exception as e:
                logger.error(f"❌ {media_name}: Failed to access - {e}")
        
        logger.info("🏁 Media accessibility test completed")
    
    def get_account_info(self):
        """Get Twilio account information to check trial status"""
        try:
            account = self.twilio_client.api.accounts(self.account_sid).fetch()
            
            logger.info("📊 Twilio Account Information:")
            logger.info(f"   Account SID: {account.sid}")
            logger.info(f"   Account Status: {account.status}")
            logger.info(f"   Account Type: {account.type}")
            
            # Check if it's a trial account
            if account.type == 'Trial':
                logger.warning("⚠️ This is a TRIAL account - Rich content features may be limited!")
                logger.info("💡 Consider upgrading to access full WhatsApp Business API features")
            else:
                logger.info("✅ This is a PAID account - Full features available")
                
            return account
            
        except Exception as e:
            logger.error(f"❌ Error fetching account info: {e}")
            return None

def main():
    """Main function to run GIF tests"""
    print("Starting Twilio WhatsApp GIF & Media Tester")
    print("=" * 50)
    
    try:
        # Initialize tester
        tester = GifTester()
        
        # Get account info
        tester.get_account_info()
        print()
        
        # Test media accessibility
        tester.test_media_accessibility()
        print()
        
        # Get phone number for testing
        test_phone = input("Enter WhatsApp number to test (format: +1234567890): ").strip()
        
        if not test_phone.startswith('+'):
            test_phone = '+' + test_phone
        
        print(f"Testing with phone number: {test_phone}")
        print()
        
        # Menu for different tests
        while True:
            print("Choose a test:")
            print("1. Send Welcome GIF")
            print("2. Send Placement Image #1")
            print("3. Send Test GIF (Giphy)")
            print("4. Send Multiple Images Sequential")
            print("5. Test All Media URLs")
            print("6. Exit")
            
            choice = input("Enter choice (1-6): ").strip()
            
            if choice == '1':
                tester.send_test_gif(test_phone, 'welcome_gif')
            elif choice == '2':
                tester.send_test_gif(test_phone, 'placement_image_1')
            elif choice == '3':
                tester.send_test_gif(test_phone, 'test_gif_url')
            elif choice == '4':
                tester.send_multiple_images_sequential(test_phone)
            elif choice == '5':
                tester.test_media_accessibility()
            elif choice == '6':
                print("Goodbye!")
                break
            else:
                print("Invalid choice. Please try again.")
            
            print("-" * 30)
    
    except KeyboardInterrupt:
        print("\n👋 Test interrupted by user")
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")

if __name__ == "__main__":
    main()
