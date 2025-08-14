import os
import json
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    """Manages Google Sheets operations for user and survey data storage"""
    
    def __init__(self, credentials_path=None, users_sheet_id=None, survey_sheet_id=None):
        """
        Initialize Google Sheets manager
        
        Args:
            credentials_path: Path to Google service account credentials JSON file
            users_sheet_id: Google Sheets ID for users sheet
            survey_sheet_id: Google Sheets ID for survey sheet
        """
        # Load environment variables
        load_dotenv()
        
        self.credentials_path = credentials_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'credentials', 
            'google-sheets-key.json'
        )
        
        # Get sheet IDs from environment variables if not provided
        self.users_sheet_id = users_sheet_id or os.getenv('USERS_SHEET_ID')
        self.survey_sheet_id = survey_sheet_id or os.getenv('SURVEY_SHEET_ID')
        
        if not self.users_sheet_id or not self.survey_sheet_id:
            missing = []
            if not self.users_sheet_id:
                missing.append('USERS_SHEET_ID')
            if not self.survey_sheet_id:
                missing.append('SURVEY_SHEET_ID')
            logger.warning(f"Missing Google Sheets environment variables: {', '.join(missing)}")
            logger.warning("Please add these to your .env file with your Google Sheet IDs")
            return
            
        self.client = None
        self.users_sheet = None
        self.survey_sheet = None
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Google Sheets client with service account credentials"""
        try:
            # Check if credentials file exists
            if not os.path.exists(self.credentials_path):
                logger.error(f"❌ Google service account credentials file not found: {self.credentials_path}")
                self.client = None
                return
            
            # Define the scope for Google Sheets API
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            logger.info(f"🔑 Loading Google credentials from: {self.credentials_path}")
            
            # Load credentials from service account file
            credentials = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=scope
            )
            
            # Initialize the client
            self.client = gspread.authorize(credentials)
            logger.info("🔗 Google Sheets client authorized successfully")
            
            # Open the sheets with retry logic
            if self.users_sheet_id:
                self.users_sheet = self._open_sheet_with_retry(self.users_sheet_id, "users")
            
            if self.survey_sheet_id:
                self.survey_sheet = self._open_sheet_with_retry(self.survey_sheet_id, "survey")
            
            # Fix headers to ensure clean column detection
            if self.users_sheet and self.survey_sheet:
                logger.info("🔧 Cleaning up sheet headers for proper column detection...")
                self.fix_sheet_headers()
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Sheets client: {e}")
            logger.error(f"💡 Make sure your service account has access to the sheets and the credentials file is valid")
            self.client = None
    
    def _open_sheet_with_retry(self, sheet_id, sheet_name, max_retries=3):
        """Open a sheet with retry logic to handle network issues"""
        import time
        
        for attempt in range(max_retries):
            try:
                sheet = self.client.open_by_key(sheet_id).sheet1
                logger.info(f"✅ Connected to {sheet_name} sheet: {sheet_id}")
                return sheet
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                    logger.warning(f"⚠️ Failed to open {sheet_name} sheet (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.info(f"🔄 Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Failed to open {sheet_name} sheet after {max_retries} attempts: {e}")
                    return None
        return None
    
    def add_user(self, name, phone_number):
        """
        Add a new user to the users sheet
        
        Args:
            name: User's name from WhatsApp
            phone_number: User's phone number from WhatsApp
        """
        if not self.users_sheet:
            logger.warning("Users sheet not available")
            return False
            
        try:
            # Check if user already exists
            if self._user_exists(phone_number):
                logger.info(f"User {phone_number} already exists in users sheet")
                return True
            
            # Add new user with current date
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row_data = [name or "Unknown", phone_number, current_date]
            self.users_sheet.append_row(row_data)
            logger.info(f"✅ Added user {name} ({phone_number}) to users sheet with date {current_date}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to add user to sheet: {e}")
            return False
    
    def _user_exists(self, phone_number):
        """Check if user already exists in users sheet"""
        try:
            # Get all phone numbers from column B (number column)
            phone_numbers = self.users_sheet.col_values(2)  # Column B
            return phone_number in phone_numbers
        except Exception as e:
            logger.error(f"Error checking if user exists: {e}")
            return False
    
    def update_user_interest(self, phone_number, interest_score, summary):
        """
        Update user's interest score and summary in the users sheet
        
        Args:
            phone_number: User's phone number to find the row
            interest_score: Interest score (0-100)
            summary: Brief summary of the analysis
        """
        if not self.users_sheet:
            logger.warning("Users sheet not available")
            return False
            
        try:
            # Get all phone numbers to find the user's row
            phone_numbers = self.users_sheet.col_values(2)  # Column B
            
            if phone_number not in phone_numbers:
                logger.warning(f"User {phone_number} not found in users sheet")
                return False
            
            # Find the row index (1-based)
            row_index = phone_numbers.index(phone_number) + 1
            
            # Get current headers to understand the structure
            headers = self.users_sheet.row_values(1) if self.users_sheet.row_values(1) else []
            logger.info(f"Current users sheet headers: {headers}")
            
            # Determine the correct columns for interest score and summary
            interest_score_col = None
            interest_summary_col = None
            
            # Check if interest_score and interest_summary columns already exist
            for i, header in enumerate(headers):
                if header == 'interest_score':
                    interest_score_col = chr(ord('A') + i)
                elif header == 'interest_summary':
                    interest_summary_col = chr(ord('A') + i)
            
            # If interest_score column doesn't exist, add it
            if not interest_score_col:
                next_col_index = len(headers)
                interest_score_col = chr(ord('A') + next_col_index)
                self.users_sheet.update(f'{interest_score_col}1', 'interest_score')
                logger.info(f"Added 'interest_score' to column {interest_score_col}")
                headers.append('interest_score')  # Update local headers list
            
            # If interest_summary column doesn't exist, add it
            if not interest_summary_col:
                next_col_index = len(headers)
                interest_summary_col = chr(ord('A') + next_col_index)
                self.users_sheet.update(f'{interest_summary_col}1', 'interest_summary')
                logger.info(f"Added 'interest_summary' to column {interest_summary_col}")
            
            # Update the user's interest score and summary using the correct columns
            logger.info(f"Updating interest score in column {interest_score_col}{row_index} and summary in column {interest_summary_col}{row_index}")
            logger.info(f"Interest score value: {interest_score} (type: {type(interest_score)})")
            logger.info(f"Summary value: {summary[:50]}... (type: {type(summary)})")
            
            try:
                # Update interest score
                result1 = self.users_sheet.update(f'{interest_score_col}{row_index}', [[str(interest_score)]])
                logger.info(f"Interest score update result: {result1}")
                
                # Update summary
                result2 = self.users_sheet.update(f'{interest_summary_col}{row_index}', [[str(summary)]])
                logger.info(f"Summary update result: {result2}")
                
            except Exception as update_error:
                logger.error(f"Detailed update error: {update_error}")
                # Try alternative update method
                try:
                    self.users_sheet.update_cell(row_index, ord(interest_score_col) - ord('A') + 1, str(interest_score))
                    self.users_sheet.update_cell(row_index, ord(interest_summary_col) - ord('A') + 1, str(summary))
                    logger.info("Successfully updated using update_cell method")
                except Exception as cell_error:
                    logger.error(f"Cell update also failed: {cell_error}")
                    raise
            
            logger.info(f"✅ Updated interest score {interest_score} for user {phone_number}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update user interest: {e}")
            return False
    
    def add_survey_response(self, name, phone_number, email, role, tech_background, motivation_to_tech, area_of_interest):
        """
        Add survey response to the survey sheet
        
        Args:
            name: User's name
            phone_number: User's phone number
            email: User's email
            role: User's role (student/professional/other)
            tech_background: Whether user has tech background
            motivation_to_tech: User's motivation to learn tech
            area_of_interest: User's area of interest
        """
        if not self.survey_sheet:
            logger.warning("Survey sheet not available")
            return False
            
        try:
            # Check if interest columns exist in survey sheet, if not create them
            headers = self.survey_sheet.row_values(1) if self.survey_sheet.row_values(1) else []
            
            # Expected headers for survey sheet (no interest columns)
            expected_headers = [
                'name', 'phone_number', 'email', 'role', 'tech_background', 
                'motivation_to_tech', 'area_of_interest', 'date_added', 'followup'
            ]
            
            # Add missing headers
            if len(headers) < len(expected_headers):
                # Update the header row with all expected headers
                header_range = f'A1:{chr(ord("A") + len(expected_headers) - 1)}1'
                self.survey_sheet.update(header_range, [expected_headers])
                logger.info("Updated survey sheet headers")
            
            # Add survey response with current date and interest data
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row_data = [
                name or "Unknown",
                phone_number,
                email or "",
                role or "",
                tech_background or "",
                motivation_to_tech or "",
                area_of_interest or "",
                current_date
            ]
            self.survey_sheet.append_row(row_data)
            logger.info(f"✅ Added survey response for {name} ({phone_number}) to survey sheet")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to add survey response: {e}")
            return False
    
    def update_survey_interest(self, phone_number, interest_score, summary, name=None):
        """
        Disabled: do not write interest to survey sheet
        
        Args:
            phone_number: User's phone number (for logging/fallback)
            interest_score: Interest score (0-100)
            summary: Brief summary of the analysis
            name: User's name to find the row (preferred method)
        """
        logger.info("Survey interest write is disabled; skipping.")
        return False
    
    def get_user_count(self):
        """Get total number of users in users sheet"""
        if not self.users_sheet:
            return 0
        try:
            return len(self.users_sheet.col_values(1)) - 1  # Subtract header row
        except Exception as e:
            logger.error(f"Error getting user count: {e}")
            return 0
    
    def get_survey_count(self):
        """Get total number of survey responses"""
        if not self.survey_sheet:
            return 0
        try:
            return len(self.survey_sheet.col_values(1)) - 1  # Subtract header row
        except Exception as e:
            logger.error(f"Error getting survey count: {e}")
            return 0
    
    def update_survey_followup_response_by_name(self, user_name, followup_response):
        """Update user's follow-up response in survey sheet by name"""
        if not self.survey_sheet:
            logger.warning("Survey sheet not available")
            return False
            
        try:
            # Find the user by name in survey sheet
            names = self.survey_sheet.col_values(1)  # Column A (names)
            
            for i, name in enumerate(names[1:], start=2):  # Skip header row
                if name == user_name:
                    # Update the follow-up response column (column 9 - 'followup')
                    self.survey_sheet.update_cell(i, 9, followup_response)
                    logger.info(f"✅ Updated follow-up response in survey sheet for {user_name}: {followup_response[:50]}...")
                    return True
            
            logger.warning(f"User with name {user_name} not found in survey sheet")
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to update follow-up response in survey sheet: {e}")
            return False
    
    def update_survey_followup_response(self, phone_number, followup_response):
        """Update user's follow-up response in survey sheet by phone number (fallback method)"""
        if not self.survey_sheet:
            logger.warning("Survey sheet not available")
            return False
            
        try:
            # Find the user by phone number in survey sheet
            phone_numbers = self.survey_sheet.col_values(2)  # Column B (phone numbers)
            
            for i, phone in enumerate(phone_numbers[1:], start=2):  # Skip header row
                if phone == phone_number:
                    # Update the follow-up response column (column 9 - 'followup')
                    self.survey_sheet.update_cell(i, 9, followup_response)
                    logger.info(f"✅ Updated follow-up response in survey sheet for {phone_number}: {followup_response[:50]}...")
                    return True
            
            logger.warning(f"User with phone {phone_number} not found in survey sheet")
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to update follow-up response in survey sheet: {e}")
            return False
    
    def update_followup_response(self, phone_number, followup_response):
        """Update user's follow-up response in users sheet (deprecated - use survey sheet instead)"""
        if not self.users_sheet:
            logger.warning("Users sheet not available")
            return False
            
        try:
            # Find the user by phone number
            phone_numbers = self.users_sheet.col_values(2)  # Column B (phone numbers)
            
            for i, phone in enumerate(phone_numbers[1:], start=2):  # Skip header row
                if phone == phone_number:
                    # Update the follow-up response column (column D)
                    self.users_sheet.update_cell(i, 4, followup_response)
                    logger.info(f"✅ Updated follow-up response for {phone_number}: {followup_response[:50]}...")
                    return True
            
            logger.warning(f"User with phone {phone_number} not found in users sheet")
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to update follow-up response: {e}")
            return False
    
    def setup_sheet_headers(self):
        """Setup headers for both sheets if they don't exist - NON-DESTRUCTIVE"""
        try:
            # Force header cleanup instead of just checking
            logger.info("🔧 Running header cleanup to ensure clean column detection...")
            self.fix_sheet_headers()
                    
        except Exception as e:
            logger.error(f"Error setting up sheet headers: {e}")
    
    def test_connection(self):
        """Test the connection to Google Sheets"""
        if not self.client:
            return False, "Google Sheets client not initialized"
        
        try:
            users_status = "✅ Connected" if self.users_sheet else "❌ Not connected"
            survey_status = "✅ Connected" if self.survey_sheet else "❌ Not connected"
            
            return True, f"Users Sheet: {users_status}, Survey Sheet: {survey_status}"
        except Exception as e:
            return False, f"Connection test failed: {e}"
    
    def fix_sheet_headers(self):
        """Fix and clean sheet headers to ensure proper column detection"""
        import time
        try:
            # Fix Users Sheet Headers
            if self.users_sheet:
                correct_users_headers = ['name', 'number', 'date', 'followup_response', 'interest_score', 'interest_summary']
                logger.info("🔧 Fixing users sheet headers...")
                
                # Clear and set correct headers
                header_range = f'A1:F1'
                self.users_sheet.update(header_range, [correct_users_headers])
                logger.info(f"✅ Users sheet headers fixed: {correct_users_headers}")
                
                # Small delay to ensure Google Sheets processes the update
                time.sleep(1)
            
            # Fix Survey Sheet Headers  
            if self.survey_sheet:
                # No interest columns in survey sheet
                correct_survey_headers = ['name', 'phone_number', 'email', 'role', 'tech_background', 'motivation_to_tech', 'area_of_interest', 'date_added', 'followup']
                logger.info("🔧 Fixing survey sheet headers...")
                
                # Clear and set correct headers
                header_range = f'A1:I1'
                self.survey_sheet.update(header_range, [correct_survey_headers])
                logger.info(f"✅ Survey sheet headers fixed: {correct_survey_headers}")

                # Explicitly clear any leftover header cells beyond I1 (e.g., old interest columns)
                try:
                    self.survey_sheet.update('J1:Z1', [["" for _ in range(17)]])
                except Exception as clear_err:
                    logger.warning(f"Could not clear extra survey header cells: {clear_err}")
                
                # Small delay to ensure Google Sheets processes the update
                time.sleep(1)
            
            # Verify headers were set correctly
            if self.users_sheet:
                verified_users_headers = self.users_sheet.row_values(1)
                logger.info(f"🔍 Verified users sheet headers: {verified_users_headers}")
                
            if self.survey_sheet:
                verified_survey_headers = self.survey_sheet.row_values(1)
                logger.info(f"🔍 Verified survey sheet headers: {verified_survey_headers}")
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to fix sheet headers: {e}")
            return False
