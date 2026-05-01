import discord
from discord.ext import commands
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
        "config": {"filterwords": [], "ai_channel": None}, 
        "economy": {},
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
start_time = time.time()

def get_eco(uid):
    if uid not in db["economy"]: db["economy"][uid] = 0
    return db["economy"][uid]

def find_member(ctx, search_term):
    if not search_term: return None
    search_term = search_term.replace("<@", "").replace(">", "").replace("!", "")
    if search_term.isdigit(): return ctx.guild.get_member(int(search_term))
    for m in ctx.guild.members:
        if m.name.lower() == search_term.lower() or m.display_name.lower() == search_term.lower():
            return m
    return None

@bot.event
async def on_ready():
    print(f"✅ habbibi mod (: logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands!")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# ==========================================
# 2. AUTO MODEL SWAPPER 
# ==========================================

def ask_groq(messages):
    if not client:
        raise Exception("Groq API Key is missing.")
    
    fallback_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768"
    ]
    
    last_error = None
    for model in fallback_models:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            last_error = e
            continue 
            
    raise Exception(f"All AI models failed. Last Error: {last_error}")

# ==========================================
# 3. AUTONOMOUS AI & DM CHAT
# ==========================================

@bot.listen('on_message')
async def ai_auto_chat(message):
    if message.author.bot: return

    if message.content.startswith('!') and len(message.content) > 1:
        cmd = message.content[1:].split()[0].lower()
        if cmd in db["custom_commands"]:
            await message.channel.send(db["custom_commands"][cmd])
            return 

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_ai_channel = (message.channel.id == db["config"].get("ai_channel"))

    if (is_dm or is_ai_channel) and not message.content.startswith(('!', '/')):
        if not client: return
        async with message.channel.typing():
            try:
                system_prompt = "You are habbibi mod (:, a chaotic, helpful, and sarcastic Discord bot. Be concise and keep the internet slang."
                if is_dm: system_prompt += " You are in their DMs providing 1-on-1 support."
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message.content}
                ]
                reply = ask_groq(messages)
                await message.channel.send(reply[:2000])
            except Exception as e:
                await message.channel.send(f"❌ My AI brain glitched: {e}")

@bot.hybrid_command(name="setaichannel", description="Sets the current channel for the AI to auto-reply to everything.")
@commands.has_permissions(administrator=True)
async def setaichannel(ctx):
    db["config"]["ai_channel"] = ctx.channel.id
    save_db(db)
    await ctx.send("🤖 **AI Channel Set!** I will now reply to every message sent in this channel automatically.")

@bot.hybrid_command(name="unsetaichannel", description="Stops the AI from auto-replying in the channel.")
@commands.has_permissions(administrator=True)
async def unsetaichannel(ctx):
    db["config"]["ai_channel"] = None
    save_db(db)
    await ctx.send("🔇 **AI Channel Disabled.** I will only speak when spoken to.")

# ==========================================
# 4. GOD-MODE AI COMMANDER & RESET
# ==========================================

@bot.hybrid_command(name="reset", description="Wipes the bot's memory and resets to original factory state.")
@commands.has_permissions(administrator=True)
async def reset(ctx):
    global db
    await ctx.send("🔄 **FACTORY RESET INITIATED...** Wiping databases...")
    db = get_default_db()
    save_db(db)
    await asyncio.sleep(1)
    await ctx.send("✅ **Reset Complete.** Economy, jails, warnings, and custom commands have been permanently wiped. I am a blank slate.")

