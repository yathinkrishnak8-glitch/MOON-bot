import discord
from discord import app_commands
from discord.ext import commands, tasks
from quart import Quart, request, session, jsonify, render_template_string
import os
import random
import time
import asyncio
import datetime
import re
import gc
import sys

# NEW GOOGLE SDK
from google import genai
from google.genai import types

# -------------------- Configuration & Globals --------------------
START_TIME = time.time()
TOTAL_QUERIES = 0
QUERY_TIMESTAMPS = [] 

# ASYNC TRAFFIC CONTROLLERS
ALERT_LOCK = asyncio.Lock()
LAST_ALERT_TIME = 0.0

# LOCAL RAM MEMORY (No Database)
CONFIG_CACHE = {
    'system_prompt': 'You are YoAI, a highly intelligent assistant.',
    'current_model': 'gemini-2.5-flash-lite',
    'global_personality': 'default',
    'status_type': 'watching',
    'status_text': 'over the Matrix',
    'response_delay': '0',
    'engine_status': 'online',
    'safety_hate': 'BLOCK_NONE',
    'safety_harassment': 'BLOCK_NONE',
    'safety_explicit': 'BLOCK_NONE',
    'safety_dangerous': 'BLOCK_NONE'
}

MESSAGE_HISTORY = {}   
ALLOWED_CHANNELS = set() 
CHANNEL_BUFFERS = {}
CHANNEL_TIMERS = {}

# MEMORY LEAK & RACE CONDITION CONTROLLERS
CHANNEL_LAST_ACTIVE = {}
CHANNEL_LOCKS = {}

GEMINI_KEYS = os.environ.get("GEMINI_API_KEYS", "").split(",")
if not GEMINI_KEYS or GEMINI_KEYS == [""]:
    raise ValueError("GEMINI_API_KEYS environment variable not set or empty")

FLASK_SECRET = os.environ.get("FLASK_SECRET", "yoai_persistent_secret_key_123")
PORT = int(os.environ.get("PORT", 5000))

# -------------------- Local Helper Functions --------------------
def get_channel_lock(channel_id: int):
    if channel_id not in CHANNEL_LOCKS:
        CHANNEL_LOCKS[channel_id] = asyncio.Lock()
    return CHANNEL_LOCKS[channel_id]

def get_config(key: str, default: str) -> str:
    return CONFIG_CACHE.get(key, default)

async def set_config(key: str, value: str):
    CONFIG_CACHE[key] = value

async def log_system_error(user: str, trace: str):
    print(f"⚠️ [SYSTEM ERROR] {user}: {trace}")

async def is_channel_allowed(guild_id: int, channel_id: int) -> bool:
    if guild_id is None: return True
    return (guild_id, channel_id) in ALLOWED_CHANNELS

async def toggle_channel(guild_id: int, channel_id: int, enable: bool):
    if enable:
        ALLOWED_CHANNELS.add((guild_id, channel_id))
    else:
        ALLOWED_CHANNELS.discard((guild_id, channel_id))

async def add_message_to_history(channel_id: int, message_id: int, author_id: int, content: str, timestamp: float):
    CHANNEL_LAST_ACTIVE[channel_id] = time.time()
    
    async with get_channel_lock(channel_id):
        if channel_id not in MESSAGE_HISTORY:
            MESSAGE_HISTORY[channel_id] = []
            
        for msg in MESSAGE_HISTORY[channel_id]:
            if msg['message_id'] == message_id:
                msg['content'] = content
                return
                
        MESSAGE_HISTORY[channel_id].append({
            'message_id': message_id,
            'author_id': author_id,
            'content': content,
            'timestamp': timestamp
        })
        
        MESSAGE_HISTORY[channel_id].sort(key=lambda x: x['timestamp'])
        
        if len(MESSAGE_HISTORY[channel_id]) > 15:
            oldest = MESSAGE_HISTORY[channel_id][:10]
            bot.loop.create_task(background_summarize(channel_id, oldest))

