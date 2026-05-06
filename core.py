import os
import json
import random
import asyncio
import traceback
from groq import AsyncGroq
from config import DEFAULT_GIFS, HABIBI_PROMPT

# ========================================================================
# GLOBAL VARIABLES & THREAD LOCKS (Anti-Lag & Anti-Dupe)
# ========================================================================
DB_FILE = "database.json"
GIF_FILE = "gifs.json"

snipes = {}
edit_snipes = {}
xp_cooldown = set()

# Locks prevent two people from saving data at the exact same millisecond
db_lock = asyncio.Lock()
gif_lock = asyncio.Lock()

# ========================================================================
# ASYNC DATABASE ENGINE
# ========================================================================
def get_default_db():
    return {
        "warns": {}, "jailed": {}, 
        "config": {"filterwords": [], "ai_channel": None, "cmd_channel": None, "event_channel": None, "antiraid": False}, 
        "economy": {}, "levels": {}, "custom_commands": {}, "afk": {}, 
        "inventory": {}, "rep": {}, "bounties": {}, "current_shop": []
    }

def load_db_sync():
    """Loads database normally when the bot first boots up."""
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f: json.dump(get_default_db(), f)
    with open(DB_FILE, "r") as f: return json.load(f)

db = load_db_sync()

def _write_json(file, data):
    """Raw physical write function."""
    with open(file, "w") as f: json.dump(data, f, indent=4)

async def _async_save_db(data):
    """Waits in line (Lock), then writes to file in a background thread."""
    async with db_lock:
        await asyncio.to_thread(_write_json, DB_FILE, data)

def save_db(data):
    """🔥 THE MAGIC WRAPPER: Fire and forget! Allows cogs to save without freezing the bot."""
    asyncio.create_task(_async_save_db(data))


# ========================================================================
# ASYNC GIF LIBRARY SYSTEM (Upgraded to Named Dictionary Format)
# ========================================================================
def load_gifs_sync():
    if not os.path.exists(GIF_FILE):
        # Create fresh with Named Dicts instead of Lists
        named_defaults = {}
        for k, v_list in DEFAULT_GIFS.items():
            named_defaults[k] = {f"default_{i+1}": url for i, url in enumerate(v_list)}
        with open(GIF_FILE, "w") as f: 
            json.dump(named_defaults, f, indent=4)
            
    with open(GIF_FILE, "r") as f:
        data = json.load(f)
        
    # 🔥 MIGRATION PROTOCOL: Convert old lists to the new Named Dict format
    for cat, content in list(data.items()):
        if isinstance(content, list):
            data[cat] = {f"gif_{i+1}": url for i, url in enumerate(content)}
            
    # Ensure all default categories exist in case they were accidentally deleted
    for k, v_list in DEFAULT_GIFS.items():
        if k not in data or not data[k]:
            data[k] = {f"default_{i+1}": url for i, url in enumerate(v_list)}
            
    return data

gif_db = load_gifs_sync()

async def _async_save_gifs(data):
    async with gif_lock:
        await asyncio.to_thread(_write_json, GIF_FILE, data)

def save_gifs(data):
    asyncio.create_task(_async_save_gifs(data))

def get_gif(category):
    """Pulls a random URL from the dictionary of named gifs."""
    category_data = gif_db.get(category, {})
    if isinstance(category_data, dict) and category_data:
        return random.choice(list(category_data.values()))
    # Reverts to a funny "Image not found" gif if somehow empty
    return "https://media.giphy.com/media/Kx1nQEQigkUUM/giphy.gif"

def is_valid_gif(url):
    """
    STRICT VALIDATION: 
    Discord embeds will ONLY render links that end in .gif or point directly to a raw media CDN.
    Returns: (is_valid: bool, error_message: str)
    """
    url = url.lower().strip()
    if not url.startswith("http"): 
        return False, "❌ Invalid URL format. Must start with `http` or `https`."
        
    # Block common mistake: copying the webpage URL instead of the image URL
    if "tenor.com/view/" in url or "giphy.com/gifs/" in url:
        return False, "❌ **You pasted a Website Link!**\nRight-click the GIF and select **'Copy Image Address'** or **'Open Image in New Tab'**. The link MUST end in `.gif` or be a raw media URL (e.g., `media1.tenor.com/...`)."
        
    valid_cdns = ["media.tenor.com", "media1.tenor.com", "media.giphy.com", "cdn.discordapp.com", "i.imgur.com"]
    
    if url.endswith(".gif") or any(cdn in url for cdn in valid_cdns):
        return True, "Valid"
        
    return False, "❌ Invalid image link. The link MUST end in `.gif` or belong to a valid CDN."


# ========================================================================
# GROQ AI ENGINE (With Heavy Error Logging)
# ========================================================================
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
ai_client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

async def ask_groq(messages, inject_personality=True):
    if not ai_client: raise Exception("Groq API Key missing.")
    
    if inject_personality and messages[0].get("role") != "system":
        messages.insert(0, HABIBI_PROMPT)
    elif inject_personality and messages[0].get("role") == "system":
        messages[0] = HABIBI_PROMPT

    for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
        try: 
            res = await ai_client.chat.completions.create(model=model, messages=messages)
            return res.choices[0].message.content.strip()
        except Exception as e: 
            # 🔥 Proper Error Logging so you can debug the AI
            print(f"⚠️ [Groq AI Engine] Model {model} failed: {e}")
            continue 
            
    raise Exception("All AI models failed to respond.")