@bot.hybrid_command(name='aicommand', description="The Master AI brain. It can do ANYTHING you ask it to.")
@app_commands.describe(instruction="What do you want the bot to do?")
@commands.has_permissions(administrator=True)
async def aicommand(ctx, *, instruction: str):
    if not client:
        return await ctx.send("🤖 **habbibi mod (::** AI is offline.")

    await ctx.defer()
    prompt = f"""
    You are "habbibi mod (:", an omnipotent Discord bot with GOD-MODE enabled.
    The boss "{ctx.author.name}" said: "{instruction}"
    
    Turn this into a JSON array of actions. 
    BASIC FORMATS:
    1. Reply: {{"action": "reply", "message": "text"}}
    2. Ban: {{"action": "ban", "target": "username", "reason": "text"}}
    3. Mute: {{"action": "mute", "target": "username", "minutes": 10}}
    4. Create Command: {{"action": "create_command", "trigger": "word", "reply": "text"}}
    
    GOD-MODE FORMAT (Use this for ANYTHING else like renaming channels, creating roles, making categories, etc):
    5. Execute Python: {{"action": "execute", "code": "await ctx.guild.create_text_channel('royal-hall')\\nawait ctx.send('Done!')"}}
    *IMPORTANT: When using 'execute', write valid asynchronous discord.py Python code. You have access to 'ctx', 'bot', and 'discord'. Use \\n for new lines.*

    ONLY RETURN RAW JSON.
    """
    try:
        messages = [{"role": "user", "content": prompt}]
        raw = ask_groq(messages)
        clean_json = raw.replace('```json', '').replace('```', '').replace('```python', '').strip()
        actions = json.loads(clean_json)
        
        for act in actions:
            atype = act.get("action")
            target_str = act.get("target")
            member = find_member(ctx, target_str) if target_str else None

            if atype == "reply":
                await ctx.send(f"🤖 **habbibi mod (::** {act.get('message')}")
            
            elif atype == "ban" and member:
                await member.ban(reason=act.get("reason", "AI Ban"))
                await ctx.send(f"🔨 AI Banished {member.mention}.")
                
            elif atype == "mute" and member:
                mins = int(act.get("minutes", 10))
                await member.timeout(timedelta(minutes=mins))
                await ctx.send(f"🔇 AI Muted {member.mention} for {mins}m.")
                
            elif atype == "create_command":
                trigger = act.get("trigger", "").lower().replace("!", "")
                reply_txt = act.get("reply", "No reply set.")
                db["custom_commands"][trigger] = reply_txt
                save_db(db)
                await ctx.send(f"🧠 **AI Learned a New Trick!**\nYou can now type `!{trigger}` to use it.")
            
            # THE GOD-MODE EXECUTOR
            elif atype == "execute":
                code = act.get("code", "")
                await ctx.send("⚡ **AI is executing dynamic Python code...**")
                try:
                    # Wrap the AI's code in an async function so it can use 'await'
                    wrapped_code = f"async def __ai_exec():\n"
                    for line in code.split("\n"):
                        wrapped_code += f"    {line}\n"
                    
                    # Create an environment for the code to run in
                    exec_env = {
                        'discord': discord,
                        'bot': bot,
                        'ctx': ctx,
                        'asyncio': asyncio
                    }
                    
                    # Execute the raw code
                    exec(wrapped_code, exec_env)
                    await exec_env['__ai_exec']()
                except Exception as code_error:
                    await ctx.send(f"⚠️ AI Code Execution Failed:\n```py\n{code_error}\n```")
                
    except Exception as e:
        await ctx.send(f"❌ AI Error: {e}")

@bot.hybrid_command(name='askai', description="Ask the AI a question.")
@app_commands.describe(question="What do you want to ask?")
async def askai(ctx, *, question: str):
    if not client: return await ctx.send("AI is sleeping.")
    await ctx.defer()
    try:
        messages = [
            {"role": "system", "content": "You are habbibi mod (:, a funny, sarcastic Discord bot using internet slang."},
            {"role": "user", "content": question}
        ]
        reply = ask_groq(messages)
        await ctx.send(reply[:2000])
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ==========================================
# 5. HYBRID MANUAL MODERATION
# ==========================================

