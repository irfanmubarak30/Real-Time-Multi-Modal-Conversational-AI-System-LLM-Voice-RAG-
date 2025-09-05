import os
import re
import json
import logging
import requests
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import tempfile
from pydub import AudioSegment
import speech_recognition as sr
 

# Import your existing ChatBot class
from levelx import ChatBot, LeadStatus, LeadData

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WhatsAppBot:
    """WhatsApp integration for the LevelX AI Assistant with voice transcription and placement images"""
    
    def __init__(self):
        """Initialize WhatsApp bot with Meta WhatsApp Cloud API and speech recognition"""
        load_dotenv()
        
        # Meta WhatsApp Cloud API credentials
        self.whatsapp_phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        self.whatsapp_access_token = os.getenv('WHATSAPP_ACCESS_TOKEN')
        self.whatsapp_verify_token = os.getenv('WHATSAPP_VERIFY_TOKEN')
        self.whatsapp_app_secret = os.getenv('WHATSAPP_APP_SECRET')  # optional
        self.graph_api_base = "https://graph.facebook.com/v17.0"
        if not all([self.whatsapp_phone_number_id, self.whatsapp_access_token]):
            raise ValueError("WhatsApp Cloud API credentials are missing from .env file")
        self.graph_messages_url = f"{self.graph_api_base}/{self.whatsapp_phone_number_id}/messages"
        self.graph_headers = {
            "Authorization": f"Bearer {self.whatsapp_access_token}",
            "Content-Type": "application/json"
        }
        
        # OpenAI API key for Whisper
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        
        # Welcome MP4 video URL from Google Drive (direct download link)
        # Original share link: https://drive.google.com/file/d/1z2-RZ0D-fpmL8RgFyT4tLX1PNSR9aCYz/view
        self.welcome_video = 'https://drive.google.com/uc?export=download&id=1z2-RZ0D-fpmL8RgFyT4tLX1PNSR9aCYz'
        
        # Follow-up message configuration
        self.follow_up_minutes = 2  # First follow-up after 2 minutes
        self.second_follow_up_minutes = 4  # Second follow-up after 4 minutes (2 minutes after first)
        self.session_timeout_minutes = 8  # Default session timeout
        self.reply_timeout_minutes = 10  # Timeout after user replies to follow-up
        self.second_followup_timeout_minutes = 6  # Timeout after second follow-up if no reply
        
        # Follow-up messages in both languages
        self.follow_up_messages = {
            'survey_complete': {
                'english': "Hello {name}, did you get admission? If not, there are still limited seats left for {interest}",
                'malayalam': "ഹലോ {name}, നിങ്ങൾക്ക് admission ലഭിച്ചോ? അല്ലെങ്കിൽ, {interest} ക്കായി ഇപ്പോഴും പരിമിതമായ സീറ്റുകൾ മാത്രമേ ലഭ്യമുള്ളൂ"
            },
            'survey_second_followup': {
                'english': "{name}, don't miss this opportunity! Limited seats available for {interest}. Reply 'ADMISSION' to know more.",
                'malayalam': "{name}, ഈ അവസരം നഷ്ടപ്പെടുത്തരുത്! {interest} ക്കായി പരിമിതമായ സീറ്റുകൾ മാത്രം. കൂടുതൽ അറിയാൻ 'ADMISSION' എന്ന് മെസ്സേജ് ചെയ്യുക."
            },
            'general_followup': {
                'english': "Hi {name}, we noticed you were interested in our courses. Would you like to continue exploring?",
                'malayalam': "ഹായ് {name}, ഞങ്ങളുടെ കോഴ്സുകളിൽ നിങ്ങൾക്ക് താല്പര്യമുണ്ടെന്ന് ഞങ്ങൾ ശ്രദ്ധിച്ചു. നിങ്ങൾക്ക് തുടരാൻ ആഗ്രഹിക്കുന്നുണ്ടോ?"
            }
        }
        
        # Initialize speech recognizer
        self.recognizer = sr.Recognizer()
        
        # Initialize your existing chatbot
        self.chatbot = ChatBot()
        
        # Store user sessions (in production, use Redis or database)
        self.user_sessions = {}
        
        # Placement configuration - First image + PDF document
        self.placement_image = {
            'url': 'https://drive.google.com/uc?export=download&id=189wzLNXFdN-cgytWf28cnt6Jk-TYZMM5',
            'caption': '🎯 100% Placement Guarantee - Our Track Record'
        }
        
        # Placement PDF document
        self.placement_pdf = {
            'url': 'https://drive.google.com/uc?export=download&id=1wMTYJk0_INBOWDmnw77O32nT-TSyEL3P',
            'caption': '📄 thats our Complete Placement Details & Success Stories do you have any specific questions about placements? '
        }
        
        # Keywords that trigger placement images
        self.placement_keywords = [
            'placement', 'job', 'career', 'hiring', 'salary', 'package', 'company',
            'placement guaranteed', 'job assured', 'get job', 'will i get job',
            'job guarantee', 'placement assistance', 'career support', 'employment',
            'പ്ലേസ്മെന്റ്', 'ജോലി', 'കരിയർ', 'ശമ്പളം', 'കമ്പനി'
        ]
        
        # Keywords that trigger fees structure images
        self.fees_keywords = [
            'fees', 'fee', 'cost', 'price', 'pricing', 'amount', 'payment', 'money',
            'how much', 'fee structure', 'course fee', 'tuition', 'charges', 'expense',
            'affordable', 'budget', 'installment', 'emi', 'scholarship', 'discount',
            'ഫീസ്', 'വില', 'പണം', 'ചെലവ്', 'തുക', 'പേയ്മെന്റ്', 'എത്ര', 'ബജറ്റ്'
        ]
        
        # Fees structure images configuration
        self.fees_images = [
            {
                'url': 'https://drive.google.com/uc?export=download&id=18RAmBOEDeSq43KasXN6arsnFqcqT5iLn',
                'caption': '💰 LevelX Course Fees Structure - Complete Breakdown'
            },
            {
                'url': 'https://drive.google.com/uc?export=download&id=1spNDedyHntz-DrEnqCaHTXoS5v7J2lYX', 
                'caption': '📊 Flexible Payment Options - EMI Available'
            },
            {
                'url': 'https://drive.google.com/uc?export=download&id=1spNDedyHntz-DrEnqCaHTXoS5v7J2lYX', 
                'caption': '₹ 10000/- scholarship available for students'
            }
        ]
        
        # Keywords that trigger Flutter reel
        self.flutter_keywords = [
            'flutter', 'flutter development', 'flutter course', 'flutter app',
            'flutter programming', 'flutter framework', 'flutter mobile',
            'flutter full stack', 'flutter backend', 'flutter firebase',
            'flutter developer', 'flutter training', 'flutter learning',
            'flutter project', 'flutter tutorial', 'flutter coding',
            'flutter app development', 'flutter mobile development'
        ]
        
        # Flutter reel configuration
        self.flutter_reel = {
            'url': 'https://www.instagram.com/reel/DMaOsgOMm0F/?igsh=c3hkd3lyMzYyNmI4',
            'caption': '🚀 Check out this amazing Flutter development reel! See how our students build stunning mobile apps with Flutter and Firebase. This is exactly what you\'ll learn in our Flutter Full Stack Development course! 💻📱'
        }
        
        # Survey poll configuration with both English and Malayalam
        self.survey_polls = {
            'q1': {
                'question': {
                    'english': 'Are you a student / working professional / other?',
                    'malayalam': 'താങ്കൾ ഒരു Student ആണോ / Working Professional ആണോ/മറ്റ് ഏതെങ്കിലുമാണോ??'
                },
                'options': {
                    'english': ['Student', 'Working Professional', 'Other'],
                    'malayalam': ['Student', 'Working Professional', 'Other']
                }
            },
            'q2': {
                'question': {
                    'english': 'Are you from a tech background?',
                    'malayalam': 'നിങ്ങൾ Tech backgrounൽ നിന്ന് ആണോ വരുന്നത്??'
                },
                'options': {
                    'english': ['Yes', 'No'],
                    'malayalam': ['അതെ', 'അല്ല']
                }
            },
            'q3': {
                'question': {
                    'english': 'What motivates you to learn tech?',
                    'malayalam': 'ടെക് പഠിക്കാൻ നിങ്ങളെ പ്രേരിപ്പിക്കുന്നത് എന്താണ്?'
                },
                'options': {
                    'english': ['Career change', 'Higher salary', 'Freelancing', 'Passion'],
                    'malayalam': ['കരിയർ മാറ്റം', 'ഉയർന്ന ശമ്പളം', 'ഫ്രീലാൻസിംഗ്', 'താൽപര്യം']
                }
            },
            'q4': {
                'question': {
                    'english': 'Which area interests you most?)',
                    'malayalam': 'താങ്കൾക്ക് ഏറ്റവും താൽപര്യമുള്ള/Area ഏതാണ്?)'
                },
                'options': {
                    'english': ['Flutter full stack', 'Full Stack React', 'MEAN Stack Development', 'MERN Stack Development', 'Not sure'],
                    'malayalam': ['flutter Full Stack ', 'Full Stack React', 'MEAN Stack Development', 'MERN Stack Development', 'Not sure (ഉറപ്പില്ല / തീർച്ചയല്ല)']
                }
            }
        }

        # Start the background task for checking inactive users
        self._start_inactivity_checker()

    # ===== Meta WhatsApp Cloud API Helpers =====
    def _graph_post(self, payload):
        try:
            resp = requests.post(self.graph_messages_url, headers=self.graph_headers, json=payload, timeout=30)
            if not resp.ok:
                logger.error(f"Graph API error {resp.status_code}: {resp.text}")
            return resp
        except Exception as e:
            logger.error(f"Graph API request failed: {e}")
            return None

    def send_whatsapp_message(self, to_phone, message):
        """Send a WhatsApp text message via Meta Cloud API"""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "text",
                "text": {"body": message}
            }
            resp = self._graph_post(payload)
            if resp and resp.ok:
                logger.info(f"✅ Message sent to {to_phone}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send message to {to_phone}: {e}")
            return False

    def send_media_message(self, to_phone, media_url, caption=None):
        """Send an image/GIF via Meta Cloud API using a public link"""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "image",
                "image": {"link": media_url}
            }
            if caption:
                payload["image"]["caption"] = caption
            resp = self._graph_post(payload)
            if resp and resp.ok:
                logger.info(f"✅ Media message sent to {to_phone}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send media message to {to_phone}: {e}")
            return False

    def send_document_message(self, to_phone, document_url, caption=None, filename=None):
        """Send a PDF document via Meta Cloud API using a public link"""
        try:
            # Ensure the URL is properly formatted for direct download
            if 'drive.google.com' in document_url and 'uc?export=download' not in document_url:
                # Convert Google Drive share link to direct download link
                file_id = document_url.split('/d/')[1].split('/')[0] if '/d/' in document_url else document_url.split('id=')[1].split('&')[0]
                document_url = f'https://drive.google.com/uc?export=download&id={file_id}'
            
            # Ensure filename has .pdf extension
            if not filename:
                filename = "LevelX_Placement_Details.pdf"
            elif not filename.lower().endswith('.pdf'):
                filename = f"{filename}.pdf"
            
            document_payload = {
                "link": document_url,
                "filename": filename
            }
                
            # Add caption if provided
            if caption:
                document_payload["caption"] = caption
                
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "document",
                "document": document_payload
            }
            
            # Add headers to ensure PDF handling
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            import requests
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages",
                json=payload,
                headers=headers
            )
            
            if resp and resp.ok:
                logger.info(f"✅ PDF document sent to {to_phone} with filename: {filename}")
                return True
            else:
                logger.error(f"❌ PDF send failed: {resp.status_code if resp else 'No response'} - {resp.text if resp else 'No response text'}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to send PDF to {to_phone}: {e}")
            return False

    def send_video_message(self, to_phone, video_url, caption=None):
        """Send a video (MP4) via Meta Cloud API using a public link"""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "video",
                "video": {"link": video_url}
            }
            if caption:
                payload["video"]["caption"] = caption
            resp = self._graph_post(payload)
            if resp and resp.ok:
                logger.info(f"✅ Video message sent to {to_phone}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send video message to {to_phone}: {e}")
            return False

    def download_media_file_by_id(self, media_id: str) -> str | None:
        """Download media by Meta media_id and return local temp file path."""
        try:
            info_url = f"{self.graph_api_base}/{media_id}"
            info_resp = requests.get(info_url, headers={"Authorization": f"Bearer {self.whatsapp_access_token}"}, timeout=30)
            if not info_resp.ok:
                logger.error(f"Failed to fetch media info: {info_resp.status_code} {info_resp.text}")
                return None
            media_url = info_resp.json().get("url")
            if not media_url:
                logger.error("Media URL missing in info response")
                return None

            bin_resp = requests.get(media_url, headers={"Authorization": f"Bearer {self.whatsapp_access_token}"}, timeout=60)
            if not bin_resp.ok:
                logger.error(f"Failed to download media: {bin_resp.status_code} {bin_resp.text}")
                return None

            ctype = bin_resp.headers.get('Content-Type', '')
            suffix = '.ogg' if 'ogg' in ctype else '.mp4' if 'mp4' in ctype else '.bin'
            tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmpf.write(bin_resp.content)
            tmpf.close()
            return tmpf.name
        except Exception as e:
            logger.error(f"Error downloading media by id: {e}")
            return None
        
    # ... (rest of the code remains the same)

    def detect_placement_intent(self, message):
        """Detect if user is asking about placement/job-related queries"""
        message_lower = message.lower()
        
        # Check for placement keywords
        for keyword in self.placement_keywords:
            if keyword in message_lower:
                return True
        
        # Check for common placement question patterns
        placement_patterns = [
            r'will i get.*job',
            r'job.*guarantee',
            r'placement.*rate',
            r'salary.*package',
            r'companies.*hire',
            r'job.*assured',
            r'placement.*support',
            r'career.*opportunity',
            r'employment.*rate',
            r'job.*security'
        ]
        
        for pattern in placement_patterns:
            if re.search(pattern, message_lower):
                return True
        
        return False
    
    def detect_fees_intent(self, message):
        """Detect if user is asking about fees/pricing-related queries"""
        message_lower = message.lower()
        
        # Check for fees keywords
        for keyword in self.fees_keywords:
            if keyword in message_lower:
                return True
        
        # Check for common fees question patterns
        fees_patterns = [
            r'how much.*cost',
            r'what.*fee',
            r'course.*price',
            r'fees.*structure',
            r'payment.*plan',
            r'can.*afford',
            r'budget.*friendly',
            r'installment.*available',
            r'emi.*option',
            r'scholarship.*available'
        ]
        
        for pattern in fees_patterns:
            if re.search(pattern, message_lower):
                return True
        
        return False
    
    def detect_flutter_intent(self, message):
        """Detect if user is asking about Flutter-related queries"""
        message_lower = message.lower()
        
        # Check for Flutter keywords
        for keyword in self.flutter_keywords:
            if keyword in message_lower:
                return True
        
        # Check for common Flutter question patterns
        flutter_patterns = [
            r'flutter.*course',
            r'flutter.*development',
            r'flutter.*app',
            r'flutter.*learn',
            r'flutter.*programming',
            r'flutter.*framework',
            r'flutter.*mobile',
            r'flutter.*full.*stack',
            r'flutter.*backend',
            r'flutter.*firebase'
        ]
        
        for pattern in flutter_patterns:
            if re.search(pattern, message_lower):
                return True
        
        return False
    
    def send_placement_images(self, to_phone):
        """Send placement image and PDF document to the user"""
        try:
            success_count = 0
            
            # Send introductory message
            intro_message = "📸 Here's everything you need to know about our placement guarantee and job assurance program:"
            self.send_whatsapp_message(to_phone, intro_message)
            
            # Send placement image
            try:
                self.send_media_message(to_phone, self.placement_image['url'], caption=self.placement_image['caption'])
                success_count += 1
                logger.info(f"✅ Sent placement image to {to_phone}")
                
                # Small delay before sending PDF
                import time
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Failed to send placement image to {to_phone}: {e}")
            
            # Send placement PDF as media (better mobile preview)
            try:
                self.send_media_message(to_phone, self.placement_pdf['url'], caption=self.placement_pdf['caption'])
                success_count += 1
                logger.info(f"✅ Sent placement PDF to {to_phone}")
                
            except Exception as e:
                logger.error(f"❌ Failed to send placement PDF to {to_phone}: {e}")
            
            # Send closing message
            closing_message = f"""
💬 wanna dive into more levelx success stories?

"""
            
            self.send_whatsapp_message(to_phone, closing_message)
            
            logger.info(f"📸 Sent {success_count}/2 placement items to {to_phone}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error sending placement materials to {to_phone}: {e}")
            return False
    
    def send_fees_images(self, to_phone):
        """Send all fees structure images to the user"""
        try:
            success_count = 0
            
            # Send introductory message
            intro_message = "💰 Here's our complete fees structure and payment options:"
            self.send_whatsapp_message(to_phone, intro_message)
            
            # Send each fees image with caption
            for i, image_data in enumerate(self.fees_images, 1):
                try:
                    self.send_media_message(to_phone, image_data['url'], caption=image_data['caption'])
                    success_count += 1
                    logger.info(f"✅ Sent fees image {i}/{len(self.fees_images)} to {to_phone}")
                    
                    # Small delay between images to avoid rate limiting
                    import time
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Failed to send fees image {i} to {to_phone}: {e}")
                    continue
            
            # Send closing message
            closing_message = f"""
💬 Have questions about payment plans or scholarships?
📞 Want to speak with our fees counselor? Just ask!

"""
            self.send_whatsapp_message(to_phone, closing_message)
            
            logger.info(f"💰 Sent {success_count}/{len(self.fees_images)} fees images to {to_phone}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error sending fees images to {to_phone}: {e}")
            return False
    
    def send_flutter_reel(self, to_phone):
        """Send Flutter reel to the user"""
        try:
            # Send the reel link with caption
            ok = self.send_whatsapp_message(to_phone, f"{self.flutter_reel['caption']}\n\n{self.flutter_reel['url']}")
            logger.info(f"🚀 Sent Flutter reel to {to_phone}: {ok}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send Flutter reel to {to_phone}: {e}")
            return False
    
    def send_survey_poll(self, to_phone, question_id):
        """Send a survey poll to the user"""
        try:
            poll_data = self.survey_polls.get(question_id)
            if not poll_data:
                logger.error(f"❌ Poll question {question_id} not found")
                return False
            
            # Determine language for the poll
            user_session = self.user_sessions.get(to_phone)
            if user_session and user_session['preferred_language']:
                language = user_session['preferred_language']
            else:
                language = 'english' # Default to English if no language selected
            
            # Create poll message with options
            poll_message = f"📊 {poll_data['question'][language]}\n\n"
            for i, option in enumerate(poll_data['options'][language], 1):
                poll_message += f"{i}. {option}\n"
            
            # Add language-specific instruction for number or exact option text
            if language == 'malayalam':
                poll_message += f"\nനമ്പർ (1-{len(poll_data['options'][language])}) അല്ലെങ്കിൽ ഓപ്ഷൻ ടൈപ്പ് ചെയ്ത് മറുപടി നൽകുക."
            else:
                poll_message += f"\nReply with the number (1-{len(poll_data['options'][language])}) or type the exact option."
            
            # Send the poll
            self.send_whatsapp_message(to_phone, poll_message)
            logger.info(f"📊 Sent survey poll {question_id} ({language}) to {to_phone}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send survey poll {question_id} to {to_phone}: {e}")
            return False
    
    def process_poll_response(self, message_body, user_session):
        """Process poll response and return next question or completion, with custom follow-up messages and special cases"""
        try:
            # Get current survey state first
            current_question = user_session.get('current_survey_question', 'q1')
            poll_data = self.survey_polls.get(current_question)
            
            if not poll_data:
                return {"type": "error", "text": "Survey question not found. Please start over."}
            
            # Determine language for the poll
            if user_session and user_session.get('preferred_language'):
                language = user_session['preferred_language']
            else:
                language = 'english' # Default to English if no language selected
            
            # Try to extract number from the response
            response_number = None
            for word in message_body.split():
                if word.isdigit():
                    response_number = int(word)
                    break
            
            # Determine selected option - either from number or exact text match
            selected_option = None
            
            if response_number and 1 <= response_number <= len(poll_data['options'][language]):
                # Valid numbered response - use predefined option
                selected_option = poll_data['options'][language][response_number - 1]
                logger.info(f"📊 Numbered response ({response_number}): {selected_option}")
            else:
                # Check if the text matches any of the predefined options (case-insensitive)
                user_text = message_body.strip()
                for option in poll_data['options'][language]:
                    if user_text.lower() == option.lower():
                        selected_option = option
                        logger.info(f"📝 Text match response: {selected_option}")
                        break
                
                # If no match found, return error
                if not selected_option:
                    if language == 'malayalam':
                        options_text = ', '.join([f"{i+1}. {opt}" for i, opt in enumerate(poll_data['options'][language])])
                        return {"type": "error", "text": f"ദയവായി നൽകിയിരിക്കുന്ന ഓപ്ഷനുകളിൽ നിന്ന് തിരഞ്ഞെടുക്കുക:\n{options_text}\n\nഅല്ലെങ്കിൽ നമ്പർ ടൈപ്പ് ചെയ്യുക."}
                    else:
                        options_text = ', '.join([f"{i+1}. {opt}" for i, opt in enumerate(poll_data['options'][language])])
                        return {"type": "error", "text": f"Please select from the provided options:\n{options_text}\n\nOr type the option number."}
            user_session['chatbot'].current_lead.survey_answers[current_question] = selected_option
            
            # Prepare follow-up message and next step
            followup = None
            next_q = None
            # Q1 logic
            if current_question == 'q1':
                if selected_option.lower() == 'other' or selected_option.lower().startswith('other'):
                    # Ask to specify
                    followup = "ദയവായി താങ്കളുടെ ജോലി വ്യക്തമാക്കൂ" if language == 'malayalam' else "Could you please specify your current role?"
                    user_session['awaiting_q1_other'] = True
                    return {"type": "followup", "text": followup, "next": None}
                elif user_session.get('awaiting_q1_other'):
                    # User just specified 'other', now proceed
                    user_session['awaiting_q1_other'] = False
                    followup = "വളരെ നല്ലത്! Tech career ആരംഭിക്കാൻ താങ്കൾ ശരിയായ സ്ഥലത്തിലാണ് എത്തിയിരിക്കുന്നത്!" if language == 'malayalam' else "Awesome, you’re at the right place to jumpstart your tech career!"
                else:
                    followup = "വളരെ നല്ലത്! Tech career ആരംഭിക്കാൻ താങ്കൾ ശരിയായ സ്ഥലത്തിലാണ് എത്തിയിരിക്കുന്നത്!" if language == 'malayalam' else "Awesome, you’re at the right place to jumpstart your tech career!"
                user_session['chatbot'].lead_status = LeadStatus.SURVEY_Q2
                user_session['current_survey_question'] = 'q2'
                next_q = 'q2'
            # Q2 logic
            elif current_question == 'q2':
                if selected_option.lower() in ['yes', 'അതെ']:
                    followup = "വളരെ നല്ലത്! നിങ്ങൾക്കിത് പറ്റിയ സ്ഥലമാണ്" if language == 'malayalam' else "Oh great, you’re at the right place!"
                else:
                    followup = "no worries ക്ലാസുകൾ എല്ലാം ആദ്യം മുതൽ ആരംഭിക്കും, അതുകൊണ്ട് നിങ്ങൾക്ക് എളുപ്പം പഠിക്കാം." if language == 'malayalam' else "No worries! Our courses start from zero basics — perfect for you."
                user_session['chatbot'].lead_status = LeadStatus.SURVEY_Q3
                user_session['current_survey_question'] = 'q3'
                next_q = 'q3'
            # Q3 logic
            elif current_question == 'q3':
                followup = "വളരെ നല്ലത്! ഇങ്ങനെ വലിയ ലക്ഷ്യങ്ങൾ ഉണ്ടെങ്കിൽ ജയം ഉറപ്പാണ്." if language == 'malayalam' else "Oh great, it’s good to meet such ambitious people!"
                user_session['chatbot'].lead_status = LeadStatus.SURVEY_Q4
                user_session['current_survey_question'] = 'q4'
                next_q = 'q4'
            # Q4 logic
            elif current_question == 'q4':
                # Map Q4 selection to interest: 1-4 -> selected option text; Not sure -> "our courses"
                is_not_sure = (
                    selected_option.lower().startswith('not sure') or 
                    'ഉറപ്പില്ല' in selected_option or 
                    'തീർച്ചയല്ല' in selected_option
                )
                interest_value = 'our courses' if is_not_sure else selected_option
                try:
                    # Persist interest on the lead for downstream usage (follow-ups, personalization)
                    user_session['chatbot'].current_lead.interest = interest_value
                    # Keep compatibility with any code referencing area_of_interest
                    setattr(user_session['chatbot'].current_lead, 'area_of_interest', interest_value)
                    logger.info(f"🔍 DEBUG: Q4 mapping -> interest set to: {interest_value}")
                except Exception as ie:
                    logger.warning(f"Could not set interest on lead: {ie}")

                if is_not_sure:
                    followup = "താങ്കൾക്കു ഏറ്റവും അനുയോജ്യമായ കോഴ്സ് കണ്ടെത്താൻ ഞങ്ങൾ സഹായിക്കാം." if language == 'malayalam' else "No problem! We’ll help you choose the best fit."
                else:
                    followup = "ആഹാ, കൊള്ളാലോ!" if language == 'malayalam' else "That’s a good choice!"
                logger.info(f"🔍 DEBUG: Q4 completed - Setting survey_completed = True for user")
                user_session['chatbot'].lead_status = LeadStatus.COLLECTING_NAME
                user_session['survey_completed'] = True
                logger.info(f"🔍 DEBUG: Survey completion flag set. Current session survey_completed: {user_session.get('survey_completed')}")
                next_q = 'complete'
            else:
                followup = None
                next_q = None
            return {"type": "followup", "text": followup, "next": next_q}
        except Exception as e:
            logger.error(f"Error processing poll response: {e}")
            return {"type": "error", "text": "Sorry, there was an error processing your response. Please try again."}
    
    def transcribe_audio_whisper(self, audio_file_path):
        """Transcribe audio using OpenAI GPT-4o-Mini-Transcribe (kept name for compatibility)"""
        try:
            with open(audio_file_path, 'rb') as audio_file:
                response = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}"
                    },
                    files={
                        "file": audio_file,
                        "model": (None, "gpt-4o-mini-transcribe"),
                        "language": (None, "en")
                    }
                )
                
                if response.status_code == 200:
                    return response.json().get('text', '')
                else:
                    logger.error(f"Transcribe API error (gpt-4o-mini-transcribe): {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error transcribing with gpt-4o-mini-transcribe: {e}")
            return None
    
    def transcribe_audio_local(self, audio_file_path):
        """Fallback transcription using local speech recognition"""
        try:
            # Convert to WAV format if needed
            audio = AudioSegment.from_file(audio_file_path)
            wav_path = audio_file_path.replace(os.path.splitext(audio_file_path)[1], '.wav')
            audio.export(wav_path, format="wav")
            
            # Transcribe using speech_recognition
            with sr.AudioFile(wav_path) as source:
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio_data)
                
            # Cleanup temporary file
            if os.path.exists(wav_path):
                os.remove(wav_path)
                
            return text
            
        except Exception as e:
            logger.error(f"Error in local transcription: {e}")
            return None
    
    def download_media_file(self, media_id):
        """Backward-compatible wrapper to download media by id (Meta Cloud)."""
        return self.download_media_file_by_id(media_id)
    
    def process_voice_message(self, media_id, from_number):
        """Process voice message: download, transcribe, and get response"""
        try:
            # Download the audio file
            audio_file_path = self.download_media_file_by_id(media_id)
            if not audio_file_path:
                # Prefer user language if session exists
                session = self.user_sessions.get(from_number, {})
                lang = session.get('preferred_language', 'english')
                return (
                    "ക്ഷമിക്കണം, നിങ്ങളുടെ വോയ്സ് മെസേജ് ഡൗൺലോഡ് ചെയ്യാൻ സാധിച്ചില്ല. ദയവായി വീണ്ടും ശ്രമിക്കുക."
                    if lang == 'malayalam' else
                    "Sorry, I couldn't download your voice message. Please try again."
                )
            
            # Try Whisper first, then fallback to local
            transcribed_text = self.transcribe_audio_whisper(audio_file_path)
            if not transcribed_text:
                transcribed_text = self.transcribe_audio_local(audio_file_path)
            
            # Cleanup temporary file
            if os.path.exists(audio_file_path):
                os.remove(audio_file_path)
            
            if transcribed_text:
                logger.info(f"🎤 Transcribed: {transcribed_text}")
                
                # Get user session to check language
                user_session = self.user_sessions.get(from_number)
                if not user_session or not user_session['language_selected']:
                    # Bilingual prompt to keep to English/Malayalam only
                    return (
                        "🎤 നിങ്ങളുടെ വോയ്സ് മെസേജ് ലഭിച്ചു. ദയവായി ആദ്യം ഭാഷ തിരഞ്ഞെടുക്കൂ:\n\n1. English\n2. മലയാളം (Malayalam)\n\n'English' അല്ലെങ്കിൽ 'Malayalam' എന്ന് ടൈപ്പ് ചെയ്യുക."
                    )
                
                # Check if transcribed text is about placement
                if self.detect_placement_intent(transcribed_text):
                    # Send placement images
                    self.send_placement_images(from_number)
                    lang = user_session.get('preferred_language', 'english')
                    if lang == 'malayalam':
                        return f"🎤 നിങ്ങൾ പറഞ്ഞത്: \"{transcribed_text}\"\n\n📸 പ്ലേസ്മെന്റ് സംബന്ധമായ വിശദാംശങ്ങൾ ഞാൻ അയച്ചിരിക്കുന്നു! എന്തെങ്കിലും പ്രത്യേക ചോദ്യങ്ങൾ ഉണ്ടെങ്കിൽ അറിയിക്കൂ."
                    else:
                        return f"🎤 I heard: \"{transcribed_text}\"\n\n📸 I've sent you detailed placement information! Let me know if you have any specific questions."
                # Check if transcribed text is about fees
                elif self.detect_fees_intent(transcribed_text):
                    # Send fees images
                    self.send_fees_images(from_number)
                    lang = user_session.get('preferred_language', 'english')
                    if lang == 'malayalam':
                        return f"🎤 നിങ്ങൾ പറഞ്ഞത്: \"{transcribed_text}\"\n\n💰 ഫീസ് ഘടനയും പേയ്മെന്റ് ഓപ്ഷനുകളും ഞാൻ അയച്ചിരിക്കുന്നു! എന്തെങ്കിലും ചോദ്യങ്ങൾ ഉണ്ടെങ്കിൽ അറിയിക്കൂ."
                    else:
                        return f"🎤 I heard: \"{transcribed_text}\"\n\n💰 I've sent you detailed fees structure and payment options! Let me know if you have any questions."
                # Check if transcribed text is about Flutter
                elif self.detect_flutter_intent(transcribed_text):
                    # Send Flutter reel
                    reel_result = self.send_flutter_reel(from_number)
                    # Process the transcribed text through your chatbot
                    user_chatbot = self.get_user_session(from_number)
                    response = user_chatbot.ask(transcribed_text)
                    
                    # Add note about the reel based on result
                    lang = user_session.get('preferred_language', 'english')
                    if reel_result == "rate_limit":
                        if lang == 'malayalam':
                            return (
                                f"🎤 നിങ്ങൾ പറഞ്ഞത്: \"{transcribed_text}\"\n\n{response}\n\n🚀 ഒരു മികച്ച Flutter ഡെവലപ്‌മെന്റ് റീൽ അയയ്ക്കാൻ ഞാൻ ശ്രമിച്ചു, എന്നാൽ ഇന്ന് ദിവസത്തിലെ മെസേജ് പരിധി എത്തി. നമ്മുടെ Flutter കോഴ്‌സ് കണ്ടെന്റ് ഇവിടെ കാണാം: https://www.instagram.com/reel/DMaOsgOMm0F/?igsh=c3hkd3lyMzYyNmI4"
                            )
                        else:
                            return (
                                f"🎤 I heard: \"{transcribed_text}\"\n\n{response}\n\n🚀 I wanted to send you an amazing Flutter development reel, but I've reached my daily message limit. You can check out our Flutter course content at: https://www.instagram.com/reel/DMaOsgOMm0F/?igsh=c3hkd3lyMzYyNmI4"
                            )
                    else:
                        if lang == 'malayalam':
                            return f"🎤 നിങ്ങൾ പറഞ്ഞത്: \"{transcribed_text}\"\n\n{response}\n\n🚀 ഒരു മികച്ച Flutter ഡെവലപ്‌മെന്റ് റീൽ കൂടി ഞാൻ അയച്ചിട്ടുണ്ട്! നോക്കിക്കോളൂ!"
                        else:
                            return f"🎤 I heard: \"{transcribed_text}\"\n\n{response}\n\n🚀 I've also sent you an amazing Flutter development reel! Check it out!"
                else:
                    # Process the transcribed text through your chatbot
                    user_chatbot = self.get_user_session(from_number)
                    response = user_chatbot.ask(transcribed_text)
                    lang = user_session.get('preferred_language', 'english')
                    if lang == 'malayalam':
                        return f"🎤 നിങ്ങൾ പറഞ്ഞത്: \"{transcribed_text}\"\n\n{response}"
                    else:
                        return f"🎤 I heard: \"{transcribed_text}\"\n\n{response}"
            else:
                session = self.user_sessions.get(from_number, {})
                lang = session.get('preferred_language', 'english')
                return (
                    "ക്ഷമിക്കണം, വോയ്സ് മെസേജ് വ്യക്തമായി മനസ്സിലാക്കാൻ കഴിഞ്ഞില്ല. ദയവായി ടൈപ്പ് ചെയ്ത് അയക്കാമോ അല്ലെങ്കിൽ വീണ്ടും വ്യക്തമായി സംസാരിക്കാമോ?"
                    if lang == 'malayalam' else
                    "Sorry, I couldn't understand your voice message. Could you please type your message or try speaking more clearly?"
                )
                
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            # Use session language if available
            session = self.user_sessions.get(from_number, {})
            lang = session.get('preferred_language', 'english')
            return (
                "ക്ഷമിക്കണം, വോയ്സ് മെസേജ് പ്രോസസ് ചെയ്യുന്നതിനിടെ ഒരു പിശക് സംഭവിച്ചു. ദയവായി വീണ്ടും ശ്രമിക്കുക."
                if lang == 'malayalam' else
                "Sorry, there was an error processing your voice message. Please try again."
            )
    
    def _start_inactivity_checker(self):
        """Start background thread to check for inactive users"""
        def check_inactive_users():
            while True:
                try:
                    self._check_and_notify_inactive_users()
                except Exception as e:
                    logger.error(f"Error in inactivity checker: {e}")
                time.sleep(60)  # Check every 1 minute for precise follow-up timing
        
        # Start the background thread
        thread = threading.Thread(target=check_inactive_users, daemon=True)
        thread.start()
        logger.info("🔍 Inactivity checker started")
    
    def _check_followup_reply(self, session, message_body, phone_number):
        """Check if user replied to a follow-up and mark reply flags"""
        # Only check for survey completed users
        if not session.get('survey_completed', False):
            return
        
        # Check if first follow-up was sent but not yet replied
        if session.get('first_followup_sent', False) and not session.get('first_followup_replied', False):
            # Any non-empty message counts as a reply to first follow-up
            if message_body.strip():
                session['first_followup_replied'] = True
                session['last_activity'] = datetime.now()  # Reset activity timer
                logger.info(f"✅ User replied to first follow-up - extending session timeout to 10 minutes")
                
                # Save follow-up response to Google Sheets
                self._save_followup_response(session, message_body, "first_followup", phone_number)
                return
        
        # Check if second follow-up was sent but not yet replied
        if session.get('second_followup_sent', False) and not session.get('second_followup_replied', False):
            # Any non-empty message counts as a reply to second follow-up
            if message_body.strip():
                session['second_followup_replied'] = True
                session['last_activity'] = datetime.now()  # Reset activity timer
                logger.info(f"✅ User replied to second follow-up - extending session timeout to 10 minutes")
                
                # Save follow-up response to Google Sheets
                self._save_followup_response(session, message_body, "second_followup", phone_number)
                return
    
    def _save_followup_response(self, session, message_body, followup_type, phone_number=None):
        """Save follow-up response to Google Sheets survey sheet"""
        try:
            # Get the chatbot instance from session to access sheets_manager
            chatbot = session.get('chatbot')
            if not chatbot or not hasattr(chatbot, 'sheets_manager') or not chatbot.sheets_manager:
                logger.warning("Google Sheets manager not available for saving follow-up response")
                return False
            
            # Get user name from survey data (preferred method)
            user_name = None
            current_lead = getattr(chatbot, 'current_lead', None)
            if current_lead and hasattr(current_lead, 'name') and current_lead.name:
                user_name = current_lead.name
                logger.info(f"📊 Using user name '{user_name}' for follow-up response saving")
            
            # Format the response with timestamp and type
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_response = f"[{timestamp}] {followup_type}: {message_body.strip()}"
            
            # Try to save by name first, then fallback to phone number
            success = False
            if user_name:
                success = chatbot.sheets_manager.update_survey_followup_response_by_name(user_name, formatted_response)
                if success:
                    logger.info(f"📊 Saved {followup_type} response to survey sheet for user '{user_name}'")
            
            # Fallback to phone number if name method failed
            if not success:
                # Use provided phone number or try to get it from chatbot
                if not phone_number:
                    phone_number = getattr(chatbot, 'phone_number', None)
                    if not phone_number and current_lead and hasattr(current_lead, 'phone'):
                        phone_number = current_lead.phone
                
                if phone_number:
                    success = chatbot.sheets_manager.update_survey_followup_response(phone_number, formatted_response)
                    if success:
                        logger.info(f"📊 Saved {followup_type} response to survey sheet for {phone_number}")
                    else:
                        logger.warning(f"Failed to save {followup_type} response to survey sheet for {phone_number}")
                else:
                    logger.warning("Neither user name nor phone number available for saving follow-up response")
            
            return success
            
        except Exception as e:
            logger.error(f"Error saving follow-up response to Google Sheets: {e}")
            return False
    
    def _compute_interest_score(self, session):
        """Compute an interest score (0-100) based on session engagement and survey progress."""
        try:
            score = 0
            # Language selected indicates initial engagement
            if session.get('language_selected'):
                score += 5
            # Survey progress
            q = str(session.get('current_survey_question', 'q1')).lower()
            if q in ('q2',):
                score += 20
            if q in ('q3',):
                score += 30
            if q in ('q4',):
                score += 40
            if session.get('survey_completed'):
                score += 10
            # Follow-up replies show stronger intent
            if session.get('first_followup_replied'):
                score += 15
            if session.get('second_followup_replied'):
                score += 15
            # Bound score
            score = max(0, min(100, score))
            return int(score)
        except Exception as e:
            logger.error(f"Error computing interest score: {e}")
            return 0

    def _build_interest_summary(self, phone, session):
        """Build a concise interest summary string based on collected data."""
        try:
            parts = []
            lang = session.get('preferred_language', 'english')
            parts.append(f"lang={lang}")
            q = session.get('current_survey_question', 'q1')
            parts.append(f"progress={q}")
            if session.get('survey_completed'):
                parts.append("survey=completed")
            
            # Extract data from the embedded ChatBot state if available
            chatbot = session.get('chatbot')

            # Add user's provided name to the summary when available
            try:
                name = None
                if chatbot and hasattr(chatbot, 'current_lead') and hasattr(chatbot.current_lead, 'name') and chatbot.current_lead.name:
                    name = chatbot.current_lead.name
                if not name:
                    # Fallback to WhatsApp profile name stored in session
                    name = session.get('whatsapp_profile_name') or None
                if name:
                    parts.append(f"name={name}")
            except Exception as ie:
                logger.debug(f"Name extraction failed for {phone}: {ie}")

            # Extract survey answers (area of interest, motivation)
            if chatbot and hasattr(chatbot, 'current_lead') and hasattr(chatbot.current_lead, 'survey_answers'):
                ans = chatbot.current_lead.survey_answers or {}
                aoI = ans.get('q4') or ''
                if aoI:
                    parts.append(f"interest={aoI}")
                # brief view of motivations
                mot = ans.get('q3') or ''
                if mot:
                    parts.append(f"motivation={mot}")
            return "; ".join(parts)
        except Exception as e:
            logger.error(f"Error building interest summary for {phone}: {e}")
            return ""
    
    def _log_interest_to_sheets(self, phone, score, summary):
        """Write interest score and summary into Users sheet via GoogleSheetsManager."""
        try:
            # Access sheets via the session's chatbot (per existing pattern)
            session = self.user_sessions.get(phone, {})
            chatbot = session.get('chatbot') if session else None
            if not chatbot or not hasattr(chatbot, 'sheets_manager') or not chatbot.sheets_manager:
                logger.warning("Google Sheets manager not available; skipping interest logging")
                return False
            ok = chatbot.sheets_manager.update_user_interest(phone, score, summary)
            if ok:
                logger.info(f"📊 Logged interest to users sheet for {phone}: score={score}")
            else:
                logger.warning(f"⚠️ Failed to log interest to users sheet for {phone}")
            return ok
        except Exception as e:
            logger.error(f"Error logging interest to sheets: {e}")
            return False
    
    def _calculate_session_timeout(self, session, inactive_minutes):
        """Calculate session timeout based on follow-up reply status"""
        # Check if user replied to first follow-up
        first_followup_sent = session.get('first_followup_sent', False)
        first_followup_replied = session.get('first_followup_replied', False)
        second_followup_sent = session.get('second_followup_sent', False)
        second_followup_replied = session.get('second_followup_replied', False)
        
        logger.info(f"🔧 TIMEOUT CALC: first_sent={first_followup_sent}, first_replied={first_followup_replied}, second_sent={second_followup_sent}, second_replied={second_followup_replied}")
        
        # If user replied to second follow-up: 10 minutes timeout
        if second_followup_replied:
            return self.reply_timeout_minutes
        
        # If second follow-up was sent but no reply: 6 minutes from second follow-up
        if second_followup_sent and not second_followup_replied:
            second_followup_time = session.get('second_followup_time')
            if second_followup_time:
                minutes_since_second = (datetime.now() - second_followup_time).total_seconds() / 60
                if minutes_since_second >= self.second_followup_timeout_minutes:
                    return inactive_minutes  # Allow timeout
                else:
                    return inactive_minutes + 1  # Prevent timeout for now
        
        # If user replied to first follow-up: 10 minutes timeout
        if first_followup_replied:
            return self.reply_timeout_minutes
        
        # If first follow-up was sent but no reply: allow second follow-up
        if first_followup_sent and not first_followup_replied:
            return self.session_timeout_minutes
        
        # Default timeout
        return self.session_timeout_minutes
    
    def _check_and_notify_inactive_users(self):
        """Check for users who haven't responded and send follow-up"""
        current_time = datetime.now()
        
        for phone, session in list(self.user_sessions.items()):
            try:
                last_activity = session.get('last_activity')
                if not last_activity:
                    continue
                
                inactive_minutes = (current_time - last_activity).total_seconds() / 60
                
                # Skip if session is already marked as ended
                if session.get('session_ended', False):
                    continue
                
                # Get user's preferred language
                language = session.get('preferred_language', 'english')
                
                # Advanced session timeout logic based on follow-up replies+
                timeout_minutes = self._calculate_session_timeout(session, inactive_minutes)
                
                # Debug timeout calculation
                logger.info(f"🔍 DEBUG: Phone {phone} - inactive_minutes: {inactive_minutes:.1f}, timeout_minutes: {timeout_minutes}")
                logger.info(f"🔍 DEBUG: Phone {phone} - first_followup_sent: {session.get('first_followup_sent')}, second_followup_sent: {session.get('second_followup_sent')}")
                
                if inactive_minutes >= timeout_minutes:
                    if session.get('survey_completed', False):
                        logger.info(f"Session ended for {phone} after {timeout_minutes} minutes of inactivity (survey completed)")
                    else:
                        logger.info(f"Session ended for {phone} after {timeout_minutes} minutes of inactivity")
                    # Before ending: compute interest score and summary, and log to Google Sheets
                    try:
                        score = self._compute_interest_score(session)
                        summary = self._build_interest_summary(phone, session)
                        self._log_interest_to_sheets(phone, score, summary)
                    except Exception as e:
                        logger.error(f"❌ Failed to compute/log interest for {phone}: {e}")

                    # Mark session as ended to prevent further follow-ups
                    session['session_ended'] = True
                    self.reset_user_session(phone)
                    continue
                
                # For users who completed the survey
                survey_completed = session.get('survey_completed', False)
                current_survey_q = session.get('current_survey_question', 'q1')
                
                # Safety check: If user reached Q2/Q3/Q4, treat survey as completed for follow-up purposes
                if not survey_completed and str(current_survey_q).lower() in ('q2', 'q3', 'q4'):
                    logger.info(f"🔧 SAFETY FIX: Phone {phone} - User on {str(current_survey_q).upper()}, setting survey_completed = True")
                    session['survey_completed'] = True
                    survey_completed = True
                
                logger.info(f"🔍 DEBUG: Phone {phone} - survey_completed flag: {survey_completed}")
                
                if survey_completed:
                    # Get survey data from chatbot
                    survey_data = session.get('chatbot', {}).current_lead
                    name = getattr(survey_data, 'name', None)
                    area_of_interest = getattr(survey_data, 'interest', 'our courses')
                    
                    # If name not in survey data, try to get from WhatsApp profile
                    if not name:
                        name = session.get('whatsapp_profile_name', 'there')
                    
                    logger.info(f"🔍 DEBUG: Survey completed user {phone} - name: {name}, interest: {area_of_interest}")
                    
                    # First follow-up after 2 minutes
                    if (inactive_minutes >= self.follow_up_minutes and 
                        not session.get('first_followup_sent', False)):
                        
                        # Send first follow-up with survey data
                        message = self.follow_up_messages['survey_complete'][language].format(
                            name=name,
                            interest=area_of_interest
                        )
                        self.send_whatsapp_message(phone, message)
                        session['first_followup_sent'] = True
                        session['first_followup_time'] = current_time
                        session['first_followup_replied'] = False  # Track reply status
                        logger.info(f"📨 Sent first follow-up to survey completer {phone}")
                    
                    # Second follow-up after 4 minutes (2 minutes after first) - ONLY if user didn't reply to first
                    elif (inactive_minutes >= self.second_follow_up_minutes and 
                          session.get('first_followup_sent') and 
                          not session.get('first_followup_replied', False) and 
                          not session.get('second_followup_sent', False)):
                        
                        # Send second follow-up with survey data
                        message = self.follow_up_messages['survey_second_followup'][language].format(
                            name=name,
                            interest=area_of_interest
                        )
                        self.send_whatsapp_message(phone, message)
                        session['second_followup_sent'] = True
                        session['second_followup_time'] = current_time
                        session['second_followup_replied'] = False  # Track reply status
                        logger.info(f"📨 Sent second follow-up to survey completer {phone}")
                
                # For users who didn't complete the survey
                else:
                    logger.info(f"🔍 DEBUG: Phone {phone} - Treating as NON-survey user. survey_completed: {survey_completed}")
                    logger.info(f"🔍 DEBUG: Session data for {phone}: {dict(session)}")
                    
                    # Single follow-up after 2 minutes
                    if (inactive_minutes >= self.follow_up_minutes and 
                        not session.get('follow_up_sent', False)):
                        
                        # Get WhatsApp profile name
                        name = session.get('whatsapp_profile_name', 'there')
                        
                        # Send general follow-up
                        message = self.follow_up_messages['general_followup'][language].format(
                            name=name
                        )
                        self.send_whatsapp_message(phone, message)
                        session['follow_up_sent'] = True
                        logger.info(f"📨 Sent follow-up to non-survey user {phone}")
            
            except Exception as e:
                logger.error(f"Error in inactivity check for {phone}: {e}", exc_info=True)
                continue
    
    def get_user_session(self, phone_number):
        """Get or create user session"""
        if phone_number not in self.user_sessions:
            self.user_sessions[phone_number] = {
                'chatbot': ChatBot(),  # Each user gets their own chatbot instance
                'last_activity': datetime.now(),
                'placement_images_sent': False,  # Track if placement images were sent
                'flutter_reel_sent': False,      # Track if Flutter reel was sent
                'fees_images_sent': False,       # Track if fees images were sent
                'language_selected': False,  # Track if language has been selected
                'preferred_language': None,  # Store preferred language
                'survey_started': False,  # Track if survey has started
                'current_survey_question': 'q1',  # Current survey question
                'survey_completed': False,  # Track if survey is completed
                'awaiting_q1_other': False, # Track if user is awaiting Q1 'Other' response
                'follow_up_sent': False,     # Track if follow-up message was sent
                'second_follow_up_sent': False,     # Track if second follow-up message was sent
                'second_follow_up_schedule': None  # Schedule for second follow-up
            }
        else:
            self.user_sessions[phone_number]['last_activity'] = datetime.now()
        
        return self.user_sessions[phone_number]['chatbot']
    
    def reset_user_session(self, phone_number):
        """Reset user session and chatbot state"""
        if phone_number in self.user_sessions:
            # Preserve survey completion status - once completed, always completed
            survey_completed = self.user_sessions[phone_number].get('survey_completed', False)
            
            # Reset chatbot instance
            self.user_sessions[phone_number]['chatbot'] = ChatBot()
            # Reset all session flags
            self.user_sessions[phone_number].update({
                'last_activity': datetime.now(),
                'placement_images_sent': False,  # Reset placement images flag
                'flutter_reel_sent': False,      # Reset Flutter reel flag
                'fees_images_sent': False,       # Reset fees images flag
                'survey_started': False,
                'survey_completed': survey_completed,  # Preserve survey completion status
                'current_survey_question': 'q1',
                'awaiting_q1_other': False,
                'follow_up_sent': False,  # Reset follow-up flag
                'second_follow_up_sent': False,  # Reset second follow-up flag
                'second_follow_up_schedule': None,  # Reset second follow-up schedule
                # Advanced follow-up tracking flags
                'first_followup_sent': False,
                'first_followup_replied': False,
                'first_followup_time': None,
                'second_followup_sent': False,
                'second_followup_replied': False,
                'second_followup_time': None
            })
            logger.info(f"🔄 Reset session for {phone_number} (survey_completed: {survey_completed})")

    def get_whatsapp_profile_name(self, phone_number, profile_name='', author='', push_name=''):
        """Get WhatsApp profile name from webhook data or return a user-friendly placeholder"""
        try:
            # Try to get the actual WhatsApp profile name from webhook data
            # Priority order: ProfileName > PushName > Author
            actual_name = None
            
            if profile_name and profile_name.strip():
                actual_name = profile_name.strip()
                logger.info(f"✅ Got ProfileName: {actual_name} for {phone_number}")
            elif push_name and push_name.strip():
                actual_name = push_name.strip()
                logger.info(f"✅ Got PushName: {actual_name} for {phone_number}")
            elif author and author.strip():
                actual_name = author.strip()
                logger.info(f"✅ Got Author: {actual_name} for {phone_number}")
            
            if actual_name:
                return actual_name
            else:
                # Fallback to user-friendly placeholder
                logger.info(f"ℹ️ No profile name available for {phone_number}, using placeholder")
                return f"WhatsApp User ({phone_number})"
                
        except Exception as e:
            logger.warning(f"Could not get WhatsApp profile name for {phone_number}: {e}")
            return f"WhatsApp User ({phone_number})"

    def send_whatsapp_message(self, to_phone, message):
        """Send a WhatsApp text message via Meta Cloud API (overrides legacy)."""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "text",
                "text": {"body": message}
            }
            resp = requests.post(self.graph_messages_url, headers=self.graph_headers, json=payload, timeout=30)
            if resp.ok:
                logger.info(f"✅ Message sent to {to_phone}")
                return True
            logger.error(f"❌ Failed to send message: {resp.status_code} {resp.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send message to {to_phone}: {e}")
            return False
            
    def send_media_message(self, to_phone, media_url, caption=None):
        """Send a media message (image/GIF) via Meta Cloud API using public link."""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "image",
                "image": {"link": media_url}
            }
            if caption:
                payload["image"]["caption"] = caption
            resp = requests.post(self.graph_messages_url, headers=self.graph_headers, json=payload, timeout=30)
            if resp.ok:
                logger.info(f"✅ Media message sent to {to_phone}")
                return True
            logger.error(f"❌ Failed to send media: {resp.status_code} {resp.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send media message to {to_phone}: {e}")
            return False
    
    def send_language_selection_buttons(self, to_phone):
        """Send interactive reply buttons for initial language selection (English/Malayalam)."""
        try:
            intro_text = (
                "Welcome to LevelX AI! Please select your preferred language:\n\n"
                "ലെവൽ-X AI-ലേക്ക് സ്വാഗതം! നിങ്ങൾക്ക് ഇഷ്ടമുള്ള ഭാഷ തിരഞ്ഞെടുക്കൂ:"
            )
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": intro_text},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": "LANG_EN", "title": "English"}
                            },
                            {
                                "type": "reply",
                                "reply": {"id": "LANG_ML", "title": "മലയാളം (Malayalam)"}
                            }
                        ]
                    }
                }
            }
            resp = requests.post(self.graph_messages_url, headers=self.graph_headers, json=payload, timeout=30)
            if resp.ok:
                logger.info(f"✅ Sent language selection buttons to {to_phone}")
                return True
            logger.error(f"❌ Failed to send language buttons: {resp.status_code} {resp.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Error sending language selection buttons to {to_phone}: {e}")
            return False
    
    def handle_language_selection(self, phone_number, message):
        """Handle language selection for WhatsApp users"""
        user_session = self.user_sessions.get(phone_number)
        if not user_session:
            return None
            
        message_lower = message.lower().strip()
        
        if any(word in message_lower for word in ['malayalam', 'മലയാളം']):
            user_session['preferred_language'] = 'malayalam'
            user_session['language_selected'] = True
            user_session['chatbot'].preferred_language = 'malayalam'
            user_session['chatbot'].language_selected = True
            
            return ("ഭാഷ മലയാളത്തിലേക്ക് ലോക്ക് ചെയ്തിരിക്കുന്നു.\n\n"
                    "ഭാഷ മാറ്റണമെങ്കിൽ 'switch to english' എന്ന് ടൈപ്പ് ചെയ്യുക.\n\n"
                    "എന്തെങ്കിലും ചോദിക്കാൻ താൽപ്പര്യമുണ്ടോ?")
        elif any(word in message_lower for word in ['english', 'inglish']):
            user_session['preferred_language'] = 'english'
            user_session['language_selected'] = True
            user_session['chatbot'].preferred_language = 'english'
            user_session['chatbot'].language_selected = True
            
            return ("Language locked to English.\n\n"
                    "To switch language, type 'switch to malayalam'.\n\n"
                    "How may I assist you today?")
        
        return None
