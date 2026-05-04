
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

# 🔥 NEW: Locks prevent two people from saving data at the exact same millisecond
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
# ASYNC GIF LIBRARY SYSTEM
# ========================================================================
def load_gifs_sync():
    if not os.path.exists(GIF_FILE):
        with open(GIF_FILE, "w") as f: json.dump(DEFAULT_GIFS, f, indent=4)
    with open(GIF_FILE, "r") as f:
        data = json.load(f)
        for k, v in DEFAULT_GIFS.items():
            if k not in data or not data[k]: data[k] = v.copy()
        return data

gif_db = load_gifs_sync()

async def _async_save_gifs(data):
    async with gif_lock:
        await asyncio.to_thread(_write_json, GIF_FILE, data)

def save_gifs(data):
    asyncio.create_task(_async_save_gifs(data))

def get_gif(category):
    lst = gif_db.get(category, [])
    return random.choice(lst) if lst else "https://media.giphy.com/media/Kx1nQEQigkUUM/giphy.gif"

def is_valid_gif(url):
    url = url.lower()
    if not url.startswith("http"): return False
    valid_domains = ["tenor.com", "giphy.com", "discordapp.com", "imgur.com"]
    return any(domain in url for domain in valid_domains) or url.endswith(".gif")


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
            # 🔥 NEW: Proper Error Logging so you can debug the AI
            print(f"⚠️ [Groq AI Engine] Model {model} failed: {e}")
            continue 
            
    raise Exception("All AI models failed to respond.")
