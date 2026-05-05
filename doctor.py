import os
import re

print("🩺 Starting Bot Doctor Diagnostic Scan...\n")

commands_found = {}
duplicates = []

# Scan the cogs folder
if not os.path.exists('./cogs'):
    print("❌ Could not find 'cogs' folder.")
else:
    for filename in os.listdir('./cogs'):
        # Ignore backup files or non-python files
        if filename.endswith('.py'):
            with open(f'./cogs/{filename}', 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Regex to find command names like name="vibecheck" or name='urban'
                matches = re.findall(r'@commands\.(?:hybrid_command|hybrid_group|command)\(.*name=["\']([^"\']+)["\']', content)
                
                for cmd in matches:
                    if cmd in commands_found:
                        duplicates.append((cmd, filename, commands_found[cmd]))
                    else:
                        commands_found[cmd] = filename

    if duplicates:
        print("🚨 CRITICAL CONFLICTS FOUND! 🚨")
        print("Delete one of the duplicates so your bot can boot up:\n")
        for dup in duplicates:
            print(f"❌ Command '/{dup[0]}' is in BOTH '{dup[1]}' AND '{dup[2]}'")
    else:
        print("✅ SYSTEM CLEAN! No duplicate commands found. Your engine is ready to boot.")
