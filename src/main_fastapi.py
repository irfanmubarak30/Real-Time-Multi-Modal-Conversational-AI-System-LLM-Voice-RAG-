import os
import json
import logging
import tempfile
import asyncio
import re
import time
from datetime import datetime
from typing import Dict, Any, Optional

import aiohttp
import speech_recognition as sr
from pydub import AudioSegment
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import WhatsAppWebhookData, WebhookResponse, HealthResponse
from levelx import ChatBot, LeadStatus

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
        self.welcome_video = 'https://drive.google.com/uc?export=download&id=1F9qzM1KwVTSYlxMMDt5UmUfslYol9pwH'
        
        # Follow-up message configuration
        self.follow_up_minutes = 2
        self.second_follow_up_minutes = 4
        self.session_timeout_minutes = 8
        self.reply_timeout_minutes = 10
        self.second_followup_timeout_minutes = 6
        
        # Follow-up messages in both languages (now with interactive buttons)
        self.follow_up_messages = {
            'survey_complete': {
                'english': "Hello {name}, did you get admission? If not, there are still limited seats left for {interest}",
                'malayalam': "ഹലോ {name}, നിങ്ങൾക്ക് admission ലഭിച്ചോ? അല്ലെങ്കിൽ, {interest} ക്കായി ഇപ്പോഴും പരിമിതമായ സീറ്റുകൾ മാത്രമേ ലഭ്യമുള്ളൂ"
            },
            'survey_second_followup': {
                'english': "{name}, don't miss this opportunity! Limited seats available for {interest}.",
                'malayalam': "{name}, ഈ അവസരം നഷ്ടപ്പെടുത്തരുത്! {interest} ക്കായി പരിമിതമായ സീറ്റുകൾ മാത്രം."
            },
            'general_followup': {
                'english': "Hi {name}, we noticed you were interested in our courses.",
                'malayalam': "ഹായ് {name}, ഞങ്ങളുടെ കോഴ്സുകളിൽ നിങ്ങൾക്ക് താല്പര്യമുണ്ടെന്ന് ഞങ്ങൾ ശ്രദ്ധിച്ചു."
            }
        }
        
        # Initialize speech recognizer
        self.recognizer = sr.Recognizer()
        
        # Initialize your existing chatbot
        self.chatbot = ChatBot()
        
        # Store user sessions (in production, use Redis or database)
        self.user_sessions = {}
        
        # Placement configuration
        self.placement_image = {
            'url': 'https://drive.google.com/uc?export=download&id=189wzLNXFdN-cgytWf28cnt6Jk-TYZMM5',
            'caption_en': '🎯 100% Placement Guarantee - Our Track Record',
            'caption_ml': '🎯 100% പ്ലേസ്മെന്റ് ഗ്യാരന്റി - ഞങ്ങളുടെ ട്രാക്ക് റെക്കോർഡ്'
        }
        
        self.placement_pdf = {
            'url': 'https://drive.google.com/uc?export=download&id=1wMTYJk0_INBOWDmnw77O32nT-TSyEL3P',
            'caption_en': '📄 thats our Complete Placement Details & Success Stories do you have any specific questions about placements?',
            'caption_ml': '📄 ഇത് ഞങ്ങളുടെ സമ്പൂർണ്ണ പ്ലേസ്മെന്റ് വിശദാംശങ്ങളും വിജയ കഥകളുമാണ്. പ്ലേസ്മെന്റിനെക്കുറിച്ച് നിങ്ങൾക്ക് എന്തെങ്കിലും പ്രത്യേക ചോദ്യങ്ങൾ ഉണ്ടോ?'
        }
        
        
       
        
        # Fees structure images configuration
        self.fees_images = [
            {
                'url': 'https://drive.google.com/uc?export=download&id=18RAmBOEDeSq43KasXN6arsnFqcqT5iLn',
                'caption_en': '💰 LevelX Course Fees Structure - Complete Breakdown',
                'caption_ml': '💰 LevelX കോഴ്സ് ഫീസ് ഘടന - സമ്പൂർണ്ണ വിശദാംശങ്ങൾ'
            },
            {
                'url': 'https://drive.google.com/uc?export=download&id=1HlQCGke4pzgnl93aKdLa-hPbNSgWsqFi', 
                'caption_en': '📊 Flexible Payment Options - EMI Available',
                'caption_ml': '📊 ഫ്ലെക്സിബിൾ പേയ്മെന്റ് ഓപ്ഷനുകൾ - EMI ലഭ്യമാണ്'
            },
            {
                'url': 'https://drive.google.com/uc?export=download&id=1spNDedyHntz-DrEnqCaHTXoS5v7J2lYX', 
                'caption_en': '₹ 10000/- scholarship available for students',
                'caption_ml': '₹ 10000/- സ്കോളർഷിപ്പ് വിദ്യാർത്ഥികൾക്ക് ലഭ്യമാണ്'
            }
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

    async def _graph_post(self, payload):
        """Async version of graph API post"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.graph_messages_url, 
                    headers=self.graph_headers, 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if not resp.ok:
                        text = await resp.text()
                        logger.error(f"Graph API error {resp.status}: {text}")
                    return resp
        except Exception as e:
            logger.error(f"Graph API request failed: {e}")
            return None

    async def send_whatsapp_message(self, to_phone, message):
        """Send a WhatsApp text message via Meta Cloud API (async)"""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "text",
                "text": {"body": message}
            }
            resp = await self._graph_post(payload)
            if resp and resp.ok:
                logger.info(f"✅ Message sent to {to_phone}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send message to {to_phone}: {e}")
            return False

    async def send_media_message(self, to_phone, media_url, caption=None):
        """Send an image/GIF via Meta Cloud API using a public link (async)"""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "image",
                "image": {"link": media_url}
            }
            if caption:
                payload["image"]["caption"] = caption
            resp = await self._graph_post(payload)
            if resp and resp.ok:
                logger.info(f"✅ Media message sent to {to_phone}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send media message to {to_phone}: {e}")
            return False

    async def send_document_message(self, to_phone, document_url, caption=None, filename=None):
        """Send a PDF document via Meta Cloud API using a public link (async)"""
        try:
            if not filename:
                filename = "LevelX_Placement_Details.pdf"
            elif not filename.lower().endswith('.pdf'):
                filename = f"{filename}.pdf"
            
            document_payload = {
                "link": document_url,
                "filename": filename
            }
                
            if caption:
                document_payload["caption"] = caption
                
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "document",
                "document": document_payload
            }
            
            resp = await self._graph_post(payload)
            if resp and resp.ok:
                logger.info(f"✅ PDF document sent to {to_phone} with filename: {filename}")
                return True
            else:
                logger.error(f"❌ PDF send failed: {resp.status if resp else 'No response'}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to send PDF to {to_phone}: {e}")
            return False

    async def send_video_message(self, to_phone, video_url, caption=None):
        """Send a video (MP4) via Meta Cloud API using a public link (async)"""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "video",
                "video": {"link": video_url}
            }
            if caption:
                payload["video"]["caption"] = caption
            resp = await self._graph_post(payload)
            if resp and resp.ok:
                logger.info(f"✅ Video message sent to {to_phone}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send video message to {to_phone}: {e}")
            return False

    def get_user_session(self, phone_number):
        """Get or create user session"""
        if phone_number not in self.user_sessions:
            self.user_sessions[phone_number] = {
                'chatbot': ChatBot(),
                'language_selected': False,
                'preferred_language': None,
                'last_activity': datetime.now(),
                'survey_started': False,
                'survey_completed': False,
                'current_survey_question': None,
                'awaiting_name': False,
                'awaiting_email': False,
                'awaiting_q1_other': False,
                'session_ended': False,
                'welcome_sent': False,
                'saved_to_sheets': False
            }
        else:
            self.user_sessions[phone_number]['last_activity'] = datetime.now()
        
        return self.user_sessions[phone_number]['chatbot']
    
    async def _get_ai_response(self, prompt):
        """Get AI response for intent detection"""
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            
            response = await client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "You are a precise intent classifier. Respond only with YES or NO."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            return "NO"

    async def detect_placement_intent(self, message):
        """AI-based detection for placement/job-related queries"""
        try:
            prompt = f"""Analyze this user message and determine if they are asking about job placement, employment, career opportunities, job guarantee, hiring, salary, or companies that hire students.

IMPORTANT: If the user is declining, rejecting, or saying they don't need placement information, respond with "NO".

User message: "{message}"

Respond with only "YES" if the message is asking for placement/jobs/employment/career information, or "NO" if it's about something else or if they're declining placement information.

Examples:
- "Will I get a job after this course?" -> YES
- "What companies hire from here?" -> YES  
- "ജോലി കിട്ടുമോ?" -> YES
- "I don't need placement details" -> NO
- "No job information needed" -> NO
- "പ്ലേസ്മെന്റ് വേണ്ട" -> NO
- "What is Flutter?" -> NO
- "How much does the course cost?" -> NO

Response:"""
            
            response = await self._get_ai_response(prompt)
            return response.strip().upper() == "YES"
        except Exception as e:
            logger.error(f"Error in AI placement intent detection: {e}")
            # Fallback to basic keyword check
            message_lower = message.lower()
            placement_keywords = ['placement', 'job', 'career', 'hiring', 'salary', 'company', 'ജോലി', 'പ്ലേസ്മെന്റ്']
            return any(keyword in message_lower for keyword in placement_keywords)
    
    async def detect_fees_intent(self, message):
        """AI-based detection for fees/pricing-related queries"""
        try:
            prompt = f"""Analyze this user message and determine if they are asking about course fees, pricing, cost, payment options, EMI, scholarships, or financial aspects.

IMPORTANT: If the user is declining, rejecting, or saying they don't need fees information, respond with "NO".

User message: "{message}"

Respond with only "YES" if the message is asking for fees/cost/payment information, or "NO" if it's about something else or if they're declining fees information.

Examples:
- "How much does the course cost?" -> YES
- "What are the fees?" -> YES
- "ഫീസ് എത്രയാണ്?" -> YES
- "EMI available?" -> YES
- "I don't need fees details" -> NO
- "No fees information needed" -> NO
- "ഫീസ് വേണ്ട" -> NO
- "What is Flutter?" -> NO
- "Will I get a job?" -> NO

Response:"""
            
            response = await self._get_ai_response(prompt)
            return response.strip().upper() == "YES"
        except Exception as e:
            logger.error(f"Error in AI fees intent detection: {e}")
            # Fallback to basic keyword check
            message_lower = message.lower()
            fees_keywords = ['fees', 'cost', 'price', 'payment', 'emi', 'scholarship', 'ഫീസ്', 'പൈസ', 'പണം', 'ചിലവ്']
            return any(keyword in message_lower for keyword in fees_keywords)
    
    async def detect_flutter_intent(self, message):
        """AI-based detection for Flutter-related queries"""
        try:
            prompt = f"""Analyze this user message and determine if they are asking about Flutter development, mobile app development, cross-platform development, or Flutter-related topics.

IMPORTANT: If the user is declining, rejecting, or saying they don't need Flutter information, respond with "NO".

User message: "{message}"

Respond with only "YES" if the message is asking for Flutter/mobile development information, or "NO" if it's about something else or if they're declining Flutter information.

Examples:
- "What is Flutter?" -> YES
- "Mobile app development" -> YES
- "ഫ്ലട്ടർ എന്താണ്?" -> YES
- "Cross-platform development" -> YES
- "I don't need Flutter details" -> NO
- "No Flutter information needed" -> NO
- "ഫ്ലട്ടർ വേണ്ട" -> NO
- "What are the fees?" -> NO
- "Will I get a job?" -> NO

Response:"""
            
            response = await self._get_ai_response(prompt)
            return response.strip().upper() == "YES"
        except Exception as e:
            logger.error(f"Error in AI Flutter intent detection: {e}")
            # Fallback to basic keyword check
            message_lower = message.lower()
            flutter_keywords = ['flutter', 'ഫ്ലട്ടർ', 'mobile app', 'app development']
            return any(keyword in message_lower for keyword in flutter_keywords)

    async def send_placement_images(self, to_phone):
        """Send placement guarantee images and PDF to the user (async)"""
        try:
            success_count = 0
            
            # Get user language preference
            session = self.user_sessions.get(to_phone, {})
            lang = session.get('preferred_language', 'english')
            
            # Send introductory message
            if lang == 'malayalam':
                intro_message = "📸 ഞങ്ങളുടെ പ്ലേസ്മെന്റ് ഗ്യാരന്റിയെക്കുറിച്ചും ജോബ് അഷ്വറൻസ് പ്രോഗ്രാമിനെക്കുറിച്ചും അറിയേണ്ടതെല്ലാം ഇവിടെയുണ്ട്:"
            else:
                intro_message = "📸 Here's everything you need to know about our placement guarantee and job assurance program:"
            await self.send_whatsapp_message(to_phone, intro_message)
            
            # Send placement image
            try:
                caption = self.placement_image['caption_ml'] if lang == 'malayalam' else self.placement_image['caption_en']
                await self.send_media_message(to_phone, self.placement_image['url'], caption=caption)
                success_count += 1
                logger.info(f"✅ Sent placement image to {to_phone}")
                
                # Small delay before sending PDF
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Failed to send placement image to {to_phone}: {e}")
            
            # Send placement PDF as document
            try:
                caption = self.placement_pdf['caption_ml'] if lang == 'malayalam' else self.placement_pdf['caption_en']
                await self.send_document_message(to_phone, self.placement_pdf['url'], caption=caption)
                success_count += 1
                logger.info(f"✅ Sent placement PDF to {to_phone}")
                
            except Exception as e:
                logger.error(f"❌ Failed to send placement PDF to {to_phone}: {e}")
            
            logger.info(f"🎯 Sent {success_count}/2 placement materials to {to_phone}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error sending placement materials to {to_phone}: {e}")
            return False

    async def send_fees_images(self, to_phone):
        """Send all fees structure images to the user (async)"""
        try:
            success_count = 0
            
            # Get user language preference
            session = self.user_sessions.get(to_phone, {})
            lang = session.get('preferred_language', 'english')
            
            # Send introductory message
            if lang == 'malayalam':
                intro_message = "💰 ഇവിടെ ഞങ്ങളുടെ സമ്പൂർണ്ണ ഫീസ് ഘടനയും പേയ്മെന്റ് ഓപ്ഷനുകളുമുണ്ട്:"
            else:
                intro_message = "💰 Here's our complete fees structure and payment options:"
            await self.send_whatsapp_message(to_phone, intro_message)
            
            # Send each fees image with caption
            for i, image_data in enumerate(self.fees_images, 1):
                try:
                    caption = image_data['caption_ml'] if lang == 'malayalam' else image_data['caption_en']
                    await self.send_media_message(to_phone, image_data['url'], caption=caption)
                    success_count += 1
                    logger.info(f"✅ Sent fees image {i}/{len(self.fees_images)} to {to_phone}")
                    
                    # Small delay between images to avoid rate limiting
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Failed to send fees image {i} to {to_phone}: {e}")
            
            # Send closing message
            if lang == 'malayalam':
                closing_message = f"""
💬 പേയ്മെന്റ് പ്ലാനുകളെക്കുറിച്ചോ സ്കോളർഷിപ്പുകളെക്കുറിച്ചോ ചോദ്യങ്ങളുണ്ടോ?
📞 ഞങ്ങളുടെ ഫീസ് കൗൺസിലറുമായി സംസാരിക്കാൻ ആഗ്രഹിക്കുന്നുണ്ടോ? ചോദിക്കൂ!

"""
            else:
                closing_message = f"""
💬 Have questions about payment plans or scholarships?
📞 Want to speak with our fees counselor? Just ask!

"""
            await self.send_whatsapp_message(to_phone, closing_message)
            
            logger.info(f"💰 Sent {success_count}/{len(self.fees_images)} fees images to {to_phone}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error sending fees images to {to_phone}: {e}")
            return False

    async def send_flutter_reel(self, to_phone):
        """Send Flutter reel to the user with preview (async)"""
        try:
            # Send Instagram reel as media message to show preview
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "text",
                "text": {
                    "body": f"{self.flutter_reel['caption']}\n\n{self.flutter_reel['url']}",
                    "preview_url": True
                }
            }
            
            resp = await self._graph_post(payload)
            if resp and resp.ok:
                logger.info(f"🚀 Sent Flutter reel with preview to {to_phone}")
                return True
            else:
                logger.error(f"❌ Failed to send Flutter reel with preview to {to_phone}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Failed to send Flutter reel to {to_phone}: {e}")
            return False

    async def send_survey_poll(self, to_phone, question_id):
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
            await self.send_whatsapp_message(to_phone, poll_message)
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
            # Map Malayalam answers to English for database storage
            english_answer = selected_option
            if language == 'malayalam':
                malayalam_to_english = {
                    # Q1 mappings
                    'Student': 'Student',
                    'Working Professional': 'Working Professional', 
                    'Other': 'Other',
                    # Q2 mappings
                    'അതെ': 'Yes',
                    'അല്ല': 'No',
                    # Q3 mappings
                    'ഉയർന്ന സാലറി': 'Higher Salary',
                    'കരിയർ മാറ്റം': 'Career Change',
                    'ഫ്രീലാൻസിംഗ്': 'Freelancing',
                    'മറ്റുള്ളവ': 'Other',
                    # Q4 mappings
                    '1-3 മാസം': '1-3 months',
                    '3-6 മാസം': '3-6 months', 
                    '6+ മാസം': '6+ months',
                    'ഉടനെ': 'Immediately'
                }
                english_answer = malayalam_to_english.get(selected_option, selected_option)
            
            user_session['chatbot'].current_lead.survey_answers[current_question] = english_answer
            
            # Prepare follow-up message and next step
            followup = None
            next_q = None
            # Q1 logic
            if current_question == 'q1':
                # All options (including "Other") proceed to Q2 without additional input
                followup = "വളരെ നല്ലത്! Tech career ആരംഭിക്കാൻ താങ്കൾ ശരിയായ സ്ഥലത്തിലാണ് എത്തിയിരിക്കുന്നത്!" if language == 'malayalam' else "Awesome, you're at the right place to jumpstart your tech career!"
                user_session['chatbot'].lead_status = LeadStatus.SURVEY_Q2
                user_session['current_survey_question'] = 'q2'
                next_q = 'q2'
            # Q2 logic
            elif current_question == 'q2':
                if selected_option.lower() in ['yes', 'അതെ']:
                    followup = "വളരെ നല്ലത്! നിങ്ങൾക്കിത് പറ്റിയ സ്ഥലമാണ്" if language == 'malayalam' else "Oh great, you're at the right place!"
                else:
                    followup = "no worries ക്ലാസുകൾ എല്ലാം ആദ്യം മുതൽ ആരംഭിക്കും, അതുകൊണ്ട് നിങ്ങൾക്ക് എളുപ്പം പഠിക്കാം." if language == 'malayalam' else "No worries! Our courses start from zero basics — perfect for you."
                user_session['chatbot'].lead_status = LeadStatus.SURVEY_Q3
                user_session['current_survey_question'] = 'q3'
                next_q = 'q3'
            # Q3 logic
            elif current_question == 'q3':
                followup = "വളരെ നല്ലത്! ഇങ്ങനെ വലിയ ലക്ഷ്യങ്ങൾ ഉണ്ടെങ്കിൽ ജയം ഉറപ്പാണ്." if language == 'malayalam' else "Oh great, it's good to meet such ambitious people!"
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
                    followup = "താങ്കൾക്കു ഏറ്റവും അനുയോജ്യമായ കോഴ്സ് കണ്ടെത്താൻ ഞങ്ങൾ സഹായിക്കാം." if language == 'malayalam' else "No problem! We'll help you choose the best fit."
                else:
                    followup = "ആഹാ, കൊള്ളാലോ!" if language == 'malayalam' else "That's a good choice!"
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

    async def send_exclusive_offer_buttons(self, to_phone, language='english'):
        """Send interactive reply buttons for exclusive offer with header image."""
        try:
            if language == 'malayalam':
                body_text = "\n\n🎯 **പ്രത്യേക ഓഫർ!** 🎯\n\nനിങ്ങൾക്ക് LevelX AI-ന്റെ വ്യക്തിഗത പതിപ്പ് വേണമോ? നിങ്ങളുടെ പ്രത്യേക ലക്ഷ്യങ്ങളും പശ്ചാത്തലവും അടിസ്ഥാനമാക്കി 4 ചോദ്യങ്ങളുള്ള ഒരു ക്വിക്ക് സർവേ വഴി ഒരു ഇഷ്ടാനുസൃത പഠന പാത സൃഷ്ടിക്കാം.\n\nഈ വ്യക്തിഗത അനുഭവത്തിൽ നിങ്ങൾക്ക് താൽപ്പര്യമുണ്ടോ? (അതെ/ഇല്ല)"
                yes_text = "അതെ"
                no_text = "ഇല്ല"
            else:
                body_text = "\n\n🎯 **Exclusive Offer!** 🎯\n\nWould you like a personalized version of LevelX AI? I can create a customized learning path based on your specific goals and background through a quick 4-question survey.\n\nWould you be interested in this personalized experience? (Yes/No)"
                yes_text = "Yes"
                no_text = "No"

            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "header": {
                        "type": "image",
                        "image": {
                            "link": "https://drive.google.com/uc?id=1wbHMZUWRnngSBERMaSCF-_KKc_6Ee2oD"
                        }
                    },
                    "body": {"text": body_text},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "exclusive_offer_yes",
                                    "title": yes_text
                                }
                            },
                            {
                                "type": "reply", 
                                "reply": {
                                    "id": "exclusive_offer_no",
                                    "title": no_text
                                }
                            }
                        ]
                    }
                }
            }

            response = await self._graph_post(payload)
            if response and response.ok:
                logger.info(f"✅ Exclusive offer buttons sent to {to_phone}")
                return True
            else:
                logger.error(f"❌ Failed to send exclusive offer buttons to {to_phone}")
                return False

        except Exception as e:
            logger.error(f"Error sending exclusive offer buttons: {e}")
            return False

    async def send_survey_first_followup_buttons(self, to_phone, name, interest, language='english'):
        """Send interactive buttons for survey user first follow-up."""
        try:
            if language == 'malayalam':
                body_text = f"ഹലോ {name}, നിങ്ങൾക്ക് admission ലഭിച്ചോ? അല്ലെങ്കിൽ, {interest} ക്കായി ഇപ്പോഴും പരിമിതമായ സീറ്റുകൾ മാത്രമേ ലഭ്യമുള്ളൂ"
                button1_text = "Admission details"
                button2_text = "Already Admitted"
            else:
                body_text = f"Hello {name}, did you get admission? If not, there are still limited seats left for {interest}"
                button1_text = "Admission Details"
                button2_text = "Already Admitted"

            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body_text},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "survey_first_admission_details",
                                    "title": button1_text
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "survey_first_already_admitted",
                                    "title": button2_text
                                }
                            }
                        ]
                    }
                }
            }

            response = await self._graph_post(payload)
            if response and response.ok:
                logger.info(f"✅ Survey first follow-up buttons sent to {to_phone}")
                return True
            else:
                logger.error(f"❌ Failed to send survey first follow-up buttons to {to_phone}")
                return False

        except Exception as e:
            logger.error(f"Error sending survey first follow-up buttons: {e}")
            return False

    async def send_survey_second_followup_buttons(self, to_phone, name, interest, language='english'):
        """Send interactive buttons for survey user second follow-up."""
        try:
            if language == 'malayalam':
                body_text = f"{name}, ഈ അവസരം നഷ്ടപ്പെടുത്തരുത്! {interest} ക്കായി പരിമിതമായ സീറ്റുകൾ മാത്രം."
                button1_text = "Admission details"
                button2_text = "Not Intrested"
            else:
                body_text = f"{name}, don't miss this opportunity! Limited seats available for {interest}."
                button1_text = "Admission Details"
                button2_text = "Not Interested"

            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body_text},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "survey_second_admission_details",
                                    "title": button1_text
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "survey_second_not_interested",
                                    "title": button2_text
                                }
                            }
                        ]
                    }
                }
            }

            response = await self._graph_post(payload)
            if response and response.ok:
                logger.info(f"✅ Survey second follow-up buttons sent to {to_phone}")
                return True
            else:
                logger.error(f"❌ Failed to send survey second follow-up buttons to {to_phone}")
                return False

        except Exception as e:
            logger.error(f"Error sending survey second follow-up buttons: {e}")
            return False

    async def send_general_followup_buttons(self, to_phone, name, language='english'):
        """Send interactive buttons for non-survey user follow-up."""
        try:
            if language == 'malayalam':
                body_text = f"ഹായ് {name}, ഞങ്ങളുടെ കോഴ്സുകളിൽ നിങ്ങൾക്ക് താല്പര്യമുണ്ടെന്ന് ഞങ്ങൾ ശ്രദ്ധിച്ചു."
                button1_text = "course details"
                button2_text = "Not intrested"
            else:
                body_text = f"Hi {name}, we noticed you were interested in our courses."
                button1_text = "course details"
                button2_text = "Not Interested"

            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body_text},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "general_followup_interested",
                                    "title": button1_text
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "general_followup_not_interested",
                                    "title": button2_text
                                }
                            }
                        ]
                    }
                }
            }

            response = await self._graph_post(payload)
            if response and response.ok:
                logger.info(f"✅ General follow-up buttons sent to {to_phone}")
                return True
            else:
                logger.error(f"❌ Failed to send general follow-up buttons to {to_phone}")
                return False

        except Exception as e:
            logger.error(f"Error sending general follow-up buttons: {e}")
            return False

    async def send_language_selection_buttons(self, to_phone):
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
            async with aiohttp.ClientSession() as session:
                async with session.post(self.graph_messages_url, headers=self.graph_headers, json=payload, timeout=30) as resp:
                    if resp.ok:
                        logger.info(f"✅ Sent language selection buttons to {to_phone}")
                        return True
                    error_text = await resp.text()
                    logger.error(f"❌ Failed to send language buttons: {resp.status} {error_text}")
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

    async def _graph_post(self, payload):
        """Make async POST request to WhatsApp Graph API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.graph_messages_url, headers=self.graph_headers, json=payload, timeout=30) as resp:
                    if not resp.ok:
                        error_text = await resp.text()
                        logger.error(f"Graph API error {resp.status}: {error_text}")
                    return resp
        except Exception as e:
            logger.error(f"Graph API request failed: {e}")
            return None

    async def send_document_message(self, to_phone, document_url, caption=None, filename=None):
        """Send a PDF document via Meta Cloud API using a public link"""
        try:
            # Ensure filename has .pdf extension for proper preview
            if not filename:
                filename = "LevelX_Placement_Details.pdf"
            elif not filename.lower().endswith('.pdf'):
                filename = f"{filename}.pdf"
            
            # Build document payload with proper structure
            document_payload = {
                "link": document_url,
                "filename": filename
            }
            
            # Build main payload
            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "document",
                "document": document_payload
            }
            
            # Add caption separately at root level if provided
            if caption:
                payload["document"]["caption"] = caption
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.graph_messages_url, headers=self.graph_headers, json=payload, timeout=30) as resp:
                    if resp.ok:
                        logger.info(f"✅ PDF document sent to {to_phone} with filename: {filename}")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"❌ PDF send failed: {resp.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"❌ Failed to send PDF to {to_phone}: {e}")
            return False

    async def send_video_message(self, to_phone, video_url, caption=None):
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
            resp = await self._graph_post(payload)
            if resp and resp.ok:
                logger.info(f"✅ Video message sent to {to_phone}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send video message to {to_phone}: {e}")
            return False

    async def download_media_file_by_id(self, media_id: str) -> str | None:
        """Download media by Meta media_id and return local temp file path."""
        try:
            info_url = f"{self.graph_api_base}/{media_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(info_url, headers={"Authorization": f"Bearer {self.whatsapp_access_token}"}, timeout=30) as info_resp:
                    if not info_resp.ok:
                        error_text = await info_resp.text()
                        logger.error(f"Failed to fetch media info: {info_resp.status} {error_text}")
                        return None
                    info_data = await info_resp.json()
                    media_url = info_data.get("url")
                    if not media_url:
                        logger.error("Media URL missing in info response")
                        return None

                async with session.get(media_url, headers={"Authorization": f"Bearer {self.whatsapp_access_token}"}, timeout=60) as bin_resp:
                    if not bin_resp.ok:
                        error_text = await bin_resp.text()
                        logger.error(f"Failed to download media: {bin_resp.status} {error_text}")
                        return None

                    ctype = bin_resp.headers.get('Content-Type', '')
                    suffix = '.ogg' if 'ogg' in ctype else '.mp4' if 'mp4' in ctype else '.bin'
                    tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    content = await bin_resp.read()
                    tmpf.write(content)
                    tmpf.close()
                    return tmpf.name
        except Exception as e:
            logger.error(f"Error downloading media by id: {e}")
            return None

    async def transcribe_audio_whisper(self, audio_file_path):
        """Transcribe audio using OpenAI GPT-4o-Mini-Transcribe (async version)"""
        try:
            async with aiohttp.ClientSession() as session:
                with open(audio_file_path, 'rb') as audio_file:
                    data = aiohttp.FormData()
                    data.add_field('file', audio_file, filename='audio.ogg')
                    data.add_field('model', 'gpt-4o-transcribe')
                    data.add_field('language', 'en')
                    
                    async with session.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.openai_api_key}"},
                        data=data
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            return result.get('text', '')
                        else:
                            error_text = await response.text()
                            logger.error(f"Transcribe API error (gpt-4o-mini-transcribe): {response.status} - {error_text}")
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

    async def process_voice_message(self, media_id, from_number):
        """Process voice message: download, transcribe, and get response (async version)"""
        try:
            # Download the audio file
            audio_file_path = await self.download_media_file_by_id(media_id)
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
            transcribed_text = await self.transcribe_audio_whisper(audio_file_path)
            if not transcribed_text:
                transcribed_text = self.transcribe_audio_local(audio_file_path)
            
            # Cleanup temporary file
            if os.path.exists(audio_file_path):
                os.remove(audio_file_path)
            
            if transcribed_text:
                logger.info(f"🎤 Transcribed: {transcribed_text}")
                
                # Get user session to check language
                user_session = self.user_sessions.get(from_number)
                if not user_session or not user_session.get('language_selected'):
                    # Bilingual prompt to keep to English/Malayalam only
                    return (
                        "🎤 നിങ്ങളുടെ വോയ്സ് മെസേജ് ലഭിച്ചു. ദയവായി ആദ്യം ഭാഷ തിരഞ്ഞെടുക്കൂ:\n\n1. English\n2. മലയാളം (Malayalam)\n\n'English' അല്ലെങ്കിൽ 'Malayalam' എന്ന് ടൈപ്പ് ചെയ്യുക."
                    )
                
                # Check if transcribed text is about placement
                if await self.detect_placement_intent(transcribed_text):
                    # Send placement images
                    await self.send_placement_images(from_number)
                    lang = user_session.get('preferred_language', 'english')
                    if lang == 'malayalam':
                        return f"🎤 നിങ്ങൾ പറഞ്ഞത്: \"{transcribed_text}\"\n\n📸 പ്ലേസ്മെന്റ് സംബന്ധമായ വിശദാംശങ്ങൾ ഞാൻ അയച്ചിരിക്കുന്നു! എന്തെങ്കിലും പ്രത്യേക ചോദ്യങ്ങൾ ഉണ്ടെങ്കിൽ അറിയിക്കൂ."
                    else:
                        return f"🎤 I heard: \"{transcribed_text}\"\n\n📸 I've sent you detailed placement information! Let me know if you have any specific questions."
                # Check if transcribed text is about fees
                elif await self.detect_fees_intent(transcribed_text):
                    # Send fees images
                    await self.send_fees_images(from_number)
                    lang = user_session.get('preferred_language', 'english')
                    if lang == 'malayalam':
                        return f"🎤 നിങ്ങൾ പറഞ്ഞത്: \"{transcribed_text}\"\n\n💰 ഫീസ് ഘടനയും പേയ്മെന്റ് ഓപ്ഷനുകളും ഞാൻ അയച്ചിരിക്കുന്നു! എന്തെങ്കിലും ചോദ്യങ്ങൾ ഉണ്ടെങ്കിൽ അറിയിക്കൂ."
                    else:
                        return f"🎤 I heard: \"{transcribed_text}\"\n\n💰 I've sent you detailed fees structure and payment options! Let me know if you have any questions."
                # Check if transcribed text is about Flutter
                elif await self.detect_flutter_intent(transcribed_text):
                    # Send Flutter reel
                    reel_result = await self.send_flutter_reel(from_number)
                    # Process the transcribed text through your chatbot
                    user_chatbot = self.get_user_session(from_number)
                    response = await user_chatbot.ask_async(transcribed_text)
                    
                    # Check if response contains exclusive offer signal
                    if "|SEND_EXCLUSIVE_OFFER|" in response:
                        # Split response and exclusive offer
                        main_response = response.replace("|SEND_EXCLUSIVE_OFFER|", "")
                        
                        # Send exclusive offer as interactive buttons
                        lang = user_session.get('preferred_language', 'english')
                        await self.send_exclusive_offer_buttons(from_number, lang)
                        response = main_response
                    
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
                    response = await user_chatbot.ask_async(transcribed_text)
                    
                    # Check if response contains exclusive offer signal
                    if "|SEND_EXCLUSIVE_OFFER|" in response:
                        # Split response and exclusive offer
                        main_response = response.replace("|SEND_EXCLUSIVE_OFFER|", "")
                        
                        # Send exclusive offer as interactive buttons
                        lang = user_session.get('preferred_language', 'english')
                        await self.send_exclusive_offer_buttons(from_number, lang)
                        response = main_response
                    
                    lang = user_session.get('preferred_language', 'english')
                    if lang == 'malayalam':
                        return f"🎤 നിങ്ങൾ പറഞ്ഞത്: \"{transcribed_text}\"\n\n{response}"
                    else:
                        return f"🎤 I heard: \"{transcribed_text}\"\n\n{response}"
            else:
                session = self.user_sessions.get(from_number, {})
                lang = session.get('preferred_language', 'english')
                return (
                    "ക്ഷമിക്കണം, നിങ്ങളുടെ വോയ്സ് മെസേജ് മനസ്സിലാക്കാൻ സാധിച്ചില്ല. ദയവായി വീണ്ടും ശ്രമിക്കുക."
                    if lang == 'malayalam' else
                    "Sorry, I couldn't understand your voice message. Please try again."
                )
                
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            session = self.user_sessions.get(from_number, {})
            lang = session.get('preferred_language', 'english')
            return (
                "വോയ്സ് മെസേജ് പ്രോസസ്സ് ചെയ്യുന്നതിൽ പ്രശ്‌നം നേരിട്ടു. ദയവായി വീണ്ടും ശ്രമിക്കുക."
                if lang == 'malayalam' else
                "There was an error processing your voice message. Please try again."
            )

    def _check_followup_reply(self, session, message_body, phone_number):
        """Check if user replied to a follow-up and mark reply flags"""
        # Handle both survey-completed and non-survey users
        is_survey_user = session.get('survey_completed', False)
        
        # Check if first follow-up was sent but not yet replied
        # For survey users: check 'first_followup_sent', for non-survey: check 'follow_up_sent'
        first_followup_sent = session.get('first_followup_sent', False) if is_survey_user else session.get('follow_up_sent', False)
        first_followup_replied = session.get('first_followup_replied', False) if is_survey_user else session.get('follow_up_replied', False)
        
        if first_followup_sent and not first_followup_replied:
            # Any non-empty message counts as a reply to first follow-up
            if message_body.strip():
                if is_survey_user:
                    session['first_followup_replied'] = True
                    logger.info(f"✅ Survey user replied to first follow-up - extending session timeout to 10 minutes")
                else:
                    session['follow_up_replied'] = True
                    logger.info(f"✅ Non-survey user replied to follow-up")
                
                session['last_activity'] = datetime.now()  # Reset activity timer
                
                # Save follow-up response to Google Sheets (works for both user types)
                followup_type = "first_followup" if is_survey_user else "general_followup"
                self._save_followup_response(session, message_body, followup_type, phone_number)
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
            logger.info(f"🔄 Attempting to save {followup_type} response: '{message_body}' for {phone_number}")
            
            # Get the chatbot instance from session to access sheets_manager
            chatbot = session.get('chatbot')
            if not chatbot or not hasattr(chatbot, 'sheets_manager') or not chatbot.sheets_manager:
                logger.warning("❌ Google Sheets manager not available for saving follow-up response")
                return False
            
            logger.info("✅ Google Sheets manager found")
            
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
                logger.info(f"🔄 Trying to save by name: '{user_name}'")
                success = chatbot.sheets_manager.update_survey_followup_response_by_name(user_name, formatted_response)
                if success:
                    logger.info(f"✅ Saved {followup_type} response to survey sheet for user '{user_name}'")
                else:
                    logger.warning(f"❌ Failed to save by name for '{user_name}'")
            
            # Fallback to phone number if name method failed
            if not success:
                # Use provided phone number or try to get it from chatbot
                if not phone_number:
                    phone_number = getattr(chatbot, 'phone_number', None)
                    if not phone_number and current_lead and hasattr(current_lead, 'phone'):
                        phone_number = current_lead.phone
                
                if phone_number:
                    logger.info(f"🔄 Trying to save by phone: '{phone_number}'")
                    success = chatbot.sheets_manager.update_survey_followup_response(phone_number, formatted_response)
                    if success:
                        logger.info(f"✅ Saved {followup_type} response to survey sheet for {phone_number}")
                    else:
                        logger.warning(f"❌ Failed to save {followup_type} response to survey sheet for {phone_number}")
                else:
                    logger.warning("❌ Neither user name nor phone number available for saving follow-up response")
            
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
                score += 10
            # Survey progress
            q = str(session.get('current_survey_question', 'q1')).lower()
            if q in ('q2',):
                score += 5
            if q in ('q3',):
                score += 10
            if q in ('q4',):
                score += 15
            if session.get('survey_completed'):
                score += 20
            # Follow-up replies show stronger intent
            if session.get('first_followup_replied'):
                score += 10
            if session.get('second_followup_replied'):
                score += 5
            # Bound score
            score = max(0, min(100, score))
            return int(score)
        except Exception as e:
            logger.error(f"Error computing interest score: {e}")
            return 0

    def _build_interest_summary(self, phone, session):
        """Build a simplified interest summary with name, survey completion, and follow-up status"""
        try:
            chatbot = session.get('chatbot')
            if not chatbot:
                return "No session data available"
            
            # Build summary components
            summary_parts = []
            
            # Get user name
            name = None
            lead_data = getattr(chatbot, 'current_lead', None)
            if lead_data and hasattr(lead_data, 'name') and lead_data.name:
                name = lead_data.name
            if not name:
                name = session.get('whatsapp_profile_name', 'Unknown')
            summary_parts.append(f"name={name}")
            
            # Survey completion status
            survey_completed = session.get('survey_completed', False)
            summary_parts.append(f"survey_completed={survey_completed}")
            
            # Follow-up reply status
            first_followup_replied = session.get('first_followup_replied', False)
            second_followup_replied = session.get('second_followup_replied', False)
            summary_parts.append(f"first_followup_replied={first_followup_replied}")
            summary_parts.append(f"second_followup_replied={second_followup_replied}")
            
            return "; ".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Error building interest summary for {phone}: {e}")
            return "name=Unknown; survey_completed=False; first_followup_replied=False; second_followup_replied=False"

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

    async def _generate_chat_summary_and_score(self, session):
        """Generate AI-powered chat summary and engagement score using OpenAI"""
        try:
            chatbot = session.get('chatbot')
            if not chatbot:
                return {"summary": "No chatbot instance available", "score": 0}
            
            # Check for RAG chain memory first
            if hasattr(chatbot, 'rag_chain') and hasattr(chatbot.rag_chain, 'memory'):
                memory = chatbot.rag_chain.memory
            elif hasattr(chatbot, 'memory'):
                memory = chatbot.memory
            else:
                return {"summary": "No chat memory available", "score": 0}
            
            # Extract chat history from memory
            chat_history = []
            if hasattr(memory, 'chat_memory') and hasattr(memory.chat_memory, 'messages'):
                for message in memory.chat_memory.messages:
                    if hasattr(message, 'content'):
                        role = "User" if message.__class__.__name__ == "HumanMessage" else "Bot"
                        chat_history.append(f"{role}: {message.content}")
            
            if not chat_history:
                return {"summary": "No meaningful chat interactions found", "score": 0}
            
            # Limit to last 10 exchanges to avoid token limits
            recent_chat = chat_history[-20:] if len(chat_history) > 20 else chat_history
            chat_text = "\n".join(recent_chat)
            
            # Create analysis prompt with scoring
            analysis_prompt = f"""Analyze this WhatsApp chat conversation and provide:

1. A brief 2-3 sentence summary focusing on:
   - User's main interests and questions
   - Key topics discussed
   - User's intent or goals
   - Any concerns or objections raised

2. An engagement score from 0-50 based on:
   - Quality of questions asked (0-15 points)
   - Depth of conversation (0-15 points) 
   - Interest level shown (0-10 points)
   - Response quality and engagement (0-10 points)

Chat History:
{chat_text}

Respond in this exact format:
SUMMARY: [your 2-3 sentence summary]
SCORE: [number from 0-50]"""

            # Use OpenAI to analyze the chat
            openai_api_key = os.getenv('OPENAI_API_KEY')
            if not openai_api_key:
                return {"summary": "Chat analysis unavailable - no API key", "score": 0}
            
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {openai_api_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': 'gpt-4o-mini',
                        'messages': [
                            {'role': 'system', 'content': 'You are an expert at analyzing customer conversations to extract insights and score engagement levels. Always respond in the exact format requested.'},
                            {'role': 'user', 'content': analysis_prompt}
                        ],
                        'temperature': 0.3
                    }
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        ai_response = result['choices'][0]['message']['content'].strip()
                        
                        # Parse the response
                        summary = "Chat analysis completed"
                        score = 0
                        
                        lines = ai_response.split('\n')
                        for line in lines:
                            if line.startswith('SUMMARY:'):
                                summary = line.replace('SUMMARY:', '').strip()
                            elif line.startswith('SCORE:'):
                                try:
                                    score = int(line.replace('SCORE:', '').strip())
                                    score = max(0, min(50, score))  # Bound between 0-50
                                except:
                                    score = 0
                        
                        return {"summary": summary, "score": score}
                    else:
                        error_text = await response.text()
                        logger.error(f"OpenAI API error: {response.status} - {error_text}")
                        return {"summary": "Chat analysis unavailable - API error", "score": 0}
                        
        except Exception as e:
            logger.error(f"Error generating chat summary: {e}")
            return {"summary": "Chat analysis failed", "score": 0}

    def _log_interest_to_sheets(self, phone, score, summary):
        """Write interest score and summary into Users sheet via GoogleSheetsManager."""
        try:
            # Access sheets via the session's chatbot (per existing pattern)
            if phone in self.user_sessions:
                chatbot = self.user_sessions[phone]['chatbot']
                if hasattr(chatbot, 'sheets_manager') and chatbot.sheets_manager:
                    chatbot.sheets_manager.update_user_interest(phone, score, summary)
                    logger.info(f"✅ Logged interest score {score} for {phone}: {summary[:100]}...")
                    return True
                else:
                    logger.warning(f"⚠️ No sheets_manager available for {phone}")
            else:
                logger.warning(f"⚠️ No session found for {phone}")
            return False
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

    def _start_inactivity_checker(self):
        """Start background thread to check for inactive users"""
        def check_inactive_users():
            while True:
                try:
                    asyncio.run(self._check_and_notify_inactive_users())
                except Exception as e:
                    logger.error(f"Error in inactivity checker: {e}")
                time.sleep(60)  # Check every 5 minutes
        
        # Start the background thread
        import threading
        thread = threading.Thread(target=check_inactive_users, daemon=True)
        thread.start()
        logger.info("🔍 Inactivity checker started")

    async def _check_and_notify_inactive_users(self):
        """Check for users who haven't responded and send follow-up"""
        current_time = datetime.now()
        
        for phone, session in list(self.user_sessions.items()):
            try:
                last_activity = session.get('last_activity')
                if not last_activity:
                    continue
                
                inactive_minutes = (current_time - last_activity).total_seconds() / 60
                
                # Skip if session is already marked as ended or conversation ended
                if session.get('session_ended', False) or session.get('conversation_ended', False):
                    continue
                
                # Get user's preferred language
                language = session.get('preferred_language', 'english')
                
                # Ensure language is not None
                if language is None:
                    language = 'english'
                
                # Advanced session timeout logic based on follow-up replies
                timeout_minutes = self._calculate_session_timeout(session, inactive_minutes)
                
                # Debug timeout calculation
                logger.info(f"🔍 DEBUG: Phone {phone} - inactive_minutes: {inactive_minutes:.1f}, timeout_minutes: {timeout_minutes}")
                logger.info(f"🔍 DEBUG: Phone {phone} - first_followup_sent: {session.get('first_followup_sent')}, second_followup_sent: {session.get('second_followup_sent')}")
                
                if inactive_minutes >= timeout_minutes:
                    if session.get('survey_completed', False):
                        logger.info(f"Session ended for {phone} after {timeout_minutes} minutes of inactivity (survey completed)")
                    else:
                        logger.info(f"Session ended for {phone} after {timeout_minutes} minutes of inactivity")
                    
                    # Before ending: compute interest score, chat summary, and log to Google Sheets
                    try:
                        engagement_score = self._compute_interest_score(session)
                        interest_summary = self._build_interest_summary(phone, session)
                        chat_analysis = await self._generate_chat_summary_and_score(session)
                        
                        # Combine engagement score (0-50) + AI chat score (0-50) = final score (0-100)
                        final_score = engagement_score + chat_analysis["score"]
                        combined_summary = f"Interest: {interest_summary} | Chat Analysis: {chat_analysis['summary']}"
                        
                        logger.info(f"📊 Final interest score for {phone}: Engagement={engagement_score} + AI={chat_analysis['score']} = {final_score}")
                        self._log_interest_to_sheets(phone, final_score, combined_summary)
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
                        
                        # Send first follow-up with interactive buttons
                        await self.send_survey_first_followup_buttons(phone, name, area_of_interest, language)
                        session['first_followup_sent'] = True
                        session['first_followup_time'] = current_time
                        session['first_followup_replied'] = False  # Track reply status
                        logger.info(f"📨 Sent first follow-up buttons to survey completer {phone}")
                    
                    # Second follow-up after 4 minutes (2 minutes after first) - ONLY if user didn't reply to first
                    elif (inactive_minutes >= self.second_follow_up_minutes and 
                          session.get('first_followup_sent') and 
                          not session.get('first_followup_replied', False) and 
                          not session.get('second_followup_sent', False)):
                        
                        # Send second follow-up with interactive buttons
                        await self.send_survey_second_followup_buttons(phone, name, area_of_interest, language)
                        session['second_followup_sent'] = True
                        session['second_followup_time'] = current_time
                        session['second_followup_replied'] = False  # Track reply status
                        logger.info(f"📨 Sent second follow-up buttons to survey completer {phone}")
                
                # For users who didn't complete the survey
                else:
                    logger.info(f"🔍 DEBUG: Phone {phone} - Treating as NON-survey user. survey_completed: {survey_completed}")
                    
                    # Single follow-up after 2 minutes
                    if (inactive_minutes >= self.follow_up_minutes and 
                        not session.get('follow_up_sent', False)):
                        
                        # Get user name from chatbot lead data or WhatsApp profile
                        name = 'there'
                        try:
                            # First try to get name from chatbot lead data
                            if 'chatbot' in session and hasattr(session['chatbot'], 'current_lead') and session['chatbot'].current_lead.name:
                                name = session['chatbot'].current_lead.name
                            # Fallback to WhatsApp profile name
                            elif session.get('whatsapp_profile_name'):
                                name = session.get('whatsapp_profile_name')
                        except Exception as e:
                            logger.warning(f"Error getting name for {phone}: {e}")
                            name = session.get('whatsapp_profile_name', 'there')
                        
                        # Send general follow-up with interactive buttons
                        await self.send_general_followup_buttons(phone, name, language)
                        session['follow_up_sent'] = True
                        logger.info(f"📨 Sent follow-up buttons to non-survey user {phone}")
                    
                    # Check if non-survey user should have session ended (after follow-up timeout)
                    elif (session.get('follow_up_sent', False) and 
                          inactive_minutes >= (self.follow_up_minutes + self.session_timeout_minutes)):
                        
                        logger.info(f"Session ended for non-survey user {phone} after {inactive_minutes:.1f} minutes of inactivity")
                        
                        # Calculate interest score for non-survey users using same method as survey users
                        try:
                            user_chatbot = session.get('chatbot')
                            if user_chatbot and hasattr(user_chatbot, 'current_lead'):
                                user_chatbot.end_session_with_analysis()
                                logger.info(f"💾 Saved interest score for non-survey user {phone} using chatbot method")
                            else:
                                logger.warning(f"⚠️ No chatbot or current_lead found for non-survey user {phone}")
                        except Exception as e:
                            logger.error(f"❌ Failed to compute/log interest for non-survey user {phone}: {e}")
                        
                        # Mark session as ended and reset
                        session['session_ended'] = True
                        self.reset_user_session(phone)
                        continue
            
            except Exception as e:
                logger.error(f"Error in inactivity check for {phone}: {e}", exc_info=True)
                continue

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
                return
        
        # Check if second follow-up was sent but not yet replied
        if session.get('second_followup_sent', False) and not session.get('second_followup_replied', False):
            # Any non-empty message counts as a reply to second follow-up
            if message_body.strip():
                session['second_followup_replied'] = True
                session['last_activity'] = datetime.now()  # Reset activity timer
                logger.info(f"✅ User replied to second follow-up - extending session timeout to 10 minutes")
                return

    def reset_user_session(self, phone_number):
        """Reset user session and chatbot state"""
        if phone_number in self.user_sessions:
            # Preserve survey completion status - once completed, always completed
            survey_completed = self.user_sessions[phone_number].get('survey_completed', False)
            # Preserve welcome_sent flag to prevent duplicate welcome messages
            welcome_sent = self.user_sessions[phone_number].get('welcome_sent', False)
            
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
                'welcome_sent': welcome_sent,  # Preserve welcome_sent flag
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