# -------------------- Smart Cluster Load Balancer --------------------
class GeminiKeyManager:
    def __init__(self, keys: list):
        self.key_objects = [{'index': i+1, 'name': k.split(":", 1)[0].strip() if ":" in k and not k.startswith("AIza") else f"Node {i+1}", 'key': k.split(":", 1)[1].strip() if ":" in k and not k.startswith("AIza") else k.strip()} for i, k in enumerate(keys) if k.strip()]
        self.key_mapping = {obj['key']: f"{obj['name']} ({obj['key'][:8]}...)" for obj in self.key_objects}
        self.all_keys = [obj['key'] for obj in self.key_objects]
        self.key_cooldowns = {k: 0.0 for k in self.all_keys}
        self.key_usage = {k: [] for k in self.all_keys} 
        self.current_key_idx = 0 
        self.dead_keys = set()
        self.lock = asyncio.Lock()
        
    def get_dynamic_safety(self):
        return [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=getattr(types.HarmBlockThreshold, get_config('safety_hate', 'BLOCK_NONE'))),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=getattr(types.HarmBlockThreshold, get_config('safety_harassment', 'BLOCK_NONE'))),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=getattr(types.HarmBlockThreshold, get_config('safety_explicit', 'BLOCK_NONE'))),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=getattr(types.HarmBlockThreshold, get_config('safety_dangerous', 'BLOCK_NONE'))),
        ]
    
    async def get_stats(self) -> dict:
        async with self.lock:
            now = time.time()
            total = len(self.all_keys)
            dead = len(self.dead_keys)
            cooldown = sum(1 for k in self.all_keys if k not in self.dead_keys and self.key_cooldowns[k] > now)
            active = total - dead - cooldown
            return {"total": total, "active": active, "cooldown": cooldown, "dead": dead}
            
    async def run_diagnostics(self) -> list:
        results = []
        now = time.time()
        for obj in self.key_objects:
            key = obj['key']
            masked_key = f"{key[:8]}•••••••••••••••••••••••••••••{key[-4:]}"
            try:
                client = genai.Client(api_key=key)
                await asyncio.wait_for(client.aio.models.generate_content(model='gemini-2.5-flash-lite', contents="ping"), timeout=15.0)
                async with self.lock:
                    if key in self.dead_keys: self.dead_keys.remove(key)
                    self.key_cooldowns[key] = 0.0
                    self.key_usage[key] = []
                results.append({"index": obj['index'], "name": obj['name'], "masked_key": masked_key, "status": "ONLINE", "detail": "Healthy & Ready", "unlock_time": 0, "color": "#10b981"})
            except Exception as e:
                error_msg = str(e).lower()
                async with self.lock:
                    if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg or "timeout" in error_msg:
                        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:s|sec|second)', error_msg)
                        cooldown_time = float(match.group(1)) + 2.0 if match else 60.0
                        unlock_epoch = now + cooldown_time
                        self.key_cooldowns[key] = unlock_epoch
                        self.key_usage[key] = []
                        results.append({"index": obj['index'], "name": obj['name'], "masked_key": masked_key, "status": "COOLDOWN", "detail": f"Rate Limited or Timeout", "unlock_time": unlock_epoch, "color": "#f59e0b"})
                    else:
                        self.dead_keys.add(key)
                        results.append({"index": obj['index'], "name": obj['name'], "masked_key": masked_key, "status": "DEAD", "detail": "Invalid Key", "unlock_time": 0, "color": "#ef4444"})
        return results

    async def generate_with_fallback(self, target_model: str, contents: list, system_instruction: str = None) -> str:
        fallback_models = list(dict.fromkeys([target_model, 'gemini-2.5-flash-lite', 'gemini-2.5-flash']))
        last_error = None
        dynamic_safety = self.get_dynamic_safety()
        
        for model_name in fallback_models:
            async with self.lock:
                now = time.time()
                available_keys = []
                for k in self.all_keys:
                    self.key_usage[k] = [ts for ts in self.key_usage[k] if now - ts < 60.0]
                    if k not in self.dead_keys and self.key_cooldowns[k] <= now and len(self.key_usage[k]) < 14:
                        available_keys.append(k)
                if not available_keys: raise Exception("Cascade Failure: All keys are exhausted (RPM Limit) or dead.")
                selected_keys = []
                for _ in range(len(self.all_keys)):
                    k = self.all_keys[self.current_key_idx % len(self.all_keys)]
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.all_keys)
                    if k in available_keys: selected_keys.append(k)
            
            for key in selected_keys:
                try:
                    async with self.lock: self.key_usage[key].append(time.time())
                    client = genai.Client(api_key=key)
                    config = types.GenerateContentConfig(system_instruction=system_instruction, safety_settings=dynamic_safety)
                    response = await asyncio.wait_for(client.aio.models.generate_content(model=model_name, contents=contents, config=config), timeout=30.0)
                    return response.text
                except Exception as e:
                    last_error = e
                    error_msg = str(e).lower()
                    async with self.lock:
                        if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg or "timeout" in error_msg:
                            match = re.search(r'(\d+(?:\.\d+)?)\s*(?:s|sec|second)', error_msg)
                            cooldown_time = float(match.group(1)) + 2.0 if match else 60.0
                            self.key_cooldowns[key] = time.time() + cooldown_time
                            self.key_usage[key] = []
                        elif "400" in error_msg or "403" in error_msg or "invalid" in error_msg:
                            self.dead_keys.add(key)
                    continue
        raise Exception(f"Cascade Failure Details: {str(last_error)}")

key_manager = GeminiKeyManager(GEMINI_KEYS)

# -------------------- Background Memory Compression (Local) --------------------
async def background_summarize(channel_id, oldest):
    texts = [f"User ID {row['author_id']}: {row['content']}" for row in oldest if row['author_id'] != 0]
    if not texts: return
    
    try:
        summary_text = await key_manager.generate_with_fallback('gemini-2.5-flash-lite', [f"Summarize concisely:\n{chr(10).join(texts)}"])
    except:
        summary_text = "[Summary unavailable]"
        
    oldest_ids = [row['message_id'] for row in oldest]
    timestamp = oldest[0]['timestamp']
    fake_msg_id = -int(time.time() * 1000) 
    
    async with get_channel_lock(channel_id):
        if channel_id in MESSAGE_HISTORY:
            MESSAGE_HISTORY[channel_id] = [msg for msg in MESSAGE_HISTORY[channel_id] if msg['message_id'] not in oldest_ids]
            MESSAGE_HISTORY[channel_id].insert(0, {
                'message_id': fake_msg_id,
                'author_id': 0,
                'content': summary_text,
                'timestamp': timestamp
            })

# -------------------- Discord Bot --------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

class YoAIBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print(f"[SYS] Engine online. Boot Auto-Sync disabled. Use !sync to register slash commands.")

bot = YoAIBot()