app = Flask(__name__)
whatsapp_bot = WhatsAppBot()

@app.route('/webhook', methods=['GET'])
def whatsapp_webhook_verify():
    """Meta Webhook verification (works with ngrok URL)"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == whatsapp_bot.whatsapp_verify_token:
        return challenge or '', 200
    return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages from Meta (JSON)"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        logger.debug(f"Incoming webhook: {json.dumps(data)[:500]}")
        entry = (data.get('entry') or [{}])[0]
        changes = (entry.get('changes') or [{}])[0]
        value = changes.get('value', {})
        messages = value.get('messages') or []
        contacts = value.get('contacts') or []
        if not messages:
            return jsonify({'status': 'ignored'}), 200

        msg = messages[0]
        from_number = msg.get('from') or (contacts[0].get('wa_id') if contacts else None)
        message_body = ''
        media_audio_id = None

        if msg.get('type') == 'text':
            message_body = (msg.get('text') or {}).get('body', '')
        elif msg.get('type') == 'audio':
            media_audio_id = (msg.get('audio') or {}).get('id')
        elif msg.get('type') == 'interactive':
            # Handle button/list replies as text
            interactive = msg.get('interactive') or {}
            if interactive.get('type') == 'button_reply':
                message_body = (interactive.get('button_reply') or {}).get('title', '')
            elif interactive.get('type') == 'list_reply':
                message_body = (interactive.get('list_reply') or {}).get('title', '')

        if not from_number:
            return jsonify({'status': 'ignored'}), 200

        # Prepare session
        user_chatbot = whatsapp_bot.get_user_session(from_number)
        user_session = whatsapp_bot.user_sessions[from_number]
        user_chatbot.set_phone_number(from_number)

        # Save to sheets once per user (Meta provides profile name in contacts[0]['profile']['name'])
        if not user_session.get('saved_to_sheets', False):
            profile_name = ((contacts or [{}])[0].get('profile') or {}).get('name', '')
            whatsapp_name = whatsapp_bot.get_whatsapp_profile_name(from_number, profile_name)
            user_chatbot.save_user_to_sheets(whatsapp_name, from_number)
            user_session['saved_to_sheets'] = True

        response_text = None

        # Voice note handling
        if media_audio_id:
            logger.info(f"🎤 Processing voice message from {from_number}")
            response_text = whatsapp_bot.process_voice_message(media_audio_id, from_number)
            if response_text:
                whatsapp_bot.send_whatsapp_message(from_number, response_text)
                return jsonify({'status': 'ok'}), 200

        # Text handling
        message_body = (message_body or '').strip()
        if message_body:
            # Clear session_ended flag when user sends a new message (fresh start)
            if user_session.get('session_ended', False):
                user_session['session_ended'] = False
                logger.info(f"🔄 User {from_number} resumed activity - clearing session_ended flag")

            whatsapp_bot._check_followup_reply(user_session, message_body, from_number)

            if not user_session['language_selected']:
                language_response = whatsapp_bot.handle_language_selection(from_number, message_body)
                if language_response:
                    response_text = language_response
                else:
                    # Send welcome video FIRST to ensure it appears before the text prompt
                    if not user_session.get('welcome_sent', False):
                        whatsapp_bot.send_video_message(from_number, whatsapp_bot.welcome_video, caption="🌟 Welcome to LevelX AI! 🌟")
                        user_session['welcome_sent'] = True
                        # Small delay to help preserve ordering in WhatsApp delivery
                        time.sleep(1)
                    # Then send the language selection interactive buttons
                    whatsapp_bot.send_language_selection_buttons(from_number)
                    response_text = None
            else:
                if message_body.lower() in ['reset', 'restart', 'start over', 'പുനരാരംഭിക്കുക']:
                    whatsapp_bot.reset_user_session(from_number)
                    response_text = "🔄 സെഷൻ പുനരാരംഭിച്ചു! എന്തെങ്കിലും ചോദിക്കാൻ താൽപ്പര്യമുണ്ടോ?" if user_session.get('preferred_language') == 'malayalam' else "🔄 Session reset! How may I assist you today?"
                elif "switch to" in message_body.lower():
                    if "english" in message_body.lower() and user_session['preferred_language'] != 'english':
                        response_text = whatsapp_bot.handle_language_selection(from_number, "english")
                    elif "malayalam" in message_body.lower() and user_session['preferred_language'] != 'malayalam':
                        response_text = whatsapp_bot.handle_language_selection(from_number, "malayalam")
                    else:
                        response_text = "That language is already selected." if user_session['preferred_language'] == 'english' else "ആ ഭാഷ നിലവിൽ തിരഞ്ഞെടുത്തിരിക്കുന്നു."
                elif user_session.get('survey_started') and not user_session.get('survey_completed'):
                    if user_session.get('awaiting_q1_other'):
                        user_session['chatbot'].current_lead.survey_answers['q1'] = message_body.strip()
                        user_session['awaiting_q1_other'] = False
                        lang = user_session.get('preferred_language', 'english')
                        followup = "സൂപ്പർ! Tech career ആരംഭിക്കാൻ താങ്കൾ ശരിയായ സ്ഥലത്തിലാണ് എത്തിയിരിക്കുന്നത്!" if lang == 'malayalam' else "Awesome, you’re at the right place to jumpstart your tech career!"
                        user_session['chatbot'].lead_status = LeadStatus.SURVEY_Q2
                        user_session['current_survey_question'] = 'q2'
                        whatsapp_bot.send_whatsapp_message(from_number, followup)
                        whatsapp_bot.send_survey_poll(from_number, 'q2')
                        response_text = None
                    else:
                        # Process survey response and advance to next poll
                        result = whatsapp_bot.process_poll_response(message_body, user_session)
                        if result.get('type') == 'error':
                            response_text = result.get('text')
                        else:
                            # Send follow-up message if any
                            if result.get('text'):
                                whatsapp_bot.send_whatsapp_message(from_number, result['text'])
                            # Send the next poll if applicable
                            nxt = result.get('next')
                            if nxt in ('q2', 'q3', 'q4'):
                                whatsapp_bot.send_survey_poll(from_number, nxt)
                            elif nxt == 'complete':
                                # Survey completed – gently transition to lead collection (name, then email)
                                lang = user_session.get('preferred_language')
                                if lang == 'malayalam':
                                    thanks = "പർഫക്റ്റ്! 🙌 നിങ്ങളുടെ മറുപടികൾ ലഭിച്ചു."
                                    name_req = "അടുത്തതായി, നിങ്ങളുടെ പൂർണ്ണ പേര് നൽകാമോ?"
                                else:
                                    thanks = "Perfect! 🙌 Got your responses."
                                    name_req = "Next, could you please share your full name?"
                                whatsapp_bot.send_whatsapp_message(from_number, thanks)
                                whatsapp_bot.send_whatsapp_message(from_number, name_req)
                                # Set explicit awaiting flags for lead collection
                                user_session['awaiting_name'] = True
                                user_session['awaiting_email'] = False
                                response_text = None
                                # Avoid any further processing on this same message
                                return jsonify({'status': 'ok'}), 200
                    # Stop further processing while survey is ongoing to avoid extra messages
                    if user_session.get('survey_started') and not user_session.get('survey_completed'):
                        if response_text:
                            whatsapp_bot.send_whatsapp_message(from_number, response_text)
                        return jsonify({'status': 'ok'}), 200
                elif user_session['chatbot'].lead_status in [LeadStatus.COLLECTING_NAME, LeadStatus.COLLECTING_EMAIL] or user_session.get('awaiting_name') or user_session.get('awaiting_email'):
                    # Handle name/email collection exclusively to avoid RAG or other replies
                    lang = user_session.get('preferred_language', 'english')
                    # Name collection
                    if user_session['chatbot'].lead_status == LeadStatus.COLLECTING_NAME or user_session.get('awaiting_name'):
                        user_session['awaiting_name'] = False
                        response_text = user_chatbot.ask(message_body)
                        # If chatbot advanced to email collection, set awaiting flag
                        if user_session['chatbot'].lead_status == LeadStatus.COLLECTING_EMAIL:
                            user_session['awaiting_email'] = True
                        if response_text:
                            whatsapp_bot.send_whatsapp_message(from_number, response_text)
                        return jsonify({'status': 'ok'}), 200
                    # Email collection
                    if user_session['chatbot'].lead_status == LeadStatus.COLLECTING_EMAIL or user_session.get('awaiting_email'):
                        user_session['awaiting_email'] = False
                        response_text = user_chatbot.ask(message_body)
                        if response_text:
                            whatsapp_bot.send_whatsapp_message(from_number, response_text)
                        return jsonify({'status': 'ok'}), 200

                if whatsapp_bot.detect_placement_intent(message_body) and not user_session.get('placement_images_sent', False):
                    if whatsapp_bot.send_placement_images(from_number):
                        user_session['placement_images_sent'] = True
                        response_text = None
                    else:
                        response_text = (
                            "പ്ലേസ്മെന്റ് വിവരങ്ങൾ ലോഡ് ചെയ്യുന്നതിൽ പ്രശ്‌നം നേരിടുന്നു. ദയവായി പിന്നീട് വീണ്ടും ശ്രമിക്കുക."
                            if user_session.get('preferred_language') == 'malayalam' else
                            "I'm having trouble loading the placement information. Please try again later."
                        )
                elif whatsapp_bot.detect_fees_intent(message_body) and not user_session.get('fees_images_sent', False):
                    if whatsapp_bot.send_fees_images(from_number):
                        user_session['fees_images_sent'] = True
                        response_text = None
                    else:
                        response_text = (
                            "ഫീസ് വിവരങ്ങൾ ലോഡ് ചെയ്യുന്നതിൽ പ്രശ്‌നം നേരിടുന്നു. ദയവായി പിന്നീട് വീണ്ടും ശ്രമിക്കുക."
                            if user_session.get('preferred_language') == 'malayalam' else
                            "I'm having trouble loading the fees information. Please try again later."
                        )
                elif whatsapp_bot.detect_flutter_intent(message_body):
                    # Send the Flutter reel only once per session
                    if not user_session.get('flutter_reel_sent', False):
                        if whatsapp_bot.send_flutter_reel(from_number):
                            user_session['flutter_reel_sent'] = True
                        else:
                            response_text = (
                                "ഫ്ലട്ടർ കണ്ടെന്റ് ലോഡ് ചെയ്യുന്നതിൽ പ്രശ്‌നം നേരിടുന്നു. ദയവായി പിന്നീട് വീണ്ടും ശ്രമിക്കുക."
                                if user_session.get('preferred_language') == 'malayalam' else
                                "I'm having trouble loading the Flutter content. Please try again later."
                            )
                    # Always respond via chatbot; do not send the reel again
                    if not response_text:
                        response_text = user_chatbot.ask(message_body)
                else:
                    if user_session.get('survey_completed'):
                        response_text = user_chatbot._invoke_rag_chain_with_language(
                            message_body, user_session.get('preferred_language') or 'english'
                        )['answer']
                    else:
                        response_text = user_chatbot.ask(message_body)
                        if response_text == "SURVEY_START":
                            user_session['survey_started'] = True
                            user_session['current_survey_question'] = 'q1'
                            whatsapp_bot.send_survey_poll(from_number, 'q1')
                            if user_session.get('preferred_language') == 'malayalam':
                                response_text = "oh great! നിങ്ങളുടെ അനുഭവം വ്യക്തിഗതമാക്കാം. നിങ്ങളുടെ background മികച്ചതായി മനസ്സിലാക്കാൻ ഞാൻ നിങ്ങൾക്ക് കുറച്ച് ചോദ്യങ്ങൾ അയയ്ക്കും."
                            else:
                                response_text = "Great! Let's personalize your experience. I'll send you a few quick questions to understand your background better."

        if response_text:
            whatsapp_bot.send_whatsapp_message(from_number, response_text)
        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.error(f"❌ Error in webhook: {e}")
        return jsonify({'error': 'webhook_error'}), 200

@app.route('/status', methods=['GET'])
def status():
    """Health check endpoint"""
    return jsonify({
        'status': 'active',
        'active_sessions': len(getattr(whatsapp_bot, 'user_sessions', {})),
        'placement_features': 'enabled',
        'placement_materials': 2,  # 1 image + 1 PDF
        'total_fees_images': len(getattr(whatsapp_bot, 'fees_images', [])),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/send-message', methods=['POST'])
def send_message():
    """Manual endpoint to send messages (for testing)"""
    try:
        data = request.json
        phone_number = data.get('phone')
        message = data.get('message')
        
        if not phone_number or not message:
            return jsonify({'error': 'Phone number and message are required'}), 400
        
        success = whatsapp_bot.send_whatsapp_message(phone_number, message)
        
        if success:
            return jsonify({'status': 'sent', 'phone': phone_number})
        else:
            return jsonify({'error': 'Failed to send message'}), 500
            
    except Exception as e:
        logger.error(f"Error in send_message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/send-placement-images', methods=['POST'])
def send_placement_images_manual():
    """Manual endpoint to send placement images (for testing)"""
    try:
        data = request.json
        phone_number = data.get('phone')
        
        if not phone_number:
            return jsonify({'error': 'Phone number is required'}), 400
        
        success = whatsapp_bot.send_placement_images(phone_number)
        
        if success:
            return jsonify({'status': 'sent', 'phone': phone_number, 'images_count': len(whatsapp_bot.placement_images)})
        else:
            return jsonify({'error': 'Failed to send placement images'}), 500
            
    except Exception as e:
        logger.error(f"Error in send_placement_images_manual: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/send-fees-images', methods=['POST'])
def send_fees_images_manual():
    """Manual endpoint to send fees images (for testing)"""
    try:
        data = request.json
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({'error': 'Phone number is required'}), 400
        
        success = whatsapp_bot.send_fees_images(phone_number)
        
        if success:
            return jsonify({'status': 'sent', 'phone': phone_number, 'images_count': len(whatsapp_bot.fees_images)})
        else:
            return jsonify({'error': 'Failed to send fees images'}), 500
            
    except Exception as e:
        logger.error(f"Error in send_fees_images_manual: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/send-flutter-reel', methods=['POST'])
def send_flutter_reel_manual():
    """Manual endpoint to send Flutter reel (for testing)"""
    try:
        data = request.json
        phone_number = data.get('phone')
        
        if not phone_number:
            return jsonify({'error': 'Phone number is required'}), 400
        
        success = whatsapp_bot.send_flutter_reel(phone_number)
        
        if success:
            return jsonify({'status': 'sent', 'phone': phone_number, 'reel_url': whatsapp_bot.flutter_reel['url']})
        else:
            return jsonify({'error': 'Failed to send Flutter reel'}), 500
            
    except Exception as e:
        logger.error(f"Error in send_flutter_reel_manual: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Starting LevelX WhatsApp Bot with Placement Images, Flutter Reel & Interactive Polls...")
    print("📱 Bot is ready to receive WhatsApp messages with voice support!")
    print("🎤 Supports both text and voice messages")
    print("📸 Automatically sends placement images for job-related queries")
    print("🚀 Automatically sends Flutter reel for Flutter-related queries")
    print("📊 Interactive survey polls for better user experience")
    print("💼 7 placement images configured for job assurance queries")
    print("💬 Each user gets their own conversation session")
    
    # Run the Flask app
    app.run(
        host='0.0.0.0',  # Allow external connections
        port=5000,
        debug=False  # Set to False in production
    )