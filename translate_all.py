import os
import subprocess
import polib
from deep_translator import GoogleTranslator

# --- CONFIGURATION ---
# Languages: Amharic, Turkish, French, Arabic, Russian
LANGUAGES = ['am', 'tr', 'fr', 'ar', 'ru']
SOURCE_LANG = 'en'

def run_command(cmd):
    """Helper to run shell commands and catch errors."""
    try:
        print(f"Executing: {cmd}")
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        return False
    return True

def translate_po_files():
    """Loops through all languages, translates empty/fuzzy strings, and saves."""
    for lang in LANGUAGES:
        po_path = f'locale/{lang}/LC_MESSAGES/django.po'
        
        if not os.path.exists(po_path):
            print(f"!!! Skipping {lang.upper()}: Folder structure not found at {po_path}")
            continue

        po = polib.pofile(po_path)
        translator = GoogleTranslator(source=SOURCE_LANG, target=lang)

        print(f"\n--- [ {lang.upper()} ] AI Translation Processing ---")
        translated_count = 0
        unfuzzed_count = 0
        
        for entry in po:
            # Check if entry is empty OR marked as 'fuzzy'
            is_fuzzy = 'fuzzy' in entry.flags
            is_empty = not entry.msgstr or entry.msgstr.strip() == ""

            if is_empty or is_fuzzy:
                try:
                    # 1. Get fresh translation from Google
                    translation = translator.translate(entry.msgid)
                    entry.msgstr = translation
                    
                    # 2. CRITICAL: Remove 'fuzzy' flag so Django doesn't ignore it
                    if is_fuzzy:
                        entry.flags.remove('fuzzy')
                        unfuzzed_count += 1
                    
                    translated_count += 1
                    print(f"  [OK] '{entry.msgid[:30]}...' -> '{translation[:30]}...'")
                except Exception as e:
                    print(f"  [ERROR] Translating '{entry.msgid}': {e}")
        
        # Save the updated .po file
        po.save()
        print(f"Done: {translated_count} translated, {unfuzzed_count} fuzzy flags cleared.")

if __name__ == "__main__":
    print("==============================================")
    print("ASORTIE LUXURY - AUTOMATED i18n SYSTEM")
    print("==============================================\n")

    # Step 1: Extract latest tags from HTML/Python
    # This finds all your {% trans %} tags
    if run_command("python manage.py makemessages -a"):

        # Step 2: AI Translation Logic
        translate_po_files()

        # Step 3: Compile into .mo binary files
        # This makes the translations "Live" for the web server
        print("\nFinal Step: Compiling to binary...")
        run_command("python manage.py compilemessages")
        
        print("\n==============================================")
        print("SUCCESS: All 5 languages are updated and LIVE.")
        print("==============================================")