@tasks.loop(seconds=60)
async def status_loop():
    s_type = get_config('status_type', 'watching')
    s_text = get_config('status_text', 'over the Matrix')
    
    activity_type = discord.ActivityType.watching
    if s_type == 'playing': activity_type = discord.ActivityType.playing
    elif s_type == 'listening': activity_type = discord.ActivityType.listening
    elif s_type == 'competing': activity_type = discord.ActivityType.competing
    elif s_type == 'streaming': activity_type = discord.ActivityType.streaming
    
    engine_status = get_config('engine_status', 'online')
    if engine_status == 'offline':
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="[OFFLINE] Engine Sleeping"), status=discord.Status.dnd)
    else:
        await bot.change_presence(activity=discord.Activity(type=activity_type, name=s_text), status=discord.Status.online)

@tasks.loop(hours=1)
async def optimize_memory():
    # Garbage Collection: Deletes channel memory if inactive for 24 hours to prevent OOM crash
    print("[SYS] Running RAM Garbage Collection...")
    now = time.time()
    dead_channels = [cid for cid, last_active in CHANNEL_LAST_ACTIVE.items() if now - last_active > 86400] 
    for cid in dead_channels:
        MESSAGE_HISTORY.pop(cid, None)
        CHANNEL_LOCKS.pop(cid, None)
        CHANNEL_LAST_ACTIVE.pop(cid, None)
    gc.collect()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not status_loop.is_running(): status_loop.start()
    if not optimize_memory.is_running(): optimize_memory.start()

@bot.command(name="sync")
async def sync_cmds(ctx):
    # HARDCODED TO YOUR EXACT ID
    if ctx.author.id != 1285791141266063475: return
    await bot.tree.sync()
    await ctx.send("✅ Slash commands manually synchronized to Discord API.")

# -------------------- Slash Commands --------------------
class InfoView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.Button(label="Open Web Dashboard", style=discord.ButtonStyle.link, url="https://yoai-trio-apex.onrender.com"))

