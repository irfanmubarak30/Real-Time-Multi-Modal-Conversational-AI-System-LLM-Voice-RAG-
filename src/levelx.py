import os
import re
import json
import logging
import requests
from datetime import datetime
from enum import Enum
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from pinecone import Pinecone as PineconeClient, ServerlessSpec
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_pinecone import PineconeVectorStore
from langchain_core.prompts import PromptTemplate
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from google_sheets_manager import GoogleSheetsManager

# Setup logging for better debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Data and State Management Classes ---

class LeadStatus(Enum):
    """Enum for lead collection status"""
    NO_INTENT = "no_intent"
    INTENT_DETECTED = "intent_detected"
    OFFERING_PERSONALIZED = "offering_personalized"
    SURVEY_Q1 = "survey_q1"
    SURVEY_Q2 = "survey_q2"
    SURVEY_Q3 = "survey_q3"
    SURVEY_Q4 = "survey_q4"
    COLLECTING_NAME = "collecting_name"
    COLLECTING_EMAIL = "collecting_email"
    PERSONALIZED_MODE = "personalized_mode"  # New state for personalized experience
    LEAD_COMPLETE = "lead_complete"

class LeadData:
    """Class to store lead information"""
    def __init__(self):
        self.name = None
        self.phone = None
        self.email = None
        self.intent_message = None
        self.wants_personalized = None
        self.survey_answers = {
            "q1": None,  # Current role/profession
            "q2": None,  # Career goals
            "q3": None,  # Skill level
            "q4": None   # Preferred learning format
        }

# --- Survey Configuration ---
SURVEY_CONFIG = {
    "system_prompt": {
        "role": "LevelX AI Personalization Assistant",
        "objective": "Collect user information to create a personalized learning experience",
        "questions": [
            {
                "id": "q1",
                "question": {
                    "english": "Are you a student / working professional / other?",
                    "malayalam": "താങ്കൾ ഒരു Student ആണോ / Working Professional ആണോ/മറ്റ് ഏതെങ്കിലുമാണോ??"
                },
                "options": {
                    "english": ["Student", "Working Professional", "Other"],
                    "malayalam": ["Student", "Working Professional", "Other"]
                },
                "context": "This helps us understand your background.",
                "response_format": "Student, Working Professional, or Other"
            },
            {
                "id": "q2",
                "question": {
                    "english": "Are you from a tech background?",
                    "malayalam": "നിങ്ങൾ Tech backgrounൽ നിന്ന് ആണോ വരുന്നത്??"
                },
                "options": {
                    "english": ["Yes", "No"],
                    "malayalam": ["അതെ", "അല്ല"]
                },
                "context": "This helps us understand your familiarity with technology.",
                "response_format": "Yes or No"
            },
            {
                "id": "q3",
                "question": {
                    "english": "What motivates you to learn tech?",
                    "malayalam": "ടെക് പഠിക്കാൻ നിങ്ങളെ പ്രേരിപ്പിക്കുന്നത് എന്താണ്?"
                },
                "options": {
                    "english": ["Career change", "Higher salary", "Freelancing", "Passion"],
                    "malayalam": ["കരിയർ മാറ്റം", "ഉയർന്ന ശമ്പളം", "ഫ്രീലാൻസിംഗ്", "താൽപര്യം"]
                },
                "context": "This helps us understand your motivation.",
                "response_format": "Career change, Higher salary, Freelancing, or Passion"
            },
            {
                "id": "q4",
                "question": {
                    "english": "Which area interests you most? (Full Stack Flutter / Full Stack React / Digital Marketing / Data Science / Not sure)",
                    "malayalam": "താങ്കൾക്ക് ഏറ്റവും താൽപര്യമുള്ള/Area ഏതാണ്?)"
                },
                "options": {
                    "english": ["Full Stack Flutter", "Full Stack React", "Digital Marketing", "Data Science", "Not sure"],
                    "malayalam": ["Full Stack Flutter", "Full Stack React", "Digital Marketing", "Data Science", "Not sure (ഉറപ്പില്ല / തീർച്ചയല്ല)"]
                },
                "context": "This helps us recommend the best learning path for you.",
                "response_format": "Full Stack Flutter, Full Stack React, Digital Marketing, Data Science, or Not sure"
            }
        ],
        "completion_message": {
            "english": "Thank you for completing our personalization survey! Based on your responses, we'll create a customized learning path just for you.",
            "malayalam": "ഞങ്ങളുടെ വ്യക്തിഗത സർവേ പൂർത്തിയാക്കിയതിന് നന്ദി! നിങ്ങളുടെ മറുപടികൾ അടിസ്ഥാനമാക്കി, നിങ്ങൾക്കായി ഒരു ഇഷ്ടാനുസൃത പഠന പാത സൃഷ്ടിക്കും."
        },
        "exclusive_offer": {
            "english": "\n\n🎯 **Exclusive Offer!** 🎯\n\nWould you like a personalized version of LevelX AI? I can create a customized learning path based on your specific goals and background through a quick 4-question survey.\n\nWould you be interested in this personalized experience? (Yes/No)",
            "malayalam": "\n\n🎯 **പ്രത്യേക ഓഫർ!** 🎯\n\nനിങ്ങൾക്ക് LevelX AI-ന്റെ വ്യക്തിഗത പതിപ്പ് വേണമോ? നിങ്ങളുടെ പ്രത്യേക ലക്ഷ്യങ്ങളും പശ്ചാത്തലവും അടിസ്ഥാനമാക്കി 4 ചോദ്യങ്ങളുള്ള ഒരു ക്വിക്ക് സർവേ വഴി ഒരു ഇഷ്ടാനുസൃത പഠന പാത സൃഷ്ടിക്കാം.\n\nഈ വ്യക്തിഗത അനുഭവത്തിൽ നിങ്ങൾക്ക് താൽപ്പര്യമുണ്ടോ? (അതെ/ഇല്ല)"
        },
        "survey_start": {
            "english": "Great! Let's personalize your experience.\n\n**Question 1 of 4:**",
            "malayalam": "അതിശയിക്കാം! നിങ്ങളുടെ അനുഭവം വ്യക്തിഗതമാക്കാം.\n\n**ചോദ്യം 1/4:**"
        },
        "thank_you": {
            "english": "Thank you!",
            "malayalam": "നന്ദി!"
        },
        "great": {
            "english": "Great!",
            "malayalam": "അതിശയിക്കാം!"
        },
        "perfect": {
            "english": "Perfect!",
            "malayalam": "തികഞ്ഞതാണ്!"
        },
        "question_2": {
            "english": "**Question 2 of 4:**",
            "malayalam": "**ചോദ്യം 2/4:**"
        },
        "question_3": {
            "english": "**Question 3 of 4:**",
            "malayalam": "**ചോദ്യം 3/4:**"
        },
        "question_4": {
            "english": "**Question 4 of 4:**",
            "malayalam": "**ചോദ്യം 4/4:**"
        },
        "name_request": {
            "english": "Now, to connect you with our team and send your personalized recommendations, could you please share your full name?",
            "malayalam": "ഇപ്പോൾ, ഞങ്ങളുടെ ടീമുമായി നിങ്ങളെ ബന്ധിപ്പിക്കാനും നിങ്ങളുടെ വ്യക്തിഗത ശുപാർശകൾ അയയ്ക്കാനും, നിങ്ങളുടെ പൂർണ്ണ നാമം പങ്കുവെയ്ക്കാമോ?"
        },
        "no_problem": {
            "english": "No problem! Could you please share your full name to connect you with our team?",
            "malayalam": "പ്രശ്നമില്ല! ഞങ്ങളുടെ ടീമുമായി നിങ്ങളെ ബന്ധിപ്പിക്കാൻ നിങ്ങളുടെ പൂർണ്ണ നാമം പങ്കുവെയ്ക്കാമോ?"
        },
        "didnt_catch": {
            "english": "I didn't catch that. Would you like the personalized experience? Please answer with 'yes' or 'no'.",
            "malayalam": "അത് മനസ്സിലായില്ല. നിങ്ങൾക്ക് വ്യക്തിഗത അനുഭവം വേണമോ? 'അതെ' അല്ലെങ്കിൽ 'ഇല്ല' എന്ന് മറുപടി നൽകുക."
        }
    }
}

