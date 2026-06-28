import json
import sys
import re

def main():
    print("--- PASTE HTML TABLE BELOW (Press Enter, then Ctrl+Z on Windows to finish) ---")
    html_content = sys.stdin.read()
    
    # Regex Strategy:
    # 1. Match the span containing the artist name
    # 2. Match the span containing the credits
    # This pattern forces the parser to capture them as a single 'unit' per row
    pattern = r'<span class="artist">\s*<a[^>]*>(.*?)</a>\s*</span>\s*<span class="artistCredits">(.*?)</span>'
    
    matches = re.findall(pattern, html_content, re.DOTALL)
    
    credits = []
    for name, role in matches:
        # Clean up any residual HTML if it slipped through
        clean_name = re.sub(r'<[^>]+>', '', name).strip()
        clean_role = re.sub(r'<[^>]+>', '', role).strip()
        
        credits.append({
            "name": clean_name,
            "role": clean_role
        })
    
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(credits, f, indent=4)
        
    print(f"\nSuccessfully extracted {len(credits)} credits to 'output.json'.")

if __name__ == "__main__":
    main()