@bot.tree.command(name="info", description="Bot statistics and control panel.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def info(interaction: discord.Interaction):
    uptime = str(datetime.timedelta(seconds=int(time.time() - START_TIME))).split(".")[0]
    current_model = get_config('current_model', 'gemini-2.5-flash-lite')
    stats = await key_manager.get_stats()
    key_health = f"{stats['active']} Active | {stats['cooldown']} CD | {stats['dead']} Dead"
    
    embed = discord.Embed(title="🏎️ YoAI | Apex Engine 8.0 (Local-Web Hybrid)", color=0xff2a2a, description="Asynchronous Matrix System")
    embed.add_field(name="Ping", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="Uptime", value=uptime, inline=True)
    embed.add_field(name="Active Engine", value=f"`{current_model}`", inline=True)
    embed.add_field(name="Cluster Health", value=f"`{key_health}`", inline=True)
    embed.add_field(name="Total AI Queries", value=str(TOTAL_QUERIES), inline=True)
    embed.add_field(name="Architect", value="**mr_yaen (Yathin)**", inline=True)
    
    await interaction.response.send_message(embed=embed, view=InfoView())

@bot.tree.command(name="invite", description="Get the bot's invite link")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def invite_cmd(interaction: discord.Interaction):
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=0&scope=bot%20applications.commands"
    if interaction.guild:
        await interaction.response.send_message(f"👋 Leaving Matrix sector. Invite: {invite_url}")
        await interaction.guild.leave()
    else:
        await interaction.response.send_message(f"🔗 Invite: {invite_url}")

@bot.tree.command(name="toggle", description="[ADMIN] Toggle the Engine ON/OFF.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def toggle_cmd(interaction: discord.Interaction):
    if interaction.user.id != 1285791141266063475: return await interaction.response.send_message("⛔ Access Denied.", ephemeral=True)
    new_status = 'offline' if get_config('engine_status', 'online') == 'online' else 'online'
    await set_config('engine_status', new_status)
    await interaction.response.send_message(f"⚙️ Engine is now **{new_status.upper()}**.")
    await status_loop()

@bot.tree.command(name="time", description="Set delay (0=Normal, >0=Delay, -1=Instant/No Debouncer).")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def time_cmd(interaction: discord.Interaction, seconds: int):
    await set_config('response_delay', str(seconds))
    if seconds < 0:
        msg = "⚡ **Debouncer DISABLED.** Engine set to INSTANT response mode."
    elif seconds == 0:
        msg = "⏱️ Artificial delay removed. Normal debouncer (1.5s) active."
    else:
        msg = f"⏱️ Artificial delay set to {seconds} seconds."
    await interaction.response.send_message(msg)

@bot.tree.command(name="model", description="Change AI model.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.choices(model_name=[
    app_commands.Choice(name="Gemini 2.5 Flash Lite", value="gemini-2.5-flash-lite"),
    app_commands.Choice(name="Gemini 2.5 Flash", value="gemini-2.5-flash"),
    app_commands.Choice(name="Gemini 2.5 Pro", value="gemini-2.5-pro")
])
async def model_cmd(interaction: discord.Interaction, model_name: app_commands.Choice[str]):
    await set_config('current_model', model_name.value)
    await interaction.response.send_message(f"🧠 Model switched to `{model_name.name}`.")

@bot.tree.command(name="personality", description="Set custom personality")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def personality(interaction: discord.Interaction, prompt: str):
    await set_config('global_personality', prompt.strip())
    await interaction.response.send_message(f"🌍 Personality Updated.")

@bot.tree.command(name="clear", description="Wipe memory for current channel.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def clear_cmd(interaction: discord.Interaction):
    async with get_channel_lock(interaction.channel_id):
        if interaction.channel_id in MESSAGE_HISTORY:
            del MESSAGE_HISTORY[interaction.channel_id]
    await interaction.response.send_message("🧹 Local Memory Wiped.")

@bot.tree.command(name="memory", description="Analyze chat memory.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def memory_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    history = MESSAGE_HISTORY.get(interaction.channel_id, [])
    if not history: return await interaction.followup.send("🧠 Memory Bank empty.")
    
    ctx_str = "\n".join([f"{'System' if r['author_id']==0 else 'User'}: {r['content']}" for r in history])
    try:
        sys_inst = "Analyze this chat memory. Give a brief, analytical overview."
        analysis = await key_manager.generate_with_fallback('gemini-2.5-flash-lite', [ctx_str], sys_inst)
        await interaction.followup.send(f"🧠 **Analysis:**\n{analysis}")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Extraction failed: {e}")

@bot.tree.command(name="hack", description="Prank hacking sequence")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def hack(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer()
    searches = random.sample(["how to pretend i know python", "anime waifu tier list", "free robux legit no virus"], k=3)
    msg = await interaction.followup.send(f"💻 `Attacking {user.display_name}'s mainframe...`")
    await asyncio.sleep(1.5)
    await msg.edit(content=f"**[CLASSIFIED LEAK]**\n" + "\n".join([f"- `{s}`" for s in searches]))

@bot.tree.command(name="setchannel", description="Auto-reply to all messages here.")
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
async def setchannel(interaction: discord.Interaction):
    await toggle_channel(interaction.guild_id, interaction.channel.id, True)
    await interaction.response.send_message(f"⚙️ Activated in {interaction.channel.mention}")

@bot.tree.command(name="unsetchannel", description="Stop auto-replying here.")
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
async def unsetchannel(interaction: discord.Interaction):
    await toggle_channel(interaction.guild_id, interaction.channel.id, False)
    await interaction.response.send_message(f"❌ Deactivated in {interaction.channel.mention}")

# -------------------- Event Router --------------------
async def generate_ai_response(channel, user_message, author, image_parts=None):
    global TOTAL_QUERIES, QUERY_TIMESTAMPS
    TOTAL_QUERIES += 1
    QUERY_TIMESTAMPS.append(time.time())

    history = MESSAGE_HISTORY.get(channel.id, [])[-10:]
    
    ctx_lines = []
    chars = 0
    for row in reversed(history):
        line = f"{'System' if row['author_id']==0 else 'User'}: {row['content']}\n"
        if chars + len(line) > 3000: break
        ctx_lines.insert(0, line)
        chars += len(line)
        
    ctx_str = "[SYSTEM: Recent history]\n" + "".join(ctx_lines) + f"\nReply to new message: {user_message}"

    payload = [ctx_str]
    if image_parts: payload.extend(image_parts)

    system = get_config('system_prompt', 'You are YoAI.')
    personality = get_config('global_personality', 'default')
    if personality != "default": system += f"\n[GLOBAL PERSONALITY]: {personality}"
    system += "\nCRITICAL: Respond DIRECTLY to the user. DO NOT output a chat transcript."

    return await key_manager.generate_with_fallback(get_config('current_model', 'gemini-2.5-flash-lite'), payload, system)

async def process_channel_buffer(channel_id):
    global LAST_ALERT_TIME
    
    delay_setting = float(get_config('response_delay', '0'))
    
    if delay_setting >= 0:
        await asyncio.sleep(1.5) 
    
    if channel_id not in CHANNEL_BUFFERS: return
    data = CHANNEL_BUFFERS.pop(channel_id)
    if channel_id in CHANNEL_TIMERS: del CHANNEL_TIMERS[channel_id]
        
    try:
        combined_content = "\n".join(data['content'])
        await add_message_to_history(channel_id, data['message'].id, data['author'].id, combined_content or "[Image]", time.time())
        
        if delay_setting > 0: 
            await asyncio.sleep(delay_setting)
            
        response = await generate_ai_response(data['channel'], combined_content, data['author'], data['attachments'])
        for i in range(0, len(response), 2000):
            await data['message'].reply(response[i:i+2000], mention_author=False)
            await asyncio.sleep(1.0) 
            
    except Exception as e:
        await log_system_error(str(data['author']), str(e))
        async with ALERT_LOCK:
            now = time.time()
            if now - LAST_ALERT_TIME > 15.0:
                LAST_ALERT_TIME = now
                try: await data['message'].reply("There is an error. Yaen is notified.", mention_author=False)
                except: pass
                try:
                    app_info = await bot.application_info()
                    await app_info.owner.send(f"⚠️ **Error Trace:**\n```\n{e}\n```")
                except: pass

@bot.event
async def on_message(message: discord.Message):
    if not bot.user or message.author == bot.user: return
    if get_config('engine_status', 'online') == 'offline': return

    is_dm = message.guild is None
    is_mentioned = bot.user in message.mentions
    is_allowed = True if is_dm else await is_channel_allowed(message.guild.id, message.channel.id)

    if is_dm or is_mentioned or is_allowed:
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if not clean_content and not message.attachments: clean_content = "Hello!"
        
        channel_id = message.channel.id
        if channel_id not in CHANNEL_BUFFERS:
            CHANNEL_BUFFERS[channel_id] = {'content': [], 'attachments': [], 'author': message.author, 'channel': message.channel, 'message': message}
            
        if clean_content: CHANNEL_BUFFERS[channel_id]['content'].append(clean_content)
        if message.attachments:
            for att in message.attachments:
                if att.content_type and att.content_type.startswith('image/'):
                    if att.size > 4 * 1024 * 1024: continue
                    CHANNEL_BUFFERS[channel_id]['attachments'].append(types.Part.from_bytes(data=await att.read(), mime_type=att.content_type))
                    
        if channel_id in CHANNEL_TIMERS: CHANNEL_TIMERS[channel_id].cancel()
        CHANNEL_TIMERS[channel_id] = bot.loop.create_task(process_channel_buffer(channel_id))

    await bot.process_commands(message)

# -------------------- Quart Web Dashboard (REDESIGNED CYBER-GLASS UI) --------------------
app = Quart(__name__)
app.secret_key = FLASK_SECRET

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>YoAI | Apex Dashboard V3</title>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg-deep: #050505; --glass: rgba(15, 15, 15, 0.65); --glass-border: rgba(255, 42, 42, 0.2); --text-main: #f3f4f6; --accent: #ff2a2a; --accent-glow: rgba(255, 42, 42, 0.5); --danger: #ef4444; --success: #10b981; }
        body { margin: 0; font-family: 'Space Grotesk', sans-serif; color: var(--text-main); height: 100vh; overflow: hidden; display: flex; background: var(--bg-deep); }
        
        /* Cyberpunk Animated Background */
        #live-bg { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: -2; background: radial-gradient(circle at 50% 50%, #1a0505 0%, #000 80%); }
        .grid-overlay { position: fixed; width: 200vw; height: 200vh; top: -50%; left: -50%; background-image: linear-gradient(var(--glass-border) 1px, transparent 1px), linear-gradient(90deg, var(--glass-border) 1px, transparent 1px); background-size: 50px 50px; z-index: -1; transform: perspective(500px) rotateX(60deg); animation: grid-move 20s linear infinite; opacity: 0.3; }
        @keyframes grid-move { 0% { transform: perspective(500px) rotateX(60deg) translateY(0); } 100% { transform: perspective(500px) rotateX(60deg) translateY(50px); } }

        /* Sleek Glassmorphism Panels */
        .glass { background: var(--glass); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid var(--glass-border); border-radius: 16px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.8); }
        .accent-text { color: var(--accent); font-weight: 700; text-transform: uppercase; letter-spacing: 2px; text-shadow: 0 0 10px var(--accent-glow); }
        
        /* Navigation Sidebar */
        #nav { width: 280px; padding: 30px; display: flex; flex-direction: column; gap: 15px; z-index: 10; margin: 20px; border-left: 4px solid var(--accent); }
        .nav-header { margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid var(--glass-border); }
        .nav-tab { padding: 15px 20px; border-radius: 8px; cursor: pointer; font-weight: 500; text-transform: uppercase; letter-spacing: 1px; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); border: 1px solid transparent; }
        .nav-tab:hover { background: rgba(255,255,255,0.03); transform: translateX(8px); border-color: rgba(255,255,255,0.1); }
        .nav-tab.active { background: rgba(255, 42, 42, 0.1); border-left: 4px solid var(--accent); border-right: 1px solid var(--accent-glow); border-top: 1px solid var(--accent-glow); border-bottom: 1px solid var(--accent-glow); color: #fff; box-shadow: inset 0 0 20px rgba(255, 42, 42, 0.05); }
        
        /* Main Content Area */
        #content { flex-grow: 1; padding: 40px; overflow-y: auto; z-index: 10; scroll-behavior: smooth; }
        .card { padding: 30px; margin-bottom: 30px; transition: transform 0.3s; }
        .card:hover { transform: translateY(-2px); border-color: rgba(255, 42, 42, 0.4); box-shadow: 0 10px 40px rgba(255, 42, 42, 0.1); }
        
        /* Dashboard Stats Grid */
        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 25px; }
        .stat-box { text-align: center; padding: 35px 20px; position: relative; overflow: hidden; }
        .stat-box::before { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 4px; background: var(--accent); opacity: 0.5; }
        .stat-title { font-size: 0.85rem; opacity: 0.6; text-transform: uppercase; letter-spacing: 2px; }
        .stat-value { font-size: 3.5rem; font-weight: 300; color: #fff; margin-top: 15px; text-shadow: 0 0 15px rgba(255, 255, 255, 0.2); }
        
        /* Advanced Cockpit Meters */
        .dash-meters { display: flex; justify-content: center; flex-wrap: wrap; gap: 50px; margin-top: 20px; }
        .meter-wrapper { text-align: center; }
        .meter-box { position: relative; width: 300px; height: 150px; display: flex; justify-content: center; background: rgba(0,0,0,0.5); border: 2px solid var(--glass-border); border-radius: 150px 150px 15px 15px; overflow: hidden; box-shadow: inset 0 20px 50px rgba(0,0,0,0.8); }
        .meter-bg { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: conic-gradient(from 180deg at 50% 100%, transparent 270deg, rgba(255,42,42,0.2) 360deg); }
        .meter-needle { position: absolute; bottom: 10px; left: 50%; width: 4px; height: 120px; background: var(--accent); transform-origin: bottom center; transform: translateX(-50%) rotate(-90deg); transition: transform 1.2s cubic-bezier(0.22, 1, 0.36, 1); box-shadow: 0 0 15px var(--accent); border-radius: 4px; }
        .meter-needle::after { content: ''; position: absolute; bottom: -5px; left: -6px; width: 16px; height: 16px; background: #fff; border-radius: 50%; box-shadow: 0 0 10px #fff; }
        .meter-data { position: absolute; bottom: -10px; background: var(--bg-deep); padding: 5px 20px; border-radius: 10px; border: 1px solid var(--glass-border); z-index: 2; }
        .meter-val { font-size: 2.2rem; font-weight: 700; color: #fff; }
        
        /* Terminal / Diagnostics */
        .terminal { font-family: monospace; background: #0a0a0a; padding: 20px; border-radius: 8px; border: 1px solid #333; color: #0f0; max-height: 300px; overflow-y: auto; }
        .term-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px dashed #222; }
        
        /* Inputs & Buttons */
        button { padding: 16px 30px; border-radius: 8px; border: 1px solid var(--accent); background: rgba(255,42,42,0.1); color: #fff; font-weight: 700; font-family: 'Space Grotesk'; text-transform: uppercase; letter-spacing: 2px; cursor: pointer; transition: all 0.3s; width: 100%; margin-top: 15px; position: relative; overflow: hidden; }
        button:hover { background: var(--accent); box-shadow: 0 0 20px var(--accent-glow); transform: translateY(-2px); }
        input, select, textarea { width: 100%; box-sizing: border-box; padding: 16px; margin-top: 8px; margin-bottom: 25px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.15); background: rgba(0,0,0,0.7); color: white; outline: none; font-family: 'Space Grotesk'; font-size: 1rem; transition: 0.3s; }
        input:focus, select:focus, textarea:focus { border-color: var(--accent); box-shadow: 0 0 15px rgba(255,42,42,0.2); }
        label { font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px; opacity: 0.8; }
        
        /* Login Screen */
        #login-overlay { position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.95); display: flex; justify-content: center; align-items: center; z-index: 1000; }
        .login-box { padding: 60px 50px; text-align: center; width: 380px; border-top: 4px solid var(--accent); position: relative; }
        .login-box::before { content: ''; position: absolute; top: -4px; left: 50%; transform: translateX(-50%); width: 50%; height: 4px; background: #fff; box-shadow: 0 0 20px #fff; }
        
        /* Architecture / Credits */
        .glitch-name { font-size: 3.5rem; font-weight: 700; color: #fff; text-shadow: 2px 2px 0px var(--danger), -2px -2px 0px #0ea5e9; letter-spacing: -2px; margin-bottom: 10px; }
        .fancy-name { font-size: 2.2rem; font-weight: bold; color: #cbd5e1; font-style: italic; text-shadow: 0 0 15px rgba(255,255,255,0.5); }
        
        .hidden { display: none !important; }
        .visible-block { display: block !important; }
        .visible-flex { display: flex !important; }
    </style>
</head>
<body>
    <div id="live-bg"></div><div class="grid-overlay"></div>
    
    <div id="login-overlay" class="glass">
        <div class="login-box glass">
            <h1 class="accent-text" style="font-size:2.5rem; margin-bottom:5px;">APEX V3</h1>
            <p style="font-size:0.8rem; letter-spacing:4px; opacity:0.5; margin-bottom: 40px;">SECURE IGNITION</p>
            <input type="password" id="pwd" placeholder="Enter Authorization Code..." style="text-align: center; letter-spacing: 2px;">
            <button onclick="login()">Authenticate</button>
            <p id="err" class="hidden" style="color:var(--danger); margin-top:20px; font-weight: bold; letter-spacing: 1px;">ACCESS DENIED.</p>
        </div>
    </div>
    
    <div id="dashboard-view" class="hidden" style="width:100%; height:100%;">
        <div id="nav" class="glass">
            <div class="nav-header">
                <h2 class="accent-text" style="margin:0; font-size: 2rem;">YoAI</h2>
                <div style="opacity:0.5; font-size:0.8rem; letter-spacing: 2px; margin-top: 5px;">LOCAL RAM EDITION</div>
            </div>
            <div class="nav-tab active" id="tab-cockpit" onclick="switchTab('cockpit')">Cockpit</div>
            <div class="nav-tab" id="tab-telemetry" onclick="switchTab('telemetry')">Local Telemetry</div>
            <div class="nav-tab" id="tab-diag" onclick="switchTab('diag')">Cluster Diagnostics</div>
            <div class="nav-tab" id="tab-admin" onclick="switchTab('admin')">Live Config</div>
            <div class="nav-tab" id="tab-credits" onclick="switchTab('credits')">Architecture</div>
            
            <div style="margin-top: auto; padding-top: 20px; border-top: 1px solid var(--glass-border);">
                <button style="border-color:var(--danger); color:var(--danger); background:transparent; padding: 12px;" onclick="logout()">Kill Switch</button>
            </div>
        </div>
        
        <div id="content">
            <div id="section-cockpit" class="visible-block">
                <h1 class="accent-text" style="margin-bottom: 40px;">Engine Cockpit</h1>
                <div class="card glass">
                    <div class="dash-meters">
                        <div class="meter-wrapper">
                            <div class="meter-box">
                                <div class="meter-bg"></div>
                                <div class="meter-needle" id="needle-rpm"></div>
                            </div>
                            <div class="meter-data"><div class="meter-val" id="val-rpm">0</div><div style="font-size:0.8rem; color:#aaa; font-weight: bold; letter-spacing: 1px;">RPM</div></div>
                        </div>
                        <div class="meter-wrapper">
                            <div class="meter-box" style="border-color: rgba(16, 185, 129, 0.4);">
                                <div class="meter-bg" style="background: conic-gradient(from 180deg at 50% 100%, transparent 270deg, rgba(16,185,129,0.2) 360deg);"></div>
                                <div class="meter-needle" id="needle-rlpd" style="background: #10b981; box-shadow: 0 0 15px #10b981;"></div>
                            </div>
                            <div class="meter-data" style="border-color: rgba(16, 185, 129, 0.4);"><div class="meter-val" id="val-rlpd" style="color: #10b981;">0</div><div style="font-size:0.8rem; color:#aaa; font-weight: bold; letter-spacing: 1px;">TOTAL QUERIES</div></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div id="section-telemetry" class="hidden">
                <h1 class="accent-text" style="margin-bottom: 40px;">Local RAM Telemetry</h1>
                <div class="stat-grid">
                    <div class="card glass stat-box"><div class="stat-title">System Uptime</div><div class="stat-value" id="uptime">-</div></div>
                    <div class="card glass stat-box"><div class="stat-title">Memory Rows (Live)</div><div class="stat-value" id="memory">-</div></div>
                    <div class="card glass stat-box"><div class="stat-title">Estimated RAM (KB)</div><div class="stat-value" id="db-size">-</div></div>
                </div>
            </div>
            
            <div id="section-diag" class="hidden">
                <h1 class="accent-text" style="margin-bottom: 40px;">Cluster Health</h1>
                <div class="card glass">
                    <button id="diag-btn" onclick="runDiag()" style="margin-top: 0; margin-bottom: 20px;">Initiate Deep Scan</button>
                    <div id="diag-results" class="terminal">Awaiting scan initiation...</div>
                </div>
            </div>
            
            <div id="section-admin" class="hidden">
                <h1 class="accent-text" style="margin-bottom: 40px;">Live Configuration</h1>
                <div class="card glass">
                    <p style="color: #aaa; margin-bottom: 20px;">Changes here are injected instantly into Python RAM. No reboot required.</p>
                    <label>System Instructions (Global Prompt)</label>
                    <textarea id="admin-prompt" rows="4"></textarea>
                    
                    <label>Active AI Model Engine</label>
                    <select id="admin-model">
                        <option value="gemini-2.5-flash-lite">Gemini 2.5 Flash Lite (Fastest)</option>
                        <option value="gemini-2.5-flash">Gemini 2.5 Flash (Balanced)</option>
                        <option value="gemini-2.5-pro">Gemini 2.5 Pro (Heavy)</option>
                    </select>
                    
                    <button onclick="saveConfig()">Inject Config into RAM</button>
                </div>
                <div class="card glass" style="border-color:rgba(239,68,68,0.5); background: rgba(239,68,68,0.05);">
                    <h3 style="color: var(--danger); margin-top: 0;">Danger Zone</h3>
                    <p style="color: #aaa; font-size: 0.9rem;">Instantly wipes all chat history dictionaries across all Discord servers.</p>
                    <button style="border-color:var(--danger); color:var(--danger); background:rgba(239,68,68,0.1); width: auto;" onclick="nukeMemory()">Incinerate RAM Memory</button>
                </div>
            </div>
            
            <div id="section-credits" class="hidden">
                <h1 class="accent-text" style="margin-bottom: 40px;">System Architecture</h1>
                <div class="card glass" style="text-align:center; padding:60px 40px;">
                    <div class="glitch-name">𝕸r_𝖄aen (Yathin)</div>
                    <p style="opacity:0.6; margin-bottom:50px; letter-spacing: 2px; text-transform: uppercase;">Master Architect & Developer</p>
                    
                    <div class="fancy-name">✨ ℜhys ✨</div>
                    <p style="opacity:0.6; letter-spacing: 2px; text-transform: uppercase;">Lead Testing Partner</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        function toggleUI(show) {
            document.getElementById('login-overlay').className = show ? 'hidden' : 'glass';
            document.getElementById('dashboard-view').className = show ? 'visible-flex' : 'hidden';
        }
        
        function switchTab(t) {
            ['cockpit','telemetry','diag','admin','credits'].forEach(id => {
                document.getElementById('tab-'+id).classList.remove('active');
                document.getElementById('section-'+id).classList.replace('visible-block', 'hidden');
            });
            document.getElementById('tab-'+t).classList.add('active');
            document.getElementById('section-'+t).classList.replace('hidden', 'visible-block');
            if(t === 'admin') fetchConfig();
        }
        
        async function login() {
            const r = await fetch('/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:document.getElementById('pwd').value})});
            if(r.ok) { 
                toggleUI(true); 
                fetchStats(); 
                setInterval(fetchStats, 3000); 
                fetchConfig(); 
            } else { 
                document.getElementById('err').classList.remove('hidden'); 
            }
        }
        
        async function logout() { 
            await fetch('/logout', {method:'POST'}); 
            toggleUI(false); 
            document.getElementById('pwd').value=''; 
        }
        
        function updateGauges(rpm, total) {
            // Animates RPM
            document.getElementById('val-rpm').innerText = rpm;
            let rpmDeg = -90 + (Math.min(rpm, 100) / 100) * 180;
            document.getElementById('needle-rpm').style.transform = `translateX(-50%) rotate(${rpmDeg}deg)`;
            
            // Animates Total
            document.getElementById('val-rlpd').innerText = total;
            let totalDeg = -90 + (Math.min(total, 5000) / 5000) * 180;
            document.getElementById('needle-rlpd').style.transform = `translateX(-50%) rotate(${totalDeg}deg)`;
        }
        
        async function fetchStats() {
            try {
                if(document.getElementById('dashboard-view').classList.contains('hidden')) return;
                const r = await fetch('/api/stats');
                if(!r.ok) throw new Error('Unauth');
                const d = await r.json();
                document.getElementById('uptime').innerText = d.uptime;
                document.getElementById('memory').innerText = d.rows;
                document.getElementById('db-size').innerText = d.db_size;
                updateGauges(d.rpm, d.total);
            } catch(e) {}
        }
        
        async function runDiag() {
            const btn = document.getElementById('diag-btn');
            const term = document.getElementById('diag-results');
            btn.innerText = 'Scanning...';
            term.innerHTML = '<span style="color:#aaa;">> Sending ping packets to Google AI infrastructure...</span><br>';
            
            const r = await fetch('/api/diag', {method:'POST'});
            const d = await r.json();
            
            term.innerHTML += d.results.map(n => {
                let color = n.status === 'ONLINE' ? '#10b981' : (n.status === 'COOLDOWN' ? '#f59e0b' : '#ef4444');
                return `<div class="term-row">
                    <div>
                        <b style="color:#fff;">[${n.name}]</b> <span style="opacity:0.7">${n.masked_key}</span><br>
                        <small style="color:#888;">${n.detail}</small>
                    </div>
                    <div style="color:${color}; font-weight:bold; letter-spacing:1px;">${n.status}</div>
                </div>`;
            }).join('');
            btn.innerText = 'Initiate Deep Scan';
        }
        
        async function fetchConfig() {
            const r = await fetch('/api/config');
            if(r.ok) {
                const d = await r.json();
                document.getElementById('admin-prompt').value = d.system_prompt;
                document.getElementById('admin-model').value = d.current_model;
            }
        }
        
        async function saveConfig() {
            await fetch('/api/config', {
                method:'POST', 
                headers:{'Content-Type':'application/json'}, 
                body:JSON.stringify({
                    system_prompt: document.getElementById('admin-prompt').value, 
                    current_model: document.getElementById('admin-model').value
                })
            });
            alert('Config Successfully Injected into Local RAM!');
        }
        
        async function nukeMemory() {
            if(confirm("CRITICAL WARNING: This will incinerate all local chat context currently stored in RAM. Proceed?")) { 
                await fetch('/api/nuke', {method:'POST'}); 
                alert("RAM Wiped."); 
                fetchStats(); 
            }
        }
        
        window.onload = async () => { 
            const r = await fetch('/api/stats'); 
            if(r.ok) { 
                toggleUI(true); 
                fetchStats(); 
                setInterval(fetchStats, 3000); 
                fetchConfig(); 
            } 
        };
    </script>
</body>
</html>
"""

@app.route('/')
async def index(): return await render_template_string(HTML_TEMPLATE)

@app.route('/login', methods=['POST'])
async def login():
    if (await request.get_json()).get('password') == "mr_yaen":
        session['logged_in'] = True
        return jsonify(success=True)
    return jsonify(success=False), 401

@app.route('/logout', methods=['POST'])
async def logout():
    session.pop('logged_in', None)
    return jsonify(success=True)

@app.route('/api/stats')
async def api_stats():
    if not session.get('logged_in'): return jsonify(error="Unauthorized"), 401
    now = time.time()
    QUERY_TIMESTAMPS[:] = [ts for ts in QUERY_TIMESTAMPS if now - ts < 60.0]
    
    # Local RAM Calculation
    rows = sum(len(msgs) for msgs in MESSAGE_HISTORY.values())
    # Estimate RAM weight in KB (very rough estimation based on strings)
    db_size = round(sys.getsizeof(str(MESSAGE_HISTORY)) / 1024, 1)
            
    return jsonify({
        "uptime": str(datetime.timedelta(seconds=int(now - START_TIME))).split(".")[0], 
        "total": TOTAL_QUERIES, 
        "rows": rows, 
        "db_size": db_size, 
        "rpm": len(QUERY_TIMESTAMPS)
    })

@app.route('/api/diag', methods=['POST'])
async def api_diag():
    if not session.get('logged_in'): return jsonify(error="Unauthorized"), 401
    return jsonify(success=True, results=await key_manager.run_diagnostics())

@app.route('/api/config', methods=['GET', 'POST'])
async def api_config():
    if not session.get('logged_in'): return jsonify(error="Unauthorized"), 401
    if request.method == 'GET':
        return jsonify({
            "system_prompt": get_config('system_prompt', 'You are YoAI, a highly intelligent assistant.'),
            "current_model": get_config('current_model', 'gemini-2.5-flash-lite')
        })
    data = await request.get_json()
    for k, v in data.items(): await set_config(k, v)
    return jsonify(success=True)

@app.route('/api/nuke', methods=['POST'])
async def api_nuke():
    if not session.get('logged_in'): return jsonify(error="Unauthorized"), 401
    MESSAGE_HISTORY.clear()
    return jsonify(success=True)

# -------------------- Decoupled Survival Startup --------------------
async def main():
    # 1. IMMEDIATE DASHBOARD BIND (No Delays)
    print(f"[BOOT] Binding V3 Dashboard to Port {PORT} instantly...")
    asyncio.create_task(app.run_task(host="0.0.0.0", port=PORT))
    
    await asyncio.sleep(1) # Nano-breather for Quart
    print("[BOOT] Cyber-Glass Dashboard is live.")
    
    # 2. IGNITE DISCORD ENGINE (Immortal Survival Loop)
    print("[BOOT] Igniting Discord Engine (Local RAM + V3 Dash)...")
    while True:
        try:
            await bot.start(os.environ.get("DISCORD_BOT_TOKEN"))
        except Exception as e:
            if "1015" in str(e) or "429" in str(e):
                print("🛑 [BANNED] Discord blocked this IP. Waiting 60s...")
                await asyncio.sleep(60)
            else:
                print(f"⚠️ [CRASH] Bot crashed: {e}. Restarting in 10s...")
                await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
