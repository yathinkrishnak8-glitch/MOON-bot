import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import random
import time
import asyncio
from datetime import timedelta
from keep_alive import keep_alive
from groq import Groq

# ==========================================
# 1. SETUP & DATABASE
# ==========================================
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

if not DISCORD_TOKEN:
    print("CRITICAL: DISCORD_TOKEN is missing!")

client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"Groq Init Error: {e}")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

DB_FILE = "database.json"

def get_default_db():
    return {
        "warns": {}, 
        "jailed": {}, 
        "config": {"filterwords": [], "ai_channel": None, "cmd_channel": None, "event_channel": None}, 
        "economy": {},
        "levels": {},
        "custom_commands": {} 
    }

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump(get_default_db(), f)
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

db = load_db()

# Economy & Level Helpers
def get_eco(uid):
    if uid not in db["economy"]: db["economy"][uid] = 0
    return db["economy"][uid]

def add_eco(uid, amount):
    db["economy"][uid] = get_eco(uid) + amount

def add_xp(uid):
    if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
    db["levels"][uid]["xp"] += random.randint(10, 25)
    current_xp = db["levels"][uid]["xp"]
    current_lvl = db["levels"][uid]["level"]
    next_lvl_xp = (current_lvl * 100) * 1.5
    if current_xp >= next_lvl_xp:
        db["levels"][uid]["level"] += 1
        return db["levels"][uid]["level"]
    return None

def find_member(ctx, search_term):
    if not search_term: return None
    search_term = search_term.replace("<@", "").replace(">", "").replace("!", "")
    if search_term.isdigit(): return ctx.guild.get_member(int(search_term))
    for m in ctx.guild.members:
        if m.name.lower() == search_term.lower() or m.display_name.lower() == search_term.lower():
            return m
    return None

# ==========================================
# 2. AUTO MODEL SWAPPER 
# ==========================================
def ask_groq(messages):
    if not client: raise Exception("Groq API Key is missing.")
    fallback_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]
    last_error = None
    for model in fallback_models:
        try:
            completion = client.chat.completions.create(model=model, messages=messages)
            return completion.choices[0].message.content.strip()
        except Exception as e:
            last_error = e
            continue 
    raise Exception(f"All AI models failed. Last Error: {last_error}")