# Initialize FastAPI app
app = FastAPI(
    title="LevelX WhatsApp Bot API",
    description="WhatsApp bot for LevelX AI Assistant with survey functionality",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Initialize WhatsApp bot
whatsapp_bot = WhatsAppBot()

@app.get("/webhook")
async def whatsapp_webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"), 
    hub_challenge: str = Query(alias="hub.challenge")
):
    """Meta Webhook verification endpoint"""
    if hub_mode == 'subscribe' and hub_verify_token == whatsapp_bot.whatsapp_verify_token:
        return PlainTextResponse(content=hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Forbidden")

@app.post("/webhook")
async def whatsapp_webhook(
    webhook_data: WhatsAppWebhookData,
    background_tasks: BackgroundTasks
):
    """Handle incoming WhatsApp messages from Meta"""
    try:
        logger.debug(f"Incoming webhook: {webhook_data.json()[:500]}")
        
        if not webhook_data.entry:
            return WebhookResponse(status="ignored")
            
        entry = webhook_data.entry[0]
        if not entry.changes:
            return WebhookResponse(status="ignored")
            
        change = entry.changes[0]
        value = change.value
        
        messages = value.messages or []
        contacts = value.contacts or []
        
        if not messages:
            return WebhookResponse(status="ignored")

        msg = messages[0]
        from_number = msg.from_ or (contacts[0].wa_id if contacts else None)
        message_body = ''
        media_audio_id = None

        if msg.type == 'text' and msg.text:
            message_body = msg.text.body
        elif msg.type == 'audio' and msg.audio:
            media_audio_id = msg.audio.id
        elif msg.type == 'interactive' and msg.interactive:
            interactive = msg.interactive
            if interactive and interactive.type == 'button_reply' and interactive.button_reply:
                button_id = interactive.button_reply.id
                message_body = interactive.button_reply.title or ''
                
                logger.info(f"🔘 Button clicked: {button_id} by {from_number}")
                
                # Handle exclusive offer button responses
                if button_id == 'exclusive_offer_yes':
                    message_body = 'Yes'
                    # Set wants_personalized flag for survey users
                    user_session = whatsapp_bot.user_sessions.get(from_number, {})
                    user_chatbot = user_session.get('chatbot')
                    if user_chatbot and hasattr(user_chatbot, 'current_lead'):
                        user_chatbot.current_lead.wants_personalized = True
                elif button_id == 'exclusive_offer_no':
                    message_body = 'No'
                    # Set wants_personalized flag to False for non-survey users
                    user_session = whatsapp_bot.user_sessions.get(from_number, {})
                    user_chatbot = user_session.get('chatbot')
                    if user_chatbot and hasattr(user_chatbot, 'current_lead'):
                        user_chatbot.current_lead.wants_personalized = False
                
                # Handle survey first follow-up button responses
                elif button_id == 'survey_first_admission_details':
                    message_body = 'Admission Details'
                    # Mark as replied to first follow-up and save to survey sheet
                    user_session = whatsapp_bot.user_sessions.get(from_number, {})
                    user_session['first_followup_replied'] = True
                    # Save to survey sheet followup column
                    try:
                        user_chatbot = user_session.get('chatbot')
                        if user_chatbot and hasattr(user_chatbot, 'sheets_manager'):
                            user_chatbot.sheets_manager.update_survey_followup_response(from_number, 'Admission Details')
                            logger.info(f"📝 Saved survey first follow-up response to sheets: {from_number} - Admission Details")
                        else:
                            logger.warning(f"❌ No sheets manager available for {from_number}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save survey first follow-up response: {e}")
                elif button_id == 'survey_first_already_admitted':
                    message_body = 'Already Admitted'
                    # Mark as replied to first follow-up and save to survey sheet
                    user_session = whatsapp_bot.user_sessions.get(from_number, {})
                    user_session['first_followup_replied'] = True
                    # Save to survey sheet followup column
                    try:
                        user_chatbot = user_session.get('chatbot')
                        if user_chatbot and hasattr(user_chatbot, 'sheets_manager'):
                            user_chatbot.sheets_manager.update_survey_followup_response(from_number, 'Already Admitted')
                            logger.info(f"📝 Saved survey first follow-up response to sheets: {from_number} - Already Admitted")
                        else:
                            logger.warning(f"❌ No sheets manager available for {from_number}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save survey first follow-up response: {e}")
                    
                    # Send thank you message and reset session
                    language = user_session.get('language', 'english')
                    if language == 'malayalam':
                        thank_you_msg = "നന്ദി! നിങ്ങൾക്ക് admission കിട്ടിയതിൽ സന്തോഷം. ഭാവിയിൽ എന്തെങ്കിലും സഹായം വേണമെങ്കിൽ ബന്ധപ്പെടാം!"
                    else:
                        thank_you_msg = "Thank you! Congratulations on getting admission. Feel free to reach out if you need any help in the future!"
                    
                    # Send thank you message and reset session in background
                    background_tasks.add_task(
                        send_thank_you_and_reset_session,
                        from_number,
                        thank_you_msg
                    )
                
                # Handle survey second follow-up button responses
                elif button_id == 'survey_second_admission_details':
                    message_body = 'Admission Details'
                    # Mark as replied to second follow-up and save to survey sheet
                    user_session = whatsapp_bot.user_sessions.get(from_number, {})
                    user_session['second_followup_replied'] = True
                    # Save to survey sheet followup column (same column as first followup)
                    try:
                        user_chatbot = user_session.get('chatbot')
                        if user_chatbot and hasattr(user_chatbot, 'sheets_manager'):
                            user_chatbot.sheets_manager.update_survey_followup_response(from_number, 'Admission Details (2nd)')
                            logger.info(f"📝 Saved survey second follow-up response to sheets: {from_number} - Admission Details (2nd)")
                        else:
                            logger.warning(f"❌ No sheets manager available for {from_number}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save survey second follow-up response: {e}")
                elif button_id == 'survey_second_not_interested':
                    message_body = 'Not Interested'
                    # Mark as replied to second follow-up and save to survey sheet
                    user_session = whatsapp_bot.user_sessions.get(from_number, {})
                    user_session['second_followup_replied'] = True
                    # Save to survey sheet followup column (same column as first followup)
                    try:
                        user_chatbot = user_session.get('chatbot')
                        if user_chatbot and hasattr(user_chatbot, 'sheets_manager'):
                            user_chatbot.sheets_manager.update_survey_followup_response(from_number, 'Not Interested (2nd)')
                            logger.info(f"📝 Saved survey second follow-up response to sheets: {from_number} - Not Interested (2nd)")
                        else:
                            logger.warning(f"❌ No sheets manager available for {from_number}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save survey second follow-up response: {e}")
                    
                    # Send thank you message and reset session
                    language = user_session.get('language', 'english')
                    if language == 'malayalam':
                        thank_you_msg = "നന്ദി! നിങ്ങളുടെ സമയത്തിന് നന്ദി. ഭാവിയിൽ എന്തെങ്കിലും സഹായം വേണമെങ്കിൽ ബന്ധപ്പെടാം!"
                    else:
                        thank_you_msg = "Thank you for your time! Feel free to reach out after 2 minutes if you need any help in the future!"
                    
                    # Send thank you message and reset session in background
                    background_tasks.add_task(
                        send_thank_you_and_reset_session,
                        from_number,
                        thank_you_msg
                    )
                
                # Handle general follow-up button responses (non-survey users)
                elif button_id == 'general_followup_interested':
                    message_body = 'course details'
                    # Mark as replied to follow-up and save to users sheet
                    user_session = whatsapp_bot.user_sessions.get(from_number, {})
                    user_session['follow_up_replied'] = True
                    # Save to users sheet followup_response column
                    try:
                        user_chatbot = user_session.get('chatbot')
                        if user_chatbot and hasattr(user_chatbot, 'sheets_manager'):
                            user_chatbot.sheets_manager.update_followup_response(from_number, 'course details')
                            logger.info(f"📝 Saved non-survey follow-up response to sheets: {from_number} - course details")
                        else:
                            logger.warning(f"❌ No sheets manager available for {from_number}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save non-survey follow-up response: {e}")
                elif button_id == 'general_followup_not_interested':
                    message_body = 'Not Interested'
                    logger.info(f"🔘 Processing general_followup_not_interested button for {from_number}")
                    # Mark as replied to follow-up and save to users sheet
                    user_session = whatsapp_bot.user_sessions.get(from_number, {})
                    user_session['follow_up_replied'] = True
                    logger.info(f"🔘 Marked follow_up_replied = True for {from_number}")
                    
                    # Add button response to conversation memory for proper analysis
                    user_chatbot = user_session.get('chatbot')
                    if user_chatbot:
                        user_chatbot.memory.chat_memory.add_user_message('Not Interested')
                        user_chatbot.memory.chat_memory.add_ai_message('Thank you for your response.')
                    
                    # Save to users sheet followup_response column
                    try:
                        if user_chatbot and hasattr(user_chatbot, 'sheets_manager'):
                            user_chatbot.sheets_manager.update_followup_response(from_number, 'Not Interested')
                            logger.info(f"📝 Saved non-survey follow-up response to sheets: {from_number} - Not Interested")
                        else:
                            logger.warning(f"❌ No sheets manager available for {from_number}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save non-survey follow-up response: {e}")
                    
                    # Send thank you message and reset session
                    language = user_session.get('language', 'english')
                    if language == 'malayalam':
                        thank_you_msg = "നന്ദി! നിങ്ങളുടെ സമയത്തിന് നന്ദി. ഭാവിയിൽ എന്തെങ്കിലും സഹായം വേണമെങ്കിൽ ബന്ധപ്പെടാം!"
                    else:
                        thank_you_msg = "Thank you for your time! Feel free to reach out after 2 minutes if you need any help in the future!"
                    
                    # Send thank you message and reset session in background
                    background_tasks.add_task(
                        send_thank_you_and_reset_session,
                        from_number,
                        thank_you_msg
                    )
                    
            elif interactive.type == 'list_reply' and interactive.list_reply:
                message_body = interactive.list_reply.title or ''

        if not from_number:
            return WebhookResponse(status="ignored")

        # Process the message in background for better performance
        background_tasks.add_task(
            process_whatsapp_message,
            from_number,
            message_body,
            media_audio_id,
            contacts
        )
        
        return WebhookResponse(status="ok")
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return WebhookResponse(status="error", message=str(e))

async def send_thank_you_and_reset_session(phone_number: str, thank_you_message: str):
    """Send thank you message and reset user session"""
    try:
        # Save interest score and summary before resetting session
        user_session = whatsapp_bot.user_sessions.get(phone_number, {})
        user_chatbot = user_session.get('chatbot')
        if user_chatbot and hasattr(user_chatbot, 'current_lead'):
            # Calculate and save interest score before reset using the chatbot's method
            user_chatbot.end_session_with_analysis()
            logger.info(f"💾 Saved interest score for {phone_number} before session reset")
        
        # Send thank you message
        await whatsapp_bot.send_whatsapp_message(phone_number, thank_you_message)
        logger.info(f"📨 Sent thank you message to {phone_number}")
        
        # Mark user as completed/not interested to prevent further AI responses
        if phone_number in whatsapp_bot.user_sessions:
            whatsapp_bot.user_sessions[phone_number]['conversation_ended'] = True
            whatsapp_bot.user_sessions[phone_number]['end_reason'] = 'user_not_interested'
            whatsapp_bot.user_sessions[phone_number]['conversation_end_time'] = datetime.now()
            logger.info(f"🚫 Marked conversation as ended for {phone_number}")
        
        # Reset session but preserve conversation_ended and welcome_sent flags
        if phone_number in whatsapp_bot.user_sessions:
            conversation_ended = whatsapp_bot.user_sessions[phone_number].get('conversation_ended', False)
            end_reason = whatsapp_bot.user_sessions[phone_number].get('end_reason', '')
            conversation_end_time = whatsapp_bot.user_sessions[phone_number].get('conversation_end_time', None)
            welcome_sent = whatsapp_bot.user_sessions[phone_number].get('welcome_sent', False)
            whatsapp_bot.reset_user_session(phone_number)
            # Restore conversation_ended and welcome_sent flags
            whatsapp_bot.user_sessions[phone_number]['conversation_ended'] = conversation_ended
            whatsapp_bot.user_sessions[phone_number]['end_reason'] = end_reason
            whatsapp_bot.user_sessions[phone_number]['conversation_end_time'] = conversation_end_time
            whatsapp_bot.user_sessions[phone_number]['welcome_sent'] = welcome_sent
        logger.info(f"🔄 Reset session for {phone_number}")
        
    except Exception as e:
        logger.error(f"❌ Error sending thank you and resetting session for {phone_number}: {e}")

async def process_whatsapp_message(
    from_number: str,
    message_body: str,
    media_audio_id: str = None,
    contacts: list = None
):
    """Process WhatsApp message in background"""
    try:
        # Prepare session
        user_chatbot = whatsapp_bot.get_user_session(from_number)
        user_session = whatsapp_bot.user_sessions[from_number]
        user_chatbot.set_phone_number(from_number)

        # Check if conversation has ended (user clicked "Not Interested" or "Already Admitted")
        if user_session.get('conversation_ended', False):
            conversation_end_time = user_session.get('conversation_end_time')
            if conversation_end_time:
                # Allow re-engagement after 2 minutes
                time_since_end = (datetime.now() - conversation_end_time).total_seconds() / 60
                if time_since_end >= 2:
                    # Reset conversation ended status to allow re-engagement
                    user_session['conversation_ended'] = False
                    user_session['end_reason'] = None
                    user_session['conversation_end_time'] = None
                    # Reset welcome_sent to allow proper welcome flow for re-engaging users
                    user_session['welcome_sent'] = False
                    user_session['language_selected'] = False
                    user_session['preferred_language'] = None
                    logger.info(f"🔄 Re-engagement allowed for {from_number} after {time_since_end:.1f} minutes - reset welcome and language flags")
                else:
                    logger.info(f"🚫 Ignoring message from {from_number} - conversation ended ({user_session.get('end_reason', 'unknown')}) - {2 - time_since_end:.1f} minutes remaining for re-engagement")
                    return
            else:
                logger.info(f"🚫 Ignoring message from {from_number} - conversation ended ({user_session.get('end_reason', 'unknown')})")
                return

        # Save to sheets once per user
        if not user_session.get('saved_to_sheets', False):
            profile_name = ''
            if contacts and len(contacts) > 0 and contacts[0].profile:
                profile_name = contacts[0].profile.name or ''
            whatsapp_name = whatsapp_bot.get_whatsapp_profile_name(from_number, profile_name)
            user_chatbot.save_user_to_sheets(whatsapp_name, from_number)
            user_session['saved_to_sheets'] = True

        response_text = None

        # Voice note handling
        if media_audio_id:
            logger.info(f"🎤 Processing voice message from {from_number}")
            response_text = await whatsapp_bot.process_voice_message(media_audio_id, from_number)
            if response_text:
                await whatsapp_bot.send_whatsapp_message(from_number, response_text)
                return

        # Text handling
        message_body = (message_body or '').strip()
        if message_body:
            # Clear session_ended flag when user sends a new message
            if user_session.get('session_ended', False):
                user_session['session_ended'] = False
                logger.info(f"🔄 User {from_number} resumed activity - clearing session_ended flag")

            # Check for follow-up replies
            whatsapp_bot._check_followup_reply(user_session, message_body, from_number)

            if not user_session['language_selected']:
                language_response = whatsapp_bot.handle_language_selection(from_number, message_body)
                if language_response:
                    response_text = language_response
                else:
                    # Send welcome video FIRST to ensure it appears before the text prompt
                    if not user_session.get('welcome_sent', False):
                        await whatsapp_bot.send_video_message(from_number, whatsapp_bot.welcome_video, caption="🌟 Welcome to LevelX AI! 🌟")
                        user_session['welcome_sent'] = True
                        # Small delay to help preserve ordering in WhatsApp delivery
                        await asyncio.sleep(1)
                    # Then send the language selection interactive buttons
                    await whatsapp_bot.send_language_selection_buttons(from_number)
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
                    # Handle survey responses
                    poll_result = whatsapp_bot.process_poll_response(message_body, user_session)
                    if poll_result['type'] == 'followup':
                        if poll_result['text']:
                            await whatsapp_bot.send_whatsapp_message(from_number, poll_result['text'])
                        if poll_result['next'] and poll_result['next'] != 'complete':
                            await whatsapp_bot.send_survey_poll(from_number, poll_result['next'])
                        elif poll_result['next'] == 'complete':
                            # Survey completed – gently transition to lead collection (name, then email)
                            lang = user_session.get('preferred_language')
                            if lang == 'malayalam':
                                thanks = "പർഫക്റ്റ്! 🙌 നിങ്ങളുടെ മറുപടികൾ ലഭിച്ചു."
                                name_req = "അടുത്തതായി, നിങ്ങളുടെ FULL NAME  നൽകാമോ?(TYPE IN ENGLISH)"
                            else:
                                thanks = "Perfect! 🙌 Got your responses."
                                name_req = "Next, could you please share your full name?"
                            await whatsapp_bot.send_whatsapp_message(from_number, thanks)
                            await whatsapp_bot.send_whatsapp_message(from_number, name_req)
                            # Set explicit awaiting flags for lead collection
                            user_session['awaiting_name'] = True
                            user_session['awaiting_email'] = False
                        response_text = None
                    elif poll_result['type'] == 'error':
                        response_text = poll_result['text']
                    
                    # Stop further processing while survey is ongoing to avoid RAG interference
                    if user_session.get('survey_started') and not user_session.get('survey_completed'):
                        if response_text:
                            await whatsapp_bot.send_whatsapp_message(from_number, response_text)
                        return
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
                            await whatsapp_bot.send_whatsapp_message(from_number, response_text)
                        return
                    # Email collection
                    if user_session['chatbot'].lead_status == LeadStatus.COLLECTING_EMAIL or user_session.get('awaiting_email'):
                        user_session['awaiting_email'] = False
                        response_text = user_chatbot.ask(message_body)
                        if response_text:
                            await whatsapp_bot.send_whatsapp_message(from_number, response_text)
                        return

                # Intent detection
                elif await whatsapp_bot.detect_placement_intent(message_body) and not user_session.get('placement_images_sent', False):
                    if await whatsapp_bot.send_placement_images(from_number):
                        user_session['placement_images_sent'] = True
                        response_text = None
                    else:
                        response_text = (
                            "പ്ലേസ്മെന്റ് വിവരങ്ങൾ ലോഡ് ചെയ്യുന്നതിൽ പ്രശ്‌നം നേരിടുന്നു. ദയവായി പിന്നീട് വീണ്ടും ശ്രമിക്കുക."
                            if user_session.get('preferred_language') == 'malayalam' else
                            "I'm having trouble loading the placement information. Please try again later."
                        )
                elif await whatsapp_bot.detect_fees_intent(message_body) and not user_session.get('fees_images_sent', False):
                    if await whatsapp_bot.send_fees_images(from_number):
                        user_session['fees_images_sent'] = True
                        response_text = None
                    else:
                        response_text = (
                            "ഫീസ് വിവരങ്ങൾ ലോഡ് ചെയ്യുന്നതിൽ പ്രശ്‌നം നേരിടുന്നു. ദയവായി പിന്നീട് വീണ്ടും ശ്രമിക്കുക."
                            if user_session.get('preferred_language') == 'malayalam' else
                            "I'm having trouble loading the fees information. Please try again later."
                        )
                elif await whatsapp_bot.detect_flutter_intent(message_body):
                    # Send the Flutter reel only once per session
                    if not user_session.get('flutter_reel_sent', False):
                        if await whatsapp_bot.send_flutter_reel(from_number):
                            user_session['flutter_reel_sent'] = True
                        else:
                            response_text = (
                                "ഫ്ലട്ടർ കണ്ടെന്റ് ലോഡ് ചെയ്യുന്നതിൽ പ്രശ്‌നം നേരിടുന്നു. ദയവായി പിന്നീട് വീണ്ടും ശ്രമിക്കുക."
                                if user_session.get('preferred_language') == 'malayalam' else
                                "I'm having trouble loading the Flutter content. Please try again later."
                            )
                    # Check if survey is active before calling chatbot
                    if user_session.get('survey_started') and not user_session.get('survey_completed'):
                        return  # Block chatbot during survey
                    
                    # Process the message through chatbot for Flutter queries
                    response_text = user_chatbot.ask(message_body)
                    
                    # Check if response contains exclusive offer signal
                    if "|SEND_EXCLUSIVE_OFFER|" in response_text:
                        # Split response and exclusive offer
                        main_response = response_text.replace("|SEND_EXCLUSIVE_OFFER|", "")
                        
                        # Send main response first
                        if main_response.strip():
                            await whatsapp_bot.send_whatsapp_message(from_number, main_response)
                        
                        # Send exclusive offer as interactive buttons
                        lang = user_session.get('preferred_language', 'english')
                        await whatsapp_bot.send_exclusive_offer_buttons(from_number, lang)
                        return
                    else:
                        # Clear response_text to prevent sending it again at the end
                        response_text = None
                else:
                    # Check for "Yes" response to exclusive offer to start survey
                    if message_body.strip().lower() in ['yes', 'അതെ'] and not user_session.get('survey_started', False) and not user_session.get('survey_completed', False):
                        user_session['survey_started'] = True
                        user_session['current_survey_question'] = 'q1'
                        # Set wants_personalized flag for text "Yes" responses
                        if user_chatbot and hasattr(user_chatbot, 'current_lead'):
                            user_chatbot.current_lead.wants_personalized = True
                        await whatsapp_bot.send_survey_poll(from_number, 'q1')
                        if user_session.get('preferred_language') == 'malayalam':
                            response_text = "oh great! നിങ്ങളുടെ അനുഭവം വ്യക്തിഗതമാക്കാം. നിങ്ങളുടെ background മികച്ചതായി മനസ്സിലാക്കാൻ ഞാൻ നിങ്ങൾക്ക് കുറച്ച് ചോദ്യങ്ങൾ അയയ്ക്കും."
                        else:
                            response_text = "Great! Let's personalize your experience. I'll send you a few quick questions to understand your background better."
                        await whatsapp_bot.send_whatsapp_message(from_number, response_text)
                        return
                    
                    # Check for "No" response to exclusive offer to skip survey and go to name collection
                    elif message_body.strip().lower() in ['no', 'ഇല്ല'] and not user_session.get('survey_started', False) and not user_session.get('survey_completed', False):
                        # Skip survey and go directly to name collection
                        user_session['awaiting_name'] = True
                        user_chatbot.lead_status = LeadStatus.COLLECTING_NAME
                        
                        if user_session.get('preferred_language') == 'malayalam':
                            response_text = "കുഴപ്പമില്ല! നിങ്ങളുടെ FULL NAME നൽകാമോ? (TYPE ONLY IN ENGLISH)"
                        else:
                            response_text = "No problem! Could you please share your full name?"
                        await whatsapp_bot.send_whatsapp_message(from_number, response_text)
                        return
                    
                    # Stop further processing while survey is ongoing to avoid extra messages
                    if user_session.get('survey_started') and not user_session.get('survey_completed'):
                        if response_text:
                            await whatsapp_bot.send_whatsapp_message(from_number, response_text)
                        return
                    
                    if user_session.get('survey_completed'):
                        response_text = user_chatbot._invoke_system_prompt_chain(
                            message_body, user_session.get('preferred_language') or 'english'
                        )
                    else:
                        response_text = user_chatbot.ask(message_body)
                        
                        # Check if response contains exclusive offer signal
                        if "|SEND_EXCLUSIVE_OFFER|" in response_text:
                            # Split response and exclusive offer
                            main_response = response_text.replace("|SEND_EXCLUSIVE_OFFER|", "")
                            
                            # Send main response first
                            if main_response.strip():
                                await whatsapp_bot.send_whatsapp_message(from_number, main_response)
                            
                            # Send exclusive offer as interactive buttons
                            lang = user_session.get('preferred_language', 'english')
                            await whatsapp_bot.send_exclusive_offer_buttons(from_number, lang)
                            return
                        # For non-exclusive offer responses, keep response_text to send normally
                        
                        if response_text == "SURVEY_START":
                            user_session['survey_started'] = True
                            user_session['current_survey_question'] = 'q1'
                            await whatsapp_bot.send_survey_poll(from_number, 'q1')
                            if user_session.get('preferred_language') == 'malayalam':
                                response_text = "oh great! നിങ്ങളുടെ അനുഭവം വ്യക്തിഗതമാക്കാം. നിങ്ങളുടെ background മികച്ചതായി മനസ്സിലാക്കാൻ ഞാൻ നിങ്ങൾക്ക് കുറച്ച് ചോദ്യങ്ങൾ അയയ്ക്കും."
                            else:
                                response_text = "Great! Let's personalize your experience. I'll send you a few quick questions to understand your background better."

            # Send response if available
            if response_text:
                await whatsapp_bot.send_whatsapp_message(from_number, response_text)

    except Exception as e:
        logger.error(f"Error processing message from {from_number}: {e}")
        await whatsapp_bot.send_whatsapp_message(
            from_number, 
            "Sorry, I encountered an error. Please try again."
        )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy", 
        timestamp=datetime.now().isoformat()
    )

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "LevelX WhatsApp Bot API", "version": "2.0.0", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