# --- External Service Management ---

# --- Core ChatBot Logic ---

class ChatBot:
    """
    A chatbot class that uses a Retrieval-Augmented Generation (RAG) pipeline
    with conversational memory and personalized survey.
    """
    def __init__(self):
        """Initializes the chatbot and all its components."""
        # --- 1. Load Environment Variables ---
        load_dotenv()
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.pinecone_api_key = os.getenv('PINECONE_API_KEY')
        self.pinecone_env = os.getenv('PINECONE_ENVIORNMENT')

        self.google_api_key = os.getenv('GOOGLE_API_KEY')

        if not all([self.openai_api_key, self.pinecone_api_key]):
            raise ValueError("OpenAI and Pinecone API keys are missing from .env file.")
        
        self._initialize_google_sheets()

        # --- 2. Lead Collection State ---
        self.lead_status = LeadStatus.NO_INTENT
        self.current_lead = LeadData()
        self.current_survey_question = None
        self.preferred_language = None  # Add this line
        self.language_selected = False  # Add this flag

        # --- 3. Initialize LangChain Components ---
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=self.openai_api_key)
        self.llm = ChatOpenAI(
            model="gpt-5-nano",  # Fixed model name
            openai_api_key=self.openai_api_key,
            temperature=1,
        )
        
        # --- 4. Setup Vector Store and RAG Chain ---
        docsearch = self._initialize_pinecone()
        self.rag_chain = self._create_rag_chain(docsearch)
        
        print("✅ LEVELX AI Assistant with Personalized Survey is ready!")

    def _initialize_google_sheets(self):
        """Initializes the Google Sheets manager if credentials are present."""
        try:
            logger.info("🔄 Initializing Google Sheets connection...")
            self.sheets_manager = GoogleSheetsManager()
            
            # Test connection and setup headers
            success, message = self.sheets_manager.test_connection()
            if success:
                logger.info(f"✅ Google Sheets initialized: {message}")
                # Setup headers if needed
                self.sheets_manager.setup_sheet_headers()
            else:
                logger.warning(f"⚠️ Google Sheets connection issue: {message}")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Sheets manager: {e}")
            self.sheets_manager = None

    def _initialize_pinecone(self):
        """Connects to Pinecone and sets up the vector index."""
        self.index_name = "levelxbot"
        try:
            pc = PineconeClient(api_key=self.pinecone_api_key)
            if self.index_name not in pc.list_indexes().names():
                pc.create_index(
                    name=self.index_name, dimension=1536, metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
                self._populate_pinecone_index()
            
            return PineconeVectorStore.from_existing_index(self.index_name, self.embeddings)
        except Exception as e:
            logger.error(f"Error initializing Pinecone: {e}")
            raise

    def _populate_pinecone_index(self):
        """Loads data from a file and embeds it into the Pinecone index."""
        print("Index is empty. Loading and embedding documents...")
        file_path = './materials/levelx.txt'
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document file not found: {file_path}")
        
        loader = TextLoader(file_path)
        documents = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        docs = text_splitter.split_documents(documents)
        
        print(f"Splitting document into {len(docs)} chunks.")
        PineconeVectorStore.from_documents(docs, self.embeddings, index_name=self.index_name)
        print(f"✅ Documents successfully added to index.")

    def _create_rag_chain(self, docsearch):
        """Creates the ConversationalRetrievalChain with a custom prompt and memory."""
        template = """
You are the LevelX AI Assistant. Use ONLY the following Retrieved Context to answer questions.
ALWAYS respond in {language} language.

Rules:
1. ONLY use information from the Retrieved Context
2. If language is 'malayalam', respond ONLY in Malayalam, keeping only technical terms in English
3. If language is 'english', respond in English
4. If information is not in context, respond:
   English: "I don't have specific information about that in my database."
   Malayalam: "ഇതിനെക്കുറിച്ചുള്ള കൃത്യമായ വിവരങ്ങൾ എന്റെ ഡാറ്റാബേസിൽ ലഭ്യമല്ല."

Retrieved Context: {context}
Previous conversation: {chat_history}
Current Question: {question}
Response Language: {language}

Provide a helpful response:"""

        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="answer"
        )

        # Create the prompt template with language parameter
        prompt = PromptTemplate(
            template=template,
            input_variables=["context", "question", "chat_history", "language"]
        )

        chain = ConversationalRetrievalChain.from_llm(
            llm=self.llm,
            retriever=docsearch.as_retriever(search_kwargs={"k": 3}),
            memory=memory,
            combine_docs_chain_kwargs={"prompt": prompt},
            return_source_documents=True
        )
        
        # Store the prompt template as an instance variable
        self.rag_prompt_template = prompt
        return chain
    
    def _invoke_rag_chain_with_language(self, question: str, language: str):
        """Custom method to invoke RAG chain with language parameter"""
        try:
            # Get the retriever and memory from the existing chain
            retriever = self.rag_chain.retriever
            memory = self.rag_chain.memory
            
            # Get relevant documents
            docs = retriever.get_relevant_documents(question)
            context = "\n\n".join([doc.page_content for doc in docs])
            
            # Get chat history
            chat_history = ""
            if hasattr(memory, 'chat_memory') and memory.chat_memory.messages:
                chat_history = "\n".join([f"{msg.type}: {msg.content}" for msg in memory.chat_memory.messages[-6:]])
            
            # Use the prompt template directly
            prompt = self.rag_prompt_template
            formatted_prompt = prompt.format(
                context=context,
                question=question,
                chat_history=chat_history,
                language=language
            )
            
            # Get response from LLM
            response = self.llm.invoke(formatted_prompt).content
            
            # Update memory
            memory.chat_memory.add_user_message(question)
            memory.chat_memory.add_ai_message(response)
            
            return {"answer": response, "source_documents": docs}
            
        except Exception as e:
            logger.error(f"Error in custom RAG chain invocation: {e}")
            return {"answer": "I apologize, but I encountered an error processing your request.", "source_documents": []}
    
    # --- Data Extraction Helpers ---

    def _detect_intent(self, question: str) -> bool:
        try:
            classification_prompt = (
                "You are an intent classifier for a sales assistant.\n"
                "Decide if the following conversation shows buying or consultation intent.\n"
                "Intent should be true if the user is interested in:\n"
                "- Enrolling in a course\n"
                "- Getting pricing info\n"
                "- Scheduling a call/demo/meeting\n"
                "- Asking for consultation or help joining\n"
                "- Learning more about courses/programs\n"
                "- Getting detailed information about offerings\n"
                "- Understanding what courses are available\n"
                "- Exploring educational options\n\n"
                f"Message: \"{question}\"\n\n"
                "Does this message show buying or consultation intent? Respond with only 'yes' or 'no'."
         )

            response = self.llm.invoke(classification_prompt).content.strip().lower()
            return response.startswith("yes")

        except Exception as e:
            logger.error(f"Intent detection error: {e}")
            return False

    def _detect_yes_no(self, text: str) -> bool | None:
        """Detects yes/no responses for personalized offer"""
        text_lower = text.lower().strip()
        yes_patterns = ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'definitely', 'absolutely', 'i would like', 'sounds good']
        no_patterns = ['no', 'nah', 'nope', 'not interested', 'no thanks', 'not now']
        
        if any(pattern in text_lower for pattern in yes_patterns):
            return True
        elif any(pattern in text_lower for pattern in no_patterns):
            return False
        return None

    def _extract_name(self, text: str) -> str | None:
        """Extracts a name from user input."""
        patterns = [
            r"i'?m\s+([a-zA-Z\s]+)", r"my name is\s+([a-zA-Z\s]+)",
            r"this is\s+([a-zA-Z\s]+)", r"call me\s+([a-zA-Z\s]+)",
            r"i am\s+([a-zA-Z\s]+)"
        ]
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                name = match.group(1).strip().title()
                if name and len(name.split()) <= 3 and name.lower() not in ['sure', 'yes', 'no', 'ok', 'interested']:
                    return name
        words = text.strip().split()
        if 1 <= len(words) <= 3 and all(word.isalpha() for word in words):
            name = text.strip().title()
            if name.lower() not in ['sure', 'yes', 'no', 'ok', 'interested']:
                return name
        return None

    def set_phone_number(self, phone_number: str) -> None:
            """Sets the phone number from external source (e.g., WhatsApp)."""
            if phone_number:
                self.current_lead.phone = phone_number.strip()
                logger.info(f"📱 Phone number set from external source: {phone_number}")

    def _extract_email(self, text: str) -> str | None:
        """Extracts an email address from user input."""
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(pattern, text)
        return match.group(0) if match else None

    def _get_survey_question(self, question_id: str) -> dict:
        """Gets survey question configuration by ID"""
        questions = SURVEY_CONFIG["system_prompt"]["questions"]
        for q in questions:
            if q["id"] == question_id:
                return q
        return None

    def _generate_personalized_recommendations(self) -> str:
        """Generate personalized course recommendations based on survey responses and Pinecone data, with new survey logic and special handling for 'Other' and 'Not sure'"""
        try:
            # First get relevant course information from Pinecone
            course_query = "What courses does LevelX offer?"
            course_result = self._invoke_rag_chain_with_language(course_query, self.preferred_language or 'english')

            # Prepare user profile fields with new survey meanings
            background = self.current_lead.survey_answers.get('q1', 'Not specified')
            tech_background = self.current_lead.survey_answers.get('q2', 'Not specified')
            motivation = self.current_lead.survey_answers.get('q3', 'Not specified')
            interest_area = self.current_lead.survey_answers.get('q4', 'Not specified')

            # Special handling for 'Other' and 'Not sure'
            if isinstance(background, str) and background.lower() == 'other':
                background = "(User specified 'Other' as background)"
            if isinstance(interest_area, str) and (interest_area.lower().startswith('not sure') or 'ഉറപ്പില്ല' in interest_area or 'തീർച്ചയല്ല' in interest_area):
                interest_area = "User is not sure about their area of interest. Please suggest suitable options."

            # Use the retrieved course information for recommendations
            recommendation_prompt = f"""
Based on the following user profile and ONLY the retrieved course information below, provide personalized recommendations:

USER PROFILE:
- Name: {self.current_lead.name}
- Background: {background}
- Tech Background: {tech_background}
- Motivation to Learn Tech: {motivation}
- Area of Interest: {interest_area}

RETRIEVED COURSE INFORMATION:
{course_result.get('answer', '')}

RULES:
1. ONLY recommend courses that are explicitly mentioned in the Retrieved Course Information
2. DO NOT invent or assume course details
3. If no suitable courses are found in the context, acknowledge this and suggest talking to an advisor
4. Keep technical terms and course names exactly as they appear in the context

Provide a personalized response focusing on actual LevelX courses that match their profile."""
            response = self.llm.invoke(recommendation_prompt).content.strip()

            # Format the final response based on language
            if self.preferred_language == 'malayalam':
                return (
                    f"നിങ്ങളുടെ പ്രൊഫൈലും ലഭ്യമായ കോഴ്‌സുകളും അടിസ്ഥാനമാക്കി, എന്റെ ശുപാർശകൾ:\n\n"
                    f"{response}\n\n"
                    f"ഈ ശുപാർശകൾ നിങ്ങളുടെ പശ്ചാത്തലത്തിനും അനുയോജ്യമായ യഥാർത്ഥ LevelX കോഴ്‌സുകളെ അടിസ്ഥാനമാക്കിയുള്ളതാണ് "
                    f"{background} എന്ന നിലയിലും "
                    f"{interest_area} എന്ന താൽപര്യത്തിലും."
                )
            else:
                return (
                    f"Based on your profile and our available courses, here are my recommendations:\n\n"
                    f"{response}\n\n"
                    f"These recommendations are based on actual LevelX courses that align with your background "
                    f"({background}) and your area of interest ({interest_area})."
                )
        except Exception as e:
            logger.error(f"Error generating personalized recommendations: {e}")
            if self.preferred_language == 'malayalam':
                return ("ക്ഷമിക്കണം, വ്യക്തിഗത ശുപാർശകൾ സൃഷ്ടിക്കുന്നതിൽ ഒരു പ്രശ്നം നേരിട്ടു. "
                        "ഞങ്ങളുടെ കോഴ്‌സുകളെക്കുറിച്ച് നിങ്ങൾക്ക് ചോദ്യങ്ങൾ ഉണ്ടെങ്കിൽ ചോദിക്കാം, ഞാൻ സഹായിക്കാം.")
            else:
                return ("I apologize, but I encountered an issue generating personalized recommendations. "
                        "Please ask me specific questions about our courses and I'll help guide you.")

    def _create_personalized_prompt_template(self):
        """Creates a personalized RAG chain prompt based on user's survey data (new survey logic)"""
        background = self.current_lead.survey_answers.get('q1', 'Not specified')
        tech_background = self.current_lead.survey_answers.get('q2', 'Not specified')
        motivation = self.current_lead.survey_answers.get('q3', 'Not specified')
        interest_area = self.current_lead.survey_answers.get('q4', 'Not specified')
        # Special handling for 'Other' and 'Not sure'
        if isinstance(background, str) and background.lower() == 'other':
            background = "(User specified 'Other' as background)"
        if isinstance(interest_area, str) and (interest_area.lower().startswith('not sure') or 'ഉറപ്പില്ല' in interest_area or 'തീർച്ചയല്ല' in interest_area):
            interest_area = "User is not sure about their area of interest. Please suggest suitable options."
        user_context = f"""
PERSONALIZED CONTEXT FOR {self.current_lead.name.upper()}:
Name: {self.current_lead.name}
Background: {background}
Tech Background: {tech_background}
Motivation to Learn Tech: {motivation}
Area of Interest: {interest_area}

RESPONSE REQUIREMENTS:
1. Use ONLY the information from the Retrieved Context below
2. If information isn't in the context, say: "I don't have specific information about that in our course database"
3. Keep responses focused on LevelX's actual courses and offerings
4. Relate answers to {self.current_lead.name}'s background and goals
5. Match course recommendations to their area of interest: {interest_area}

INTERACTION GUIDELINES:
1. Address as: {self.current_lead.name}
2. Reference their background: {background}
3. Align with their motivation: {motivation}
4. Match their area of interest: {interest_area}

CONTEXT USAGE RULES:
- ONLY use information present in the Retrieved Context
- DO NOT make assumptions about course details not mentioned
- DO NOT invent features or benefits
- If unsure, acknowledge limitations of available information
- ALWAYS respond in {{language}} language
- If language is 'malayalam', respond ONLY in Malayalam, keeping only technical terms in English
- If language is 'english', respond in English

Retrieved Context: {{context}}
Previous Discussion: {{chat_history}}
Current Question: {{question}}
Response Language: {{language}}

Based strictly on the above context, provide a personalized response for {self.current_lead.name}:"""
        return user_context

    # --- Core State Machine ---

    def _handle_lead_collection(self, question: str) -> str | None:
        """Enhanced lead collection state machine with personalized survey flow"""
        
        # Course lists for both languages
        course_list_en = [
            "• Flutter Full Stack Development",
            "• React Full Stack Development", 
            "• Digital Marketing Mastery",
            "• Data Analytics and Visualization"
        ]
        course_list_ml = [
            "• ഫ്ലട്ടർ ഫുൾ സ്റ്റാക്ക് ഡെവലപ്പ്മെന്റ്",
            "• റിയാക്ട് ഫുൾ സ്റ്റാക്ക് ഡെവലപ്പ്മെന്റ്",
            "• ഡിജിറ്റൽ മാർക്കറ്റിംഗ് മാസ്റ്ററി",
            "• ഡാറ്റാ അനലിറ്റിക്സ് ആൻഡ് വിഷ്വലൈസേഷൻ"
        ]
        
        # Course keywords for detection
        course_keywords_en = ["course", "courses", "program", "programs", "learning path", "what do you offer", "available courses"]
        course_keywords_ml = ["കോഴ്സ്", "കോഴ്സുകൾ", "പഠനം", "പാഠ്യക്രമം", "പാഠ്യക്രമങ്ങൾ"]
        specific_courses_en = ["flutter", "react", "digital marketing", "data analytics", "data analysis", "visualization"]
        specific_courses_ml = ["ഫ്ലട്ടർ", "റിയാക്ട്", "ഡിജിറ്റൽ മാർക്കറ്റിംഗ്", "ഡാറ്റാ അനലിറ്റിക്സ്"]

        # Only check for new intent if we're in NO_INTENT or LEAD_COMPLETE state
        if self.lead_status in [LeadStatus.NO_INTENT, LeadStatus.LEAD_COMPLETE]:
            if self._detect_intent(question):
                logger.info(f"🎯 Intent detected: {question}")
                self.current_lead.intent_message = question
                self.lead_status = LeadStatus.INTENT_DETECTED
                
                # Check if this is a course-related query
                language = self.preferred_language or 'english'
                question_lower = question.lower()
                
                if language == 'malayalam':
                    is_general_course_query = any(kw in question for kw in course_keywords_ml) and not any(specific in question for specific in specific_courses_ml)
                    if is_general_course_query:
                        content_answer = "LevelX-ൽ ലഭ്യമായ കോഴ്സുകൾ:\n\n" + "\n".join(course_list_ml)
                    else:
                        # For specific course queries, use RAG
                        rag_result = self._invoke_rag_chain_with_language(question, language)
                        content_answer = rag_result.get('answer', "I can certainly help with that.")
                else:
                    is_general_course_query = any(kw in question_lower for kw in course_keywords_en) and not any(specific in question_lower for specific in specific_courses_en)
                    if is_general_course_query:
                        content_answer = "Available courses at LevelX:\n\n" + "\n".join(course_list_en)
                    else:
                        # For specific course queries, use RAG
                        rag_result = self._invoke_rag_chain_with_language(question, language)
                        content_answer = rag_result.get('answer', "I can certainly help with that.")
                
                # Offer personalized LevelX AI with language support
                personalized_offer = SURVEY_CONFIG["system_prompt"]["exclusive_offer"][language]
                
                # Transition to offering personalized
                self.lead_status = LeadStatus.OFFERING_PERSONALIZED
                return f"{content_answer}{personalized_offer}"
    
        # Handle other states without re-detecting intent
        if self.lead_status == LeadStatus.OFFERING_PERSONALIZED:
            response = self._detect_yes_no(question)
            language = self.preferred_language or 'english'
            if response is True:
                self.current_lead.wants_personalized = True
                self.lead_status = LeadStatus.SURVEY_Q1
                # Return SURVEY_START signal for WhatsApp to handle with polls
                return "SURVEY_START"
            elif response is False:
                self.current_lead.wants_personalized = False
                self.lead_status = LeadStatus.COLLECTING_NAME
                return SURVEY_CONFIG["system_prompt"]["no_problem"][language]
            else:
                return SURVEY_CONFIG["system_prompt"]["didnt_catch"][language]

        # Survey Question Handlers
        if self.lead_status == LeadStatus.SURVEY_Q1:
            self.current_lead.survey_answers["q1"] = question.strip()
            self.lead_status = LeadStatus.SURVEY_Q2
            q2_config = self._get_survey_question("q2")
            language = self.preferred_language or 'english'
            thank_you = SURVEY_CONFIG["system_prompt"]["thank_you"][language]
            question_2 = SURVEY_CONFIG["system_prompt"]["question_2"][language]
            return f"{thank_you} \n\n{question_2}\n{q2_config['question'][language]}"

        if self.lead_status == LeadStatus.SURVEY_Q2:
            self.current_lead.survey_answers["q2"] = question.strip()
            self.lead_status = LeadStatus.SURVEY_Q3
            q3_config = self._get_survey_question("q3")
            language = self.preferred_language or 'english'
            great = SURVEY_CONFIG["system_prompt"]["great"][language]
            question_3 = SURVEY_CONFIG["system_prompt"]["question_3"][language]
            return f"{great} \n\n{question_3}\n{q3_config['question'][language]}"

        if self.lead_status == LeadStatus.SURVEY_Q3:
            self.current_lead.survey_answers["q3"] = question.strip()
            self.lead_status = LeadStatus.SURVEY_Q4
            q4_config = self._get_survey_question("q4")
            language = self.preferred_language or 'english'
            perfect = SURVEY_CONFIG["system_prompt"]["perfect"][language]
            question_4 = SURVEY_CONFIG["system_prompt"]["question_4"][language]
            return f"{perfect} \n\n{question_4}\n{q4_config['question'][language]}"

        if self.lead_status == LeadStatus.SURVEY_Q4:
            self.current_lead.survey_answers["q4"] = question.strip()
            self.lead_status = LeadStatus.COLLECTING_NAME
            language = self.preferred_language or 'english'
            completion_msg = SURVEY_CONFIG["system_prompt"]["completion_message"][language]
            name_request = SURVEY_CONFIG["system_prompt"]["name_request"][language]
            return f"{completion_msg}\n\n{name_request}"

        # Contact Information Collection
        if self.lead_status == LeadStatus.COLLECTING_NAME:
            name = self._extract_name(question)
            language = self.preferred_language or 'english'
            if name:
                self.current_lead.name = name
                self.lead_status = LeadStatus.COLLECTING_EMAIL
                if language == 'malayalam':
                    return f"നന്ദി, {name}! അവസാനമായി, നിങ്ങളുടെ ഇമെയിൽ വിലാസം എന്താണ്?"
                else:
                    return f"Thank you, {name}! Finally, what's your email address?"
            else:
                if language == 'malayalam':
                    return "ക്ഷമിക്കണം, ഒരു സാധുവായ പേര് മനസ്സിലായില്ല. നിങ്ങളുടെ പൂർണ്ണ നാമം നൽകാമോ?"
                else:
                    return "I'm sorry, I didn't catch a valid name. Could you please provide your full name?"

        if self.lead_status == LeadStatus.COLLECTING_EMAIL:
            email = self._extract_email(question)
            language = self.preferred_language or 'english'
            if email:
                self.current_lead.email = email
                
                # Save user data to Google Sheets
                if self.current_lead.name and self.current_lead.phone:
                    # Save user info to users sheet
                    self.save_user_to_sheets(self.current_lead.name, self.current_lead.phone)
                    
                    # If they completed the survey, save that too
                    if all(self.current_lead.survey_answers.values()):
                        self.save_survey_to_sheets(
                            name=self.current_lead.name,
                            phone_number=self.current_lead.phone,
                            email=email,
                            survey_answers=self.current_lead.survey_answers
                        )
                
                # Switch to personalized mode if they wanted it
                if self.current_lead.wants_personalized:
                    self.lead_status = LeadStatus.PERSONALIZED_MODE
                    self._update_to_personalized_mode()
                    recommendations = self._generate_personalized_recommendations()
                    
                    if language == 'malayalam':
                        return (
                            f"🎉 ഹലോ {self.current_lead.name}! ഞാൻ ഇപ്പോൾ നിങ്ങൾക്കായി പ്രത്യേകമായി ഇഷ്ടാനുസൃതമാക്കിയ LevelX AI-ന്റെ പതിപ്പാണ്!\n\n"
                            f"നിങ്ങളുടെ സർവേ മറുപടികൾ അടിസ്ഥാനമാക്കി, എന്റെ ശുപാർശകൾ:\n\n{recommendations}\n\n"
                            f"ഞാൻ ഇപ്പോൾ നിങ്ങളുടെ പശ്ചാത്തലത്തിനും ലക്ഷ്യങ്ങൾക്കും അനുയോജ്യമായി പൂർണ്ണമായും വ്യക്തിഗതമാക്കിയിരിക്കുന്നു. കോഴ്‌സുകൾ, കരിയർ ഉപദേശം, അല്ലെങ്കിൽ പഠന പാതകൾ എന്നിവയെക്കുറിച്ച് എന്തെങ്കിലും ചോദിക്കാം - "
                            f"ഞാൻ എല്ലാം നിങ്ങളുടെ യാത്രയ്ക്ക് അനുയോജ്യമായി ഇഷ്ടാനുസൃതമാക്കും {self.current_lead.survey_answers.get('q1', 'വിദഗ്ധൻ')} "
                            f"എന്ന നിലയിൽ നിങ്ങളുടെ ലക്ഷ്യങ്ങളിലേക്ക്!\n\n"
                            f"നിങ്ങളുടെ പഠന യാത്രയിൽ അടുത്ത ഘട്ടത്തിൽ എങ്ങനെ സഹായിക്കാനാകും?"
                        )
                    else:
                        return (
                            f"🎉 Hello {self.current_lead.name}! I am now your personalized version of LevelX AI, exclusively customized for you!\n\n"
                            f"Based on your survey responses, here are my recommendations:\n\n{recommendations}\n\n"
                            f"I'm now fully personalized to your background and goals. Feel free to ask me anything about courses, career advice, or learning paths - "
                            f"I'll tailor everything specifically for your journey as a {self.current_lead.survey_answers.get('q1', 'professional')} "
                            f"working toward your goals!\n\n"
                            f"How can I help you take the next step in your learning journey?"
                        )
                else:
                    self.lead_status = LeadStatus.LEAD_COMPLETE
                    if language == 'malayalam':
                        return (
                            f"അതിശയിക്കാം, {self.current_lead.name}! നിങ്ങളുടെ വിവരങ്ങൾ സുരക്ഷിതമായി രേഖപ്പെടുത്തിയിരിക്കുന്നു.\n\n"
                            f"ഞങ്ങളുടെ ടീമിലെ ഒരു അംഗം 24 മണിക്കൂറിനുള്ളിൽ നിങ്ങളെ ബന്ധപ്പെടും. "
                            f"LEVELX-ൽ നിങ്ങൾക്കുള്ള താൽപ്പര്യത്തിന് നന്ദി!"
                        )
                    else:
                        return (
                            f"Excellent, {self.current_lead.name}! I have securely logged your information.\n\n"
                            f"A member of our team will reach out to you within 24 hours. "
                            f"Thank you for your interest in LEVELX!"
                        )
            else:
                if language == 'malayalam':
                    return "ആ സന്ദേശത്തിൽ ഒരു സാധുവായ ഇമെയിൽ കണ്ടെത്താൻ കഴിഞ്ഞില്ല. ദയവായി നിങ്ങളുടെ ഇമെയിൽ വിലാസം നൽകാമോ?"
                else:
                    return "I couldn't find a valid email in that message. Could you please provide your email address?"
        
        return None

    def _update_to_personalized_mode(self):
        """Updates the RAG chain to use personalized prompts"""
        try:
            # Create new personalized prompt template
            personalized_template = self._create_personalized_prompt_template()
            
            # Update the chain's prompt
            new_prompt = PromptTemplate(
                template=personalized_template,
                input_variables=["context", "question", "chat_history", "language"]
            )
            
            # Recreate the chain with updated prompt and increased context retrieval
            # Create a retriever with increased k value
            retriever_with_more_docs = self.rag_chain.retriever.with_search_kwargs({"k": 5})
            
            self.rag_chain = ConversationalRetrievalChain.from_llm(
                llm=self.llm,
                retriever=retriever_with_more_docs,
                memory=self.rag_chain.memory,
                combine_docs_chain_kwargs={"prompt": new_prompt},
                return_source_documents=True,
                # Increase context retrieval for better personalization
                max_tokens_limit=2000
            )
            
            logger.info(f"✅ Updated to personalized mode for {self.current_lead.name}")
            
        except Exception as e:
            logger.error(f"Error updating to personalized mode: {e}")


    def _save_lead_to_airtable(self):
        """Saves the collected lead data to Airtable and Google Sheets."""
        # Always save user to Google Sheets users_sheet first
        if self.current_lead.name and self.current_lead.phone:
            logger.info(f"💾 Saving user {self.current_lead.name} to users sheet...")
            self.save_user_to_sheets(
                name=self.current_lead.name,
                phone_number=self.current_lead.phone
            )
        
        # Save to Google Sheets survey_sheet if survey was completed
        if (self.current_lead.name and self.current_lead.email and 
            any(self.current_lead.survey_answers.values())):
            logger.info(f"📋 Saving survey data for {self.current_lead.name} to survey sheet...")
            success = self.save_survey_to_sheets(
                name=self.current_lead.name,
                phone_number=self.current_lead.phone,
                email=self.current_lead.email,
                survey_answers=self.current_lead.survey_answers
            )
            if success:
                logger.info(f"✅ Survey data successfully saved to Google Sheets for {self.current_lead.name}")
            else:
                logger.error(f"❌ Failed to save survey data to Google Sheets for {self.current_lead.name}")
        
        # Save to Airtable (existing functionality)
        if not hasattr(self, 'airtable_manager') or not self.airtable_manager:
            logger.warning("Airtable not configured. Logging lead locally.")
            logger.info(f"📝 LOCAL LEAD: Name={self.current_lead.name}, Phone={self.current_lead.phone}, Email={self.current_lead.email}")
            logger.info(f"📋 Survey Answers: {json.dumps(self.current_lead.survey_answers, indent=2)}")
            return
        
        if self.current_lead.name:
            self.airtable_manager.create_lead(self.current_lead)
        else:
            logger.error("Cannot save lead: No name was provided.")

    def _set_language_preference(self, question: str) -> str:
        """Sets user's preferred language for the conversation"""
        question_lower = question.lower().strip()
        if any(word in question_lower for word in ['malayalam', 'മലയാളം']):
            self.preferred_language = 'malayalam'
            self.language_selected = True
            return ("ഭാഷ മലയാളത്തിലേക്ക് ലോക്ക് ചെയ്തിരിക്കുന്നു.\n\n"
                    "ഭാഷ മാറ്റണമെങ്കിൽ 'switch to english' എന്ന് ടൈപ്പ് ചെയ്യുക.\n\n"
                    "എന്തെങ്കിലും ചോദിക്കാൻ താൽപ്പര്യമുണ്ടോ?")
        else:
            self.preferred_language = 'english'
            self.language_selected = True
            return ("Language locked to English.\n\n"
                    "To switch language, type 'switch to malayalam'.\n\n"
                    "How may I assist you today?")

    def ask(self, question: str) -> str:
        """Processes user questions with language preference handling"""
        if not question.strip():
            return "Please ask a question."
        
        try:
            # Initial language selection
            if not self.language_selected:
                return ("Welcome to LevelX AI! Please select your preferred language:\n\n"
                       "ലെവൽ-X AI-ലേക്ക് സ്വാഗതം! നിങ്ങൾക്ക് ഇഷ്ടമുള്ള ഭാഷ തിരഞ്ഞെടുക്കൂ:\n\n"
                       "1. English\n"
                       "2. മലയാളം (Malayalam)\n\n"
                       "Please type 'English' or 'Malayalam'")
            
            # Handle language switching request
            if "switch to" in question.lower():
                if "english" in question.lower() and self.preferred_language != 'english':
                    return self._set_language_preference("english")
                elif "malayalam" in question.lower() and self.preferred_language != 'malayalam':
                    return self._set_language_preference("malayalam")
                else:
                    return "That language is already selected." if self.preferred_language == 'english' else "ആ ഭാഷ നിലവിൽ തിരഞ്ഞെടുത്തിരിക്കുന്നു."
            
            # Skip RAG processing if we're collecting email and input looks like an email
            if self.lead_status == LeadStatus.COLLECTING_EMAIL and '@' in question and '.' in question.split('@')[-1]:
                logger.info("Email detected during lead collection, bypassing RAG processing")
                lead_response = self._handle_lead_collection(question)
                if lead_response:
                    return lead_response
                return "Thank you! Your information has been saved." if self.preferred_language == 'english' \
                        else "നന്ദി! നിങ്ങളുടെ വിവരങ്ങൾ സംരക്ഷിച്ചിരിക്കുന്നു."
            
            # Process lead collection and RAG pipeline with preferred language
            try:
                lead_response = self._handle_lead_collection(question)
                if lead_response:
                    return lead_response
            except Exception as lead_error:
                logger.error(f"Error in lead collection: {lead_error}")
        
            # Process through RAG pipeline only if not in email collection state
            logger.info(f"Processing question with RAG chain: {question}")
            result = self._invoke_rag_chain_with_language(question, self.preferred_language or 'english')
            response = result.get('answer', "I'm sorry, I encountered an issue. Please try again.")

            # Fallback: If the user is asking about courses and the answer does not mention at least two course names, append the course list
            course_keywords_en = ["course", "courses", "program", "programs", "learning path"]
            course_keywords_ml = ["കോഴ്‌സ്", "കോഴ്‌സുകൾ", "പഠനം", "പാഠ്യക്രമം", "പാഠ്യക്രമങ്ങൾ", "കോഴ്സ്", "കോഴ്സുകൾ", "ട്രെയിനിംഗ്", "പ്രോഗ്രാം", "പ്രോഗ്രാമുകൾ", "എന്താണ് പഠിപ്പിക്കുന്നത്", "എന്ത് കോഴ്സുകൾ"]
            course_list_en = [
                "Full Stack Development",
                "Flutter Development",
                "Data Science",
                "Digital Marketing"
            ]
            course_list_ml = [
                "ഫുൾ സ്റ്റാക്ക് ഡെവലപ്പ്മെന്റ്",
                "ഫ്ലട്ടർ ഡെവലപ്പ്മെന്റ്",
                "ഡാറ്റാ സയൻസ്",
                "ഡിജിറ്റൽ മാർക്കറ്റിംഗ്"
            ]
            # Detect if the question is about courses
            is_course_query = False
            if self.preferred_language == 'malayalam':
                is_course_query = any(kw in question for kw in course_keywords_ml)
                course_names = course_list_ml
                logger.info(f"🔍 Malayalam course detection: question='{question[:50]}...', is_course_query={is_course_query}")
            else:
                is_course_query = any(kw in question.lower() for kw in course_keywords_en)
                course_names = course_list_en
                logger.info(f"🔍 English course detection: question='{question[:50]}...', is_course_query={is_course_query}")
            
            # Check if at least two course names are in the response
            found_courses = [c for c in course_names if c in response]
            logger.info(f"🔍 Found courses in response: {found_courses} (need at least 2)")
            
            if is_course_query and len(found_courses) < 2:
                logger.info(f"✅ Replacing generic response with course list (language: {self.preferred_language})")
                if self.preferred_language == 'malayalam':
                    response = "LevelX-ൽ ലഭ്യമായ പ്രധാന കോഴ്‌സുകൾ:\n" + "\n".join(course_list_ml)
                else:
                    response = "Main courses available at LevelX:\n" + "\n".join(course_list_en)
            else:
                logger.info(f"❌ Not replacing response: is_course_query={is_course_query}, found_courses_count={len(found_courses)}")

            if self.preferred_language == 'malayalam' and "I don't have specific information" in response:
                response = "ഇതിനെക്കുറിച്ചുള്ള കൃത്യമായ വിവരങ്ങൾ എന്റെ ഡാറ്റാബേസിൽ ലഭ്യമല്ല."

            return response
            
        except Exception as e:
            logger.error(f"Critical error in ask method: {e}")
            return "I apologize, but I've encountered an unexpected error. Please try again later."

    def get_lead_status(self):
        """Returns the current lead collection status for debugging."""
        return {
            "status": self.lead_status.value,
            "lead_data": {
                "name": self.current_lead.name,
                "phone": self.current_lead.phone,
                "email": self.current_lead.email,
                "role": self.current_lead.role,
                "tech_background": self.current_lead.tech_background,
                "motivation": self.current_lead.motivation_to_tech,
                "interest": self.current_lead.area_of_interest
            },
            "survey_config": SURVEY_CONFIG
        }

    def get_survey_config_json(self):
        """Returns the survey configuration in JSON format"""
        return json.dumps(SURVEY_CONFIG, indent=2)
    
    def reset_state(self):
        """Reset the chatbot state to initial state"""
        self.lead_status = LeadStatus.NO_INTENT
        self.current_lead = LeadData()
        if hasattr(self.rag_chain, 'memory') and hasattr(self.rag_chain.memory, 'chat_memory'):
            self.rag_chain.memory.chat_memory.clear()
        logger.info("🔄 ChatBot state reset to initial state")
    
    def save_user_to_sheets(self, name, phone_number):
        """Save user data to Google Sheets users_sheet"""
        if not hasattr(self, 'sheets_manager') or not self.sheets_manager:
            logger.warning("Google Sheets manager not available")
            return False
        
        try:
            success = self.sheets_manager.add_user(name, phone_number)
            if success:
                logger.info(f"✅ User {name} ({phone_number}) saved to users sheet")
            return success
        except Exception as e:
            logger.error(f"❌ Failed to save user to sheets: {e}")
            return False
    
    def save_survey_to_sheets(self, name, phone_number, email, survey_answers):
        """Save survey response to Google Sheets survey_sheet - interest score will be calculated from conversation analysis"""
        if not hasattr(self, 'sheets_manager') or not self.sheets_manager:
            logger.warning("Google Sheets manager not available")
            return False
        
        try:
            # Extract survey answers
            role = survey_answers.get('q1', 'Not provided')
            tech_background = survey_answers.get('q2', 'Not provided')
            motivation_to_tech = survey_answers.get('q3', 'Not provided')
            area_of_interest = survey_answers.get('q4', 'Not provided')
            
            # Note: Interest score will be calculated later from full conversation analysis
            # We save survey without interest score initially - leave blank until analysis runs
            success = self.sheets_manager.add_survey_response(
                name=name,
                phone_number=phone_number,
                email=email,
                role=role,
                tech_background=tech_background,
                motivation_to_tech=motivation_to_tech,
                area_of_interest=area_of_interest
            )
            
            if success:
                logger.info(f"✅ Survey response for {name} ({phone_number}) saved to survey sheet - interest score will be calculated from conversation analysis")
            return success
        except Exception as e:
            logger.error(f"❌ Failed to save survey to sheets: {e}")
            return False
    
    def get_sheets_stats(self):
        """Get statistics from Google Sheets"""
        if not hasattr(self, 'sheets_manager') or not self.sheets_manager:
            return {"error": "Google Sheets manager not available"}
        
        try:
            user_count = self.sheets_manager.get_user_count()
            survey_count = self.sheets_manager.get_survey_count()
            
            return {
                "total_users": user_count,
                "total_surveys": survey_count,
                "conversion_rate": f"{(survey_count/user_count*100):.1f}%" if user_count > 0 else "0%"
            }
        except Exception as e:
            logger.error(f"Error getting sheets stats: {e}")
            return {"error": str(e)}
    
    def _calculate_survey_interest_score(self, survey_answers):
        """
        Calculate interest score based on survey responses
        Returns tuple: (interest_score, summary)
        """
        try:
            score = 50  # Base score
            factors = []
            
            # Q1: Role analysis
            role = survey_answers.get('q1', '').lower()
            if 'student' in role:
                score += 15
                factors.append("Student background (+15)")
            elif 'working professional' in role:
                score += 10
                factors.append("Working professional (+10)")
            elif 'other' in role:
                score += 5
                factors.append("Other background (+5)")
            
            # Q2: Tech background
            tech_bg = survey_answers.get('q2', '').lower()
            if 'yes' in tech_bg or 'അതെ' in tech_bg:
                score += 20
                factors.append("Has tech background (+20)")
            elif 'no' in tech_bg or 'അല്ല' in tech_bg:
                score += 10
                factors.append("No tech background, learning opportunity (+10)")
            
            # Q3: Motivation analysis
            motivation = survey_answers.get('q3', '').lower()
            if any(word in motivation for word in ['career change', 'കരിയർ മാറ്റം']):
                score += 25
                factors.append("Career change motivation (+25)")
            elif any(word in motivation for word in ['higher salary', 'ഉയർന്ന ശമ്പളം']):
                score += 20
                factors.append("Salary improvement motivation (+20)")
            elif any(word in motivation for word in ['freelancing', 'ഫ്രീലാൻസിംഗ്']):
                score += 15
                factors.append("Freelancing interest (+15)")
            elif any(word in motivation for word in ['passion', 'താൽപര്യം']):
                score += 30
                factors.append("Passion-driven motivation (+30)")
            
            # Q4: Area of interest
            interest = survey_answers.get('q4', '').lower()
            if any(word in interest for word in ['full stack flutter', 'full stack react']):
                score += 25
                factors.append("High-demand tech skill interest (+25)")
            elif 'digital marketing' in interest:
                score += 20
                factors.append("Digital marketing interest (+20)")
            elif 'data science' in interest:
                score += 25
                factors.append("Data science interest (+25)")
            elif any(word in interest for word in ['not sure', 'ഉറപ്പില്ല', 'തീർച്ചയല്ല']):
                score += 5
                factors.append("Exploring options (+5)")
            
            # Cap the score between 0-100
            score = max(0, min(100, score))
            
            # Create summary
            summary = f"Survey-based interest score: {score}/100. " + "; ".join(factors[:3])
            if len(factors) > 3:
                summary += f" and {len(factors)-3} more factors"
            
            logger.info(f"📊 Survey interest calculation: {score}/100 - {summary}")
            return score, summary
            
        except Exception as e:
            logger.error(f"❌ Error calculating survey interest score: {e}")
            return 60, f"Default survey interest score due to calculation error: {str(e)[:50]}"
    
    def end_session_with_analysis(self, survey_completed=None):
        """
        Analyze the entire conversation and save interest score/summary to Google Sheets
        
        Args:
            survey_completed: Boolean indicating if survey was completed (passed from session data)
        """
        try:
            # Get comprehensive conversation history from memory
            conversation_history = []
            user_message_count = 0
            bot_message_count = 0
            
            if hasattr(self.rag_chain, 'memory') and hasattr(self.rag_chain.memory, 'chat_memory'):
                messages = self.rag_chain.memory.chat_memory.messages
                for message in messages:
                    if hasattr(message, 'content') and message.content.strip():
                        # Identify if it's a user or bot message
                        if hasattr(message, 'type'):
                            if message.type == 'human':
                                conversation_history.append(f"USER: {message.content}")
                                user_message_count += 1
                            elif message.type == 'ai':
                                conversation_history.append(f"BOT: {message.content}")
                                bot_message_count += 1
                        else:
                            # Fallback - add all messages
                            conversation_history.append(message.content)
            
            # If no conversation history, return default low interest
            if not conversation_history:
                logger.warning("No conversation history found for analysis")
                return {
                    'interest_score': 15,
                    'summary': 'No conversation history available for analysis - user may have just started interaction'
                }
            
            # Create comprehensive conversation text (use more messages for better analysis)
            conversation_text = "\n".join(conversation_history[-30:])  # Last 30 messages for better context
            
            logger.info(f"📊 Analyzing conversation: {user_message_count} user messages, {bot_message_count} bot messages, {len(conversation_history)} total messages")
            
            analysis_prompt = f"""
            Analyze this entire WhatsApp conversation to determine the user's interest level in LevelX tech courses and provide a comprehensive interest score (0-100).
            
            CONVERSATION ANALYSIS:
            {conversation_text}
            
            SCORING CRITERIA (Focus on conversation behavior, not just survey):
            
            HIGH INTEREST INDICATORS (70-100):
            - Asked multiple questions about courses, fees, placement, career prospects
            - Showed enthusiasm with positive language ("great", "interested", "excited")
            - Requested specific information about curriculum, duration, certification
            - Asked about admission process, next steps, or enrollment
            - Engaged in back-and-forth conversation for extended period
            - Asked about job guarantees, salary packages, or career outcomes
            - Showed urgency ("when can I start", "how soon", "available seats")
            
            MODERATE INTEREST INDICATORS (40-69):
            - Responded to questions but didn't ask many follow-ups
            - Showed some interest but remained cautious or hesitant
            - Asked basic questions about courses but didn't dive deep
            - Completed survey but conversation was brief
            - Mixed signals - interested but concerned about time/money
            
            LOW INTEREST INDICATORS (0-39):
            - Very short responses, minimal engagement
            - Didn't ask questions about courses or career prospects
            - Seemed distracted or uninterested in course details
            - Only responded when directly asked, no proactive questions
            - Conversation ended quickly without exploring options
            
            ANALYZE THE ENTIRE CONVERSATION FLOW:
            - How many messages did the user send?
            - What types of questions did they ask?
            - Did they show enthusiasm or hesitation?
            - How engaged were they throughout the conversation?
            - Did they ask about practical details (fees, duration, placement)?
            - What was their overall tone and engagement level?
            
            User Profile Context:
            - Name: {self.current_lead.name or 'Not provided'}
            - Phone: {self.current_lead.phone or 'Not provided'}
            
            Provide response in this exact format:
            INTEREST_SCORE: [0-100]
            SUMMARY: [2-3 sentence summary focusing on conversation engagement, questions asked, and overall interest level demonstrated through the entire chat]
            """
            
            # Get analysis from LLM
            try:
                response = self.llm.invoke(analysis_prompt)
                analysis_text = response.content if hasattr(response, 'content') else str(response)
                
                # Parse the response
                interest_score = 50  # Default
                summary = "User showed moderate interest in tech courses"
                
                lines = analysis_text.split('\n')
                for line in lines:
                    if line.startswith('INTEREST_SCORE:'):
                        try:
                            score_str = line.split(':')[1].strip()
                            interest_score = max(0, min(100, int(score_str)))
                        except:
                            pass
                    elif line.startswith('SUMMARY:'):
                        summary = line.split(':', 1)[1].strip()
                
                logger.info(f"📊 Conversation analysis: Score {interest_score}/100")
                logger.info(f"📝 Summary: {summary}")
                
                # Save to Google Sheets if we have user data
                if self.current_lead.phone and hasattr(self, 'sheets_manager') and self.sheets_manager:
                    try:
                        # Update user sheet with interest score
                        self.sheets_manager.update_user_interest(
                            phone_number=self.current_lead.phone,
                            interest_score=interest_score,
                            summary=summary
                        )
                        
                        # Update survey sheet with interest score if survey was completed
                        logger.info(f"🔍 Survey update check - lead_status: {self.lead_status}, survey_completed: {hasattr(self, 'survey_completed') and self.survey_completed}")
                        logger.info(f"🔍 Current lead name: {self.current_lead.name if self.current_lead else 'None'}")
                        
                        # Check if survey was completed (regardless of lead status)
                        survey_completed = (hasattr(self, 'survey_completed') and self.survey_completed) or self.lead_status == LeadStatus.LEAD_COMPLETE
                        
                        if survey_completed:
                            logger.info(f"✅ Survey completed - updating survey sheet for {self.current_lead.name}")
                            try:
                                self.sheets_manager.update_survey_interest(
                                    phone_number=self.current_lead.phone,
                                    interest_score=interest_score,
                                    summary=summary,
                                    name=self.current_lead.name  # Add name parameter for survey sheet matching
                                )
                                logger.info(f"✅ Survey sheet updated successfully for {self.current_lead.name}")
                            except Exception as survey_error:
                                logger.error(f"❌ Failed to update survey sheet: {survey_error}")
                        else:
                            logger.warning(f"⚠️ Survey sheet not updated - lead_status is {self.lead_status}, not LEAD_COMPLETE")
                        
                        logger.info(f"✅ Interest score saved to Google Sheets for {self.current_lead.phone}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save interest score to sheets: {e}")
                
                return {
                    'interest_score': interest_score,
                    'summary': summary
                }
                
            except Exception as e:
                logger.error(f"❌ Error during LLM analysis: {e}")
                return {
                    'interest_score': 30,
                    'summary': f'Analysis error occurred: {str(e)[:100]}'
                }
                
        except Exception as e:
            logger.error(f"❌ Error in end_session_with_analysis: {e}")
            return {
                'interest_score': 20,
                'summary': f'Session analysis failed: {str(e)[:100]}'
            }

