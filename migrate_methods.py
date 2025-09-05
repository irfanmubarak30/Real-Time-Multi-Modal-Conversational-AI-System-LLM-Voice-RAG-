#!/usr/bin/env python3
"""
Migration helper script to copy all missing WhatsAppBot methods from Flask to FastAPI.
This script extracts all methods from the original Flask app and helps complete the migration.
"""

import re
import os

def extract_whatsapp_bot_methods():
    """Extract all WhatsAppBot methods from the original Flask main.py"""
    
    flask_file = "src/main.py"
    if not os.path.exists(flask_file):
        print(f"Error: {flask_file} not found")
        return []
    
    with open(flask_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the WhatsAppBot class
    class_start = content.find("class WhatsAppBot:")
    if class_start == -1:
        print("Error: WhatsAppBot class not found")
        return []
    
    # Find where the class ends (look for Flask app initialization)
    app_start = content.find("app = Flask(__name__)")
    if app_start == -1:
        print("Error: Flask app initialization not found")
        return []
    
    class_content = content[class_start:app_start]
    
    # Extract all method definitions with their full bodies
    methods = []
    lines = class_content.split('\n')
    current_method = None
    method_lines = []
    indent_level = None
    
    for line in lines:
        # Check if this is a method definition
        if re.match(r'    def \w+\(', line):
            # Save previous method if exists
            if current_method and method_lines:
                methods.append((current_method, '\n'.join(method_lines)))
            
            # Start new method
            current_method = line.strip()
            method_lines = [line]
            indent_level = len(line) - len(line.lstrip())
        elif current_method:
            # Continue collecting method lines
            if line.strip() == '' or (line.startswith(' ' * (indent_level + 4)) and line.strip()):
                method_lines.append(line)
            elif line.startswith('    def ') or line.startswith('class ') or not line.startswith(' '):
                # End of current method
                methods.append((current_method, '\n'.join(method_lines)))
                current_method = None
                method_lines = []
                # Check if this line starts a new method
                if re.match(r'    def \w+\(', line):
                    current_method = line.strip()
                    method_lines = [line]
                    indent_level = len(line) - len(line.lstrip())
    
    # Add the last method if exists
    if current_method and method_lines:
        methods.append((current_method, '\n'.join(method_lines)))
    
    return methods

def create_async_method(method_signature, method_body):
    """Convert method to async if it makes HTTP requests"""
    
    # Methods that should be async (make HTTP requests)
    async_methods = [
        'send_whatsapp_message', 'send_media_message', 'send_document_message',
        'send_video_message', 'download_media_file_by_id', 'process_voice_message',
        'send_placement_images', 'send_fees_images', 'send_flutter_reel',
        'send_language_selection_buttons', 'transcribe_audio_whisper'
    ]
    
    method_name = method_signature.split('(')[0].replace('def ', '')
    
    if method_name in async_methods:
        # Convert to async
        async_signature = method_signature.replace('def ', 'async def ')
        # Replace requests calls with aiohttp equivalents in the body
        async_body = method_body.replace('requests.post(', 'await session.post(')
        async_body = async_body.replace('requests.get(', 'await session.get(')
        async_body = async_body.replace('resp = self._graph_post(', 'resp = await self._graph_post(')
        return f"{async_signature}\n{async_body}"
    else:
        return f"{method_signature}\n{method_body}"

def main():
    print("Flask to FastAPI Migration Helper")
    print("=================================")
    
    methods = extract_whatsapp_bot_methods()
    
    if not methods:
        print("No methods found to migrate")
        return
    
    print(f"Found {len(methods)} methods to migrate")
    
    # Create the missing methods file
    with open("src/whatsapp_bot_methods.py", 'w', encoding='utf-8') as f:
        f.write("# Missing WhatsAppBot methods for FastAPI migration\n")
        f.write("# Copy these methods into your main_fastapi.py WhatsAppBot class\n\n")
        
        for method_signature, method_body in methods:
            if 'def __init__(' in method_signature:
                continue  # Skip constructor as it's already handled
                
            async_method = create_async_method(method_signature, method_body)
            f.write(async_method)
            f.write("\n\n")
    
    print("Created src/whatsapp_bot_methods.py with all missing methods")
    print("\nNext steps:")
    print("1. Review the generated methods in whatsapp_bot_methods.py")
    print("2. Copy the methods into your main_fastapi.py WhatsAppBot class")
    print("3. Update any remaining synchronous HTTP calls to use aiohttp")
    print("4. Install dependencies: pip install -r requirements.txt")
    print("5. Test the migrated application: python start_fastapi.py")

if __name__ == "__main__":
    main()