@bot.hybrid_command(name="kick", description="Kicks a member from the server.")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "Caught lacking"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 **{member.name}** just got YEETED! 💨 Reason: {reason}")

@bot.hybrid_command(name="ban", description="Bans a member from the server.")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "Crossed the line"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 {member.mention} has been banished. Reason: {reason}")

@bot.hybrid_command(name="unban", description="Unbans a user ID.")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: str, *, reason: str = "Forgiven"):
    user = await bot.fetch_user(int(user_id))
    await ctx.guild.unban(user, reason=reason)
    await ctx.send(f"🕊️ {user.mention} revived from the dead.")

@bot.hybrid_command(name="mute", description="Time out a member.")
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int, *, reason: str = "Yapping"):
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    await ctx.send(f"🔇 {member.mention} timed out for {minutes}m.")

@bot.hybrid_command(name="unmute", description="Remove timeout from a member.")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"🔊 {member.mention} is off the leash.")

@bot.hybrid_command(name="jail", description="Strips roles and locks a user in jail.")
@commands.has_permissions(administrator=True)
async def jail(ctx, member: discord.Member):
    db["jailed"][str(member.id)] = [role.id for role in member.roles if role.id != ctx.guild.default_role.id]
    save_db(db)
    for role in member.roles[1:]:
        try: await member.remove_roles(role)
        except: pass
    jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
    if not jail_role:
        jail_role = await ctx.guild.create_role(name="Jailed", color=discord.Color.dark_grey())
        for channel in ctx.guild.channels: await channel.set_permissions(jail_role, read_messages=False)
    await member.add_roles(jail_role)
    await ctx.send(f"⛓️ {member.mention} is locked up.")

@bot.hybrid_command(name="unjail", description="Releases a user and restores roles.")
@commands.has_permissions(administrator=True)
async def unjail(ctx, member: discord.Member):
    jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
    if jail_role in member.roles: await member.remove_roles(jail_role)
    for role_id in db["jailed"].pop(str(member.id), []):
        role = ctx.guild.get_role(role_id)
        if role: await member.add_roles(role)
    save_db(db)
    await ctx.send(f"🔓 {member.mention} made bail.")

@bot.hybrid_command(name="nuke", description="Deletes and clones the current channel.")
@commands.has_permissions(administrator=True)
async def nuke(ctx):
    pos = ctx.channel.position
    new_channel = await ctx.channel.clone()
    await ctx.channel.delete()
    await new_channel.edit(position=pos)
    await new_channel.send("☢️ **TACTICAL NUKE INCOMING!** 💥")

@bot.hybrid_command(name="purge", description="Deletes multiple messages.")
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Swept {amount} messages.", delete_after=3)

@bot.hybrid_command(name="lock", description="Locks the current channel.")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Channel locked.")

@bot.hybrid_command(name="unlock", description="Unlocks the current channel.")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Channel unlocked.")

# ==========================================
# 6. HYBRID WARNING SYSTEM
# ==========================================

@bot.hybrid_command(name="warn", description="Warns a user.")
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason: str = "Bad vibes"):
    uid = str(member.id)
    if uid not in db["warns"]: db["warns"][uid] = []
    db["warns"][uid].append({"id": len(db["warns"][uid])+1, "reason": reason, "mod": ctx.author.name})
    save_db(db)
    await ctx.send(f"⚠️ {member.mention} warned. Reason: {reason}")

@bot.hybrid_command(name="warnings", description="Shows a user's warnings.")
@commands.has_permissions(kick_members=True)
async def warnings(ctx, member: discord.Member):
    warns = db["warns"].get(str(member.id), [])
    if not warns: return await ctx.send("✅ Clean record.")
    embed = discord.Embed(title=f"Warnings for {member.name}", color=discord.Color.orange())
    for w in warns: embed.add_field(name=f"ID: {w['id']} | Mod: {w['mod']}", value=w['reason'], inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="clearwarns", description="Clears all warnings for a user.")