# ==========================================
# 3. ON READY & AUTOMATED EVENT LOOP
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ habbibi mod (: logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands!")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    if not ai_event_loop.is_running():
        ai_event_loop.start()

@tasks.loop(minutes=60)
async def ai_event_loop():
    """Triggers a random AI event every 60 minutes in the designated channel."""
    if not client: return
    channel_id = db["config"].get("event_channel")
    if not channel_id: return
    
    channel = bot.get_channel(channel_id)
    if not channel: return

    prompt = """
    You are the Dungeon Master of a Discord server. Generate a random, engaging server event. 
    It can be a lore drop about a mysterious traveler, a boss monster appearing, or a blessing from the gods.
    Make it epic, funny, and use internet slang. Keep it under 3 paragraphs. 
    Do NOT output JSON. Just output the raw message to send to the chat.
    """
    try:
        reply = ask_groq([{"role": "user", "content": prompt}])
        embed = discord.Embed(title="🚨 RANDOM SERVER EVENT 🚨", description=reply, color=discord.Color.dark_purple())
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Event Loop Error: {e}")

# ==========================================
# 4. COMMAND CHANNEL BINDING
# ==========================================
@bot.check
async def check_command_channel(ctx):
    """Ensures normal users only use commands in the designated bot channel."""
    if ctx.author.guild_permissions.administrator: return True # Admins bypass this
    
    cmd_channel_id = db["config"].get("cmd_channel")
    if not cmd_channel_id: return True # If no channel is set, allow anywhere
    
    if ctx.channel.id != cmd_channel_id:
        cmd_chan = ctx.guild.get_channel(cmd_channel_id)
        if cmd_chan:
            await ctx.send(f"❌ Commands belong in {cmd_chan.mention}, bozo.", delete_after=5)
        return False
    return True

# ==========================================
# 5. SERVER DEPLOYER & GOD-MODE
# ==========================================
@bot.hybrid_command(name="deployserver", description="WARNING: Deletes ALL channels/roles and builds a top-tier server from scratch.")
@commands.has_permissions(administrator=True)
async def deployserver(ctx):
    await ctx.send("⚠️ **INITIATING PROJECT ZERO.** Wiping current server and building the Ultimate Kingdom...\n*This will take a few minutes to bypass Discord limits.*")
    guild = ctx.guild

    # 1. DELETE EXISTING CHANNELS (SLOWLY)
    for channel in guild.channels:
        try: 
            await channel.delete()
            await asyncio.sleep(0.5)
        except: pass

    # 2. DELETE EXISTING ROLES (SLOWLY)
    for role in guild.roles:
        if role.name != "@everyone" and not role.managed and role < ctx.guild.me.top_role:
            try: 
                await role.delete()
                await asyncio.sleep(0.5)
            except: pass

    # 3. BUILD NEW ROLES
    roles_to_make = [
        {"name": "👑 Emperor", "color": discord.Color.gold(), "admin": True},
        {"name": "⚔️ High Council", "color": discord.Color.dark_red(), "admin": False},
        {"name": "🛡️ Knight", "color": discord.Color.blue(), "admin": False},
        {"name": "📜 Citizen", "color": discord.Color.light_grey(), "admin": False},
        {"name": "Jailed", "color": discord.Color.dark_grey(), "admin": False}
    ]
    created_roles = {}
    for r in roles_to_make:
        perms = discord.Permissions(administrator=r["admin"])
        new_role = await guild.create_role(name=r["name"], color=r["color"], permissions=perms, hoist=True)
        created_roles[r["name"]] = new_role
        await asyncio.sleep(1)
        
    await ctx.author.add_roles(created_roles["👑 Emperor"])

    # 4. BUILD NEW CATEGORIES & CHANNELS
    cat_hub = await guild.create_category("🏰 THE KINGDOM HUB")
    await guild.create_text_channel("rules", category=cat_hub)
    announcements = await guild.create_text_channel("announcements", category=cat_hub)
    
    cat_chat = await guild.create_category("🗣️ LORE & CHAT")
    gen_chat = await guild.create_text_channel("general", category=cat_chat)
    bot_cmds = await guild.create_text_channel("bot-commands", category=cat_chat)
    ai_chat = await guild.create_text_channel("talk-to-ai", category=cat_chat)
    
    cat_vc = await guild.create_category("🔊 TAVERN (VOICE)")
    await guild.create_voice_channel("Lounge", category=cat_vc)
    await guild.create_voice_channel("Gaming", category=cat_vc)

    # 5. LOCK JAIL
    jail_role = created_roles["Jailed"]
    for cat in guild.categories:
        await cat.set_permissions(jail_role, read_messages=False, connect=False)

    # 6. BIND BOT CONFIG
    db["config"]["cmd_channel"] = bot_cmds.id
    db["config"]["ai_channel"] = ai_chat.id
    db["config"]["event_channel"] = gen_chat.id
    save_db(db)

    embed = discord.Embed(title="✅ DEPLOYMENT COMPLETE", description="Welcome to your new Kingdom. \n- AI Events set to General.\n- Normal Commands locked to #bot-commands.\n- AI auto-chat locked to #talk-to-ai.", color=discord.Color.green())
    await gen_chat.send(f"{ctx.author.mention}", embed=embed)

@bot.hybrid_command(name='aicommand', description="The Master AI brain. It can do ANYTHING you ask it to.")
@app_commands.describe(instruction="What do you want the bot to do?")
@commands.has_permissions(administrator=True)
async def aicommand(ctx, *, instruction: str):
    if not client: return await ctx.send("🤖 **habbibi mod (::** AI is offline.")
    await ctx.defer()
    
    prompt = f"""
    You are "habbibi mod (:", an omnipotent Discord bot with GOD-MODE enabled.
    The boss "{ctx.author.name}" said: "{instruction}"
    
    Turn this into a JSON array of actions. 
    1. Reply: {{"action": "reply", "message": "text"}}
    2. Ban: {{"action": "ban", "target": "username", "reason": "text"}}
    3. Execute Python: {{"action": "execute", "code": "await ctx.send('Done!')"}}
    
    STRICT EXECUTE RULES:
    - You must write valid discord.py asynchronous code.
    - You have access to 'ctx', 'bot', 'discord', 'asyncio', and 'db'.
    - Use \\n for new lines.
    - Add 'await asyncio.sleep(2)' between EVERY channel creation/deletion.
    
    OUTPUT STRICTLY A VALID JSON ARRAY starting with [ and ending with ].
    """
    try:
        raw = ask_groq([{"role": "user", "content": prompt}])
        start_idx, end_idx = raw.find('['), raw.rfind(']')
        if start_idx != -1 and end_idx != -1: clean_json = raw[start_idx:end_idx+1]
        else: clean_json = raw.replace('```json', '').replace('```', '').replace('```python', '').strip()
        
        actions = json.loads(clean_json)
        
        for act in actions:
            atype = act.get("action")
            if atype == "reply": await ctx.send(f"🤖 **habbibi mod (::** {act.get('message')}")
            elif atype == "ban" and act.get("target"):
                member = find_member(ctx, act.get("target"))
                if member:
                    await member.ban(reason=act.get("reason", "AI Ban"))
                    await ctx.send(f"🔨 AI Banished {member.mention}.")
            elif atype == "execute":
                code = act.get("code", "")
                await ctx.send("⚡ **AI is executing dynamic Python code...**")
                try:
                    wrapped_code = f"async def __ai_exec():\n"
                    for line in code.split("\n"): wrapped_code += f"    {line}\n"
                    exec_env = {'discord': discord, 'bot': bot, 'ctx': ctx, 'asyncio': asyncio, 'db': db}
                    exec(wrapped_code, exec_env)
                    await exec_env['__ai_exec']()
                except Exception as code_error:
                    await ctx.send(f"⚠️ AI Code Execution Failed:\n```py\n{code_error}\n```")
    except Exception as e:
        await ctx.send(f"❌ AI Error: {e}")

# ==========================================
# 6. MESSAGE LISTENER (AI, XP, AUTOMOD)
# ==========================================
@bot.listen('on_message')
async def on_message_listener(message):
    if message.author.bot or not message.guild: return

    # 1. Automod
    for word in db["config"]["filterwords"]:
        if word in message.content.lower():
            await message.delete()
            return await message.channel.send(f"⚠️ {message.author.mention}, that word is banned!", delete_after=5)

    # 2. XP Leveling
    leveled_up = add_xp(str(message.author.id))
    if leveled_up:
        save_db(db)
        await message.channel.send(f"🎉 **{message.author.mention} leveled up to Level {leveled_up}!**")
    
    # 3. Custom Commands
    if message.content.startswith('!') and len(message.content) > 1:
        cmd = message.content[1:].split()[0].lower()
        if cmd in db["custom_commands"]:
            return await message.channel.send(db["custom_commands"][cmd])

    # 4. AI Auto-Chat
    is_ai_channel = (message.channel.id == db["config"].get("ai_channel"))
    if is_ai_channel and not message.content.startswith(('!', '/')):
        if not client: return
        async with message.channel.typing():
            try:
                reply = ask_groq([
                    {"role": "system", "content": "You are habbibi mod (:, a sarcastic Discord bot."},
                    {"role": "user", "content": message.content}
                ])
                await message.channel.send(reply[:2000])
            except Exception as e:
                await message.channel.send(f"❌ AI glitched: {e}")

# ==========================================
# 7. ECONOMY & RPG COMMANDS
# ==========================================
@bot.hybrid_command(name="bal", description="Check your coin balance.")
async def bal(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"💰 {member.name} has **{get_eco(str(member.id))}** coins.")

@bot.hybrid_command(name="work", description="Work to earn coins.")
@commands.cooldown(1, 3600, commands.BucketType.user) # 1 hour cooldown
async def work(ctx):
    earned = random.randint(100, 300)
    add_eco(str(ctx.author.id), earned)
    save_db(db)
    await ctx.send(f"💼 You worked a grueling shift and earned **{earned} coins**!")

@bot.hybrid_command(name="crime", description="Commit a crime for coins (risky).")
@commands.cooldown(1, 3600, commands.BucketType.user)
async def crime(ctx):
    uid = str(ctx.author.id)
    if random.choice([True, False]):
        earned = random.randint(300, 700)
        add_eco(uid, earned)
        await ctx.send(f"🥷 You successfully robbed the royal vault for **{earned} coins**!")
    else:
        lost = random.randint(100, 250)
        db["economy"][uid] = max(0, get_eco(uid) - lost)
        await ctx.send(f"🚓 The guards caught you! You paid a fine of **{lost} coins**.")
    save_db(db)

@bot.hybrid_command(name="rob", description="Attempt to steal from another user.")
@commands.cooldown(1, 7200, commands.BucketType.user) # 2 hour cooldown
async def rob(ctx, member: discord.Member):
    uid, target_id = str(ctx.author.id), str(member.id)
    if get_eco(target_id) < 100:
        return await ctx.send(f"❌ {member.name} is too poor to rob.")
    
    if random.choice([True, False]):
        stolen = random.randint(50, int(get_eco(target_id) * 0.2)) # Steal up to 20%
        db["economy"][target_id] -= stolen
        add_eco(uid, stolen)
        await ctx.send(f"🔫 You violently mugged {member.name} and stole **{stolen} coins**!")
    else:
        fine = 200
        db["economy"][uid] = max(0, get_eco(uid) - fine)
        await ctx.send(f"🛡️ {member.name} fought back! You dropped **{fine} coins** running away.")
    save_db(db)

@bot.hybrid_command(name="level", description="Check your current RPG Level.")
async def level(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    lvl_data = db["levels"].get(uid, {"xp": 0, "level": 1})
    await ctx.send(f"⭐ **{member.name}** is Level **{lvl_data['level']}** ({lvl_data['xp']} XP).")

# ==========================================
# 8. STANDARD MODERATION 
# ==========================================
@bot.hybrid_command(name="purge", description="Deletes multiple messages.")
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Swept {amount} messages.", delete_after=3)

@bot.hybrid_command(name="nuke", description="Deletes and clones the current channel.")
@commands.has_permissions(administrator=True)
async def nuke(ctx):
    pos = ctx.channel.position
    new_channel = await ctx.channel.clone()
    await ctx.channel.delete()
    await new_channel.edit(position=pos)
    await new_channel.send("☢️ **TACTICAL NUKE INCOMING!** 💥")

# ==========================================
# 9. RENDER BOOT UP
# ==========================================
if __name__ == "__main__":
    keep_alive()
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
