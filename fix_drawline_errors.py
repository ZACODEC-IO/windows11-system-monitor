"""
Fix floating point errors in drawLine calls in system_monitor.py
"""

import re
import sys
import os

def fix_float_errors(file_path):
    print(f"Processing {file_path}...")
    
    # Read the file content
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Regular expression to find drawLine with floating point arguments
    pattern = r'painter\.drawLine\((.*?)\)'
    
    def replace_with_int(match):
        args = match.group(1)
        # Split by commas
        parts = args.split(',')
        # Add int() around expressions that might be float
        new_parts = []
        for part in parts:
            if '/' in part or '+' in part or '-' in part:
                new_parts.append(f"int({part.strip()})")
            else:
                new_parts.append(part)
        return f'painter.drawLine({", ".join(new_parts)})'
    
    # Replace all instances
    modified_content = re.sub(pattern, replace_with_int, content)
    
    # Check if any changes were made
    if content != modified_content:
        # Write the modified content back to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(modified_content)
        print("Fixed drawLine calls with int() conversions.")
    else:
        print("No drawLine calls needed fixing.")

if __name__ == '__main__':
    file_path = 'system_monitor.py'
    if os.path.exists(file_path):
        fix_float_errors(file_path)
    else:
        print(f"Error: File {file_path} not found.")
        sys.exit(1)