@commands.has_permissions(administrator=True)
async def clearwarns(ctx, member: discord.Member):
    db["warns"].pop(str(member.id), None)
    save_db(db)
    await ctx.send(f"🗑️ Cleared warnings for {member.mention}.")

@bot.hybrid_command(name="filterword", description="Add or remove words from the automod blacklist.")
@commands.has_permissions(administrator=True)
async def filterword(ctx, action: str, word: str):
    if action.lower() == "add":
        db["config"]["filterwords"].append(word.lower())
        await ctx.send(f"🚫 Added `{word}` to blacklist.")
    elif action.lower() == "remove" and word.lower() in db["config"]["filterwords"]:
        db["config"]["filterwords"].remove(word.lower())
        await ctx.send(f"✅ Removed `{word}` from blacklist.")
    save_db(db)

# ==========================================
# 7. HYBRID INFO & GAMES
# ==========================================

@bot.hybrid_command(name="ping", description="Check bot latency.")
async def ping(ctx): 
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.hybrid_command(name="avatar", description="Get a user's profile picture.")
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member.name}'s Avatar", color=discord.Color.blue())
    embed.set_image(url=member.avatar.url if member.avatar else member.default_avatar.url)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="serverinfo", description="View server stats.")
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"Server Info - {guild.name}", color=discord.Color.gold())
    embed.add_field(name="👑 Owner", value=guild.owner.mention)
    embed.add_field(name="👥 Members", value=guild.member_count)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="eightball", description="Ask the magic 8ball.")
async def eightball(ctx, *, question: str):
    responses = ["Yes definitely.", "Ask again later.", "My sources say no."]
    await ctx.send(f"🎱 **Question:** {question}\n**Answer:** {random.choice(responses)}")

@bot.hybrid_command(name="coinflip", description="Flip a coin.")
async def coinflip(ctx):
    await ctx.send(f"🪙 You flipped: **{random.choice(['Heads', 'Tails'])}**")

@bot.hybrid_command(name="hack", description="Fake hack a user.")
async def hack(ctx, member: discord.Member):
    await ctx.send(f"💻 Hacking {member.name}...\n✅ Successfully hacked {member.mention}. Selling their search history for 5 robux.")

# ==========================================
# 8. HYBRID ECONOMY SYSTEM
# ==========================================

@bot.hybrid_command(name="bal", description="Check your coin balance.")
async def bal(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    await ctx.send(f"💰 {member.name} has **{get_eco(uid)}** coins.")

@bot.hybrid_command(name="work", description="Work to earn coins.")
async def work(ctx):
    uid = str(ctx.author.id)
    earned = random.randint(50, 200)
    db["economy"][uid] = get_eco(uid) + earned
    save_db(db)
    await ctx.send(f"💼 You worked a grueling shift and earned **{earned} coins**!")

@bot.hybrid_command(name="crime", description="Commit a crime for coins (risky).")
async def crime(ctx):
    uid = str(ctx.author.id)
    if random.choice([True, False]):
        earned = random.randint(200, 500)
        db["economy"][uid] = get_eco(uid) + earned
        save_db(db)
        await ctx.send(f"🥷 You robbed a bank and got away with **{earned} coins**!")
    else:
        lost = random.randint(50, 150)
        db["economy"][uid] = max(0, get_eco(uid) - lost)
        save_db(db)
        await ctx.send(f"🚓 You got caught by the feds and fined **{lost} coins**.")

# ==========================================
# 9. AUTOMOD LISTENER
# ==========================================

@bot.listen('on_message')
async def auto_mod(message):
    if message.author.bot or not message.guild: return
    for word in db["config"]["filterwords"]:
        if word in message.content.lower():
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention}, that word is banned!", delete_after=5)
            return

# ==========================================
# 10. RENDER BOOT UP
# ==========================================
if __name__ == "__main__":
    keep_alive()
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