# --- Main Execution Block ---
if __name__ == "__main__":
    try:
        chatbot = ChatBot()
        print("\n--- LEVELX AI Assistant with Personalized Survey ---")
        print("Type 'exit' to end, 'debug' for history, 'leads' for status, or 'survey-config' for survey JSON.\n")
      
        while True:
            try:
                user_question = input("Your Question: ")
                
                if user_question.lower() == 'exit':
                    print("Thank you for chatting with LEVELX. Have a great day!")
                    break
                elif user_question.lower() == 'debug':
                    try:
                        if hasattr(chatbot.rag_chain, 'memory') and hasattr(chatbot.rag_chain.memory, 'chat_memory'):
                            history = chatbot.rag_chain.memory.chat_memory.messages
                            if history:
                                print(f"\n--- Conversation History ({len(history)} messages) ---")
                                for i, msg in enumerate(history):
                                    print(f"{i+1}. {msg.type}: {msg.content[:100]}...")
                            else:
                                print("\n--- No conversation history yet ---")
                        else:
                            print("\n--- Conversation history not available ---")
                    except Exception as e:
                        print(f"\n--- Error accessing conversation history: {e} ---")
                    continue
                elif user_question.lower() == 'leads':
                    status = chatbot.get_lead_status()
                    print("\n--- Lead Collection Status ---")
                    print(json.dumps(status, indent=2))
                    continue
                elif user_question.lower() == 'survey-config':
                    print("\n--- Survey Configuration JSON ---")
                    print(chatbot.get_survey_config_json())
                    continue
                elif user_question.lower() == 'analyze':
                    print("\n--- Analyzing Conversation Interest ---")
                    score, summary = chatbot.analyze_conversation_interest()
                    print(f"Interest Score: {score}/100")
                    print(f"Summary: {summary}")
                    continue
                elif user_question.lower() == 'end-session':
                    print("\n--- Ending Session with Analysis ---")
                    result = chatbot.end_session_with_analysis()
                    if result:
                        print(f"Session ended for: {result['user']} ({result['phone']})")
                        print(f"Interest Score: {result['interest_score']}/100")
                        print(f"Summary: {result['summary']}")
                    else:
                        print("Failed to end session with analysis")
                    continue
                
                # Process the question and handle language selection
                if not chatbot.language_selected:
                    response = chatbot._set_language_preference(user_question)
                    print(f"\nLEVELX AI: {response}\n")
                else:
                    answer = chatbot.ask(user_question)
                    print(f"\nLEVELX AI: {answer}\n")

            except Exception as loop_error:
                logger.error(f"Error processing input: {loop_error}")
                print("\nLEVELX AI: I encountered an error. Please try again.\n")
                continue

    except Exception as e:
        print(f"❌ A critical error occurred: {e}")
        logger.error(f"Critical error in main execution: {e}")