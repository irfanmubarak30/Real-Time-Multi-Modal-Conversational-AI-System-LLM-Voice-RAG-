#!/usr/bin/env python3
"""
Test script to verify the fix for the personalized mode error
"""

import sys
import os
sys.path.append('src')

from levelx import ChatBot, LeadStatus

def test_personalized_mode():
    """Test that personalized mode works correctly"""
    print("🧪 Testing Personalized Mode Fix")
    print("=" * 50)
    
    try:
        # Initialize chatbot
        chatbot = ChatBot()
        
        # Test 1: Set language to English
        print("\n1. Setting language to English...")
        chatbot.preferred_language = "english"
        print(f"Language: {chatbot.preferred_language}")
        
        # Test 2: Simulate survey completion
        print("\n2. Simulating survey completion...")
        # Set some test data
        chatbot.current_lead.name = "Test User"
        chatbot.current_lead.phone = "+1234567890"
        chatbot.current_lead.survey_answers = {
            "q1": "Software Developer",
            "q2": "Intermediate",
            "q3": "Career advancement",
            "q4": "AI and Machine Learning"
        }
        chatbot.current_lead.wants_personalized = True
        chatbot.lead_status = LeadStatus.PERSONALIZED_MODE
        
        # Test 3: Update to personalized mode
        print("\n3. Updating to personalized mode...")
        chatbot._update_to_personalized_mode()
        print("✅ Successfully updated to personalized mode")
        
        # Test 4: Test personalized response
        print("\n4. Testing personalized response...")
        test_question = "What courses do you recommend for me?"
        result = chatbot._invoke_rag_chain_with_language(test_question, 'english')
        print(f"Personalized Response: {result.get('answer', 'No response')}")
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_personalized_mode()