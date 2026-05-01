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

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump({
                "warns": {}, 
                "jailed": {}, 
                "config": {"filterwords": [], "ai_channel": None}, 
                "economy": {},
                "custom_commands": {} # AI stores new commands here!
            }, f)
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

# Helper function for AI to find users
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
# 2. AUTONOMOUS AI & DM CHAT (The Brain)
# ==========================================

@bot.listen('on_message')
async def ai_auto_chat(message):
    if message.author.bot: return

    # 1. AI Custom Commands Logic
    if message.content.startswith('!') and len(message.content) > 1:
        cmd = message.content[1:].split()[0].lower()
        if cmd in db["custom_commands"]:
            await message.channel.send(db["custom_commands"][cmd])
            return # Don't process anything else

    # 2. DM & Dedicated AI Channel Logic
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_ai_channel = (message.channel.id == db["config"].get("ai_channel"))

    if (is_dm or is_ai_channel) and not message.content.startswith('!'):
        if not client: return
        async with message.channel.typing():
            try:
                system_prompt = "You are habbibi mod (:, a chaotic, helpful, and sarcastic Discord bot. You are chatting with a user. Be concise, answer doubts, and keep the internet slang."
                if is_dm: system_prompt += " You are in their DMs providing 1-on-1 support."
                
                completion = client.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message.content}
                    ]
                )
                await message.channel.send(completion.choices[0].message.content[:2000])
            except Exception as e:
                await message.channel.send("❌ My AI brain glitched.")

@bot.command()
@commands.has_permissions(administrator=True)
async def setaichannel(ctx):
    """Sets the current channel for the AI to auto-reply to everything."""
    db["config"]["ai_channel"] = ctx.channel.id
    save_db(db)
    await ctx.send("🤖 **AI Channel Set!** I will now reply to every message sent in this channel automatically.")

@bot.command()
@commands.has_permissions(administrator=True)
async def unsetaichannel(ctx):
    """Stops the AI from auto-replying in the channel."""
    db["config"]["ai_channel"] = None
    save_db(db)
    await ctx.send("🔇 **AI Channel Disabled.** I will only speak when spoken to.")

# ==========================================
# 3. OMNIPOTENT AI COMMANDER
# ==========================================

@bot.hybrid_command(name='aicommand', description="The Master AI brain. It can moderate, create commands, and control the economy.")
@app_commands.describe(instruction="What do you want the bot to do?")
@commands.has_permissions(administrator=True)
async def aicommand(ctx, *, instruction: str):
    if not client:
        return await ctx.send("🤖 **habbibi mod (::** AI is offline.")

    await ctx.defer()
    prompt = f"""
    You are "habbibi mod (:", an omnipotent Discord moderation bot.
    The boss "{ctx.author.name}" said: "{instruction}"
    
    Turn this into a JSON array of actions. 
    FORMATS YOU MUST USE:
    1. Reply: {{"action": "reply", "message": "text"}}
    2. Ban: {{"action": "ban", "target": "username or mention", "reason": "text"}}
    3. Kick: {{"action": "kick", "target": "username or mention", "reason": "text"}}
    4. Mute: {{"action": "mute", "target": "username or mention", "minutes": 10}}
    5. Jail: {{"action": "jail", "target": "username or mention"}}
    6. Clear: {{"action": "clear", "amount": 10}}
    7. Nuke: {{"action": "nuke"}}
    8. Give Coins: {{"action": "give_coins", "target": "username or mention", "amount": 100}}
    9. Create Command: {{"action": "create_command", "trigger": "word", "reply": "what the bot should say"}}
    
    ONLY RETURN RAW JSON.
    """
    try:
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = completion.choices[0].message.content.strip()
        clean_json = raw.replace('```json', '').replace('```', '').strip()
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
                
            elif atype == "kick" and member:
                await member.kick(reason=act.get("reason", "AI Kick"))
                await ctx.send(f"👢 AI Yeeted {member.mention}.")
                
            elif atype == "mute" and member:
                mins = int(act.get("minutes", 10))
                await member.timeout(timedelta(minutes=mins))
                await ctx.send(f"🔇 AI Muted {member.mention} for {mins}m.")
                
            elif atype == "jail" and member:
                db["jailed"][str(member.id)] = [r.id for r in member.roles if r.id != ctx.guild.default_role.id]
                save_db(db)
                for role in member.roles[1:]:
                    try: await member.remove_roles(role)
                    except: pass
                jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
                if not jail_role:
                    jail_role = await ctx.guild.create_role(name="Jailed", color=discord.Color.dark_grey())
                    for c in ctx.guild.channels: await c.set_permissions(jail_role, read_messages=False)
                await member.add_roles(jail_role)
                await ctx.send(f"⛓️ AI Locked up {member.mention}.")
                
            elif atype == "clear":
                await ctx.channel.purge(limit=int(act.get("amount", 0)) + 1)
                
            elif atype == "nuke":
                pos = ctx.channel.position
                new_channel = await ctx.channel.clone()
                await ctx.channel.delete()
                await new_channel.edit(position=pos)
                await new_channel.send("☢️ **AI INITIATED TACTICAL NUKE!** 💥")
                
            elif atype == "give_coins" and member:
                amt = int(act.get("amount", 0))
                uid = str(member.id)
                db["economy"][uid] = get_eco(uid) + amt
                save_db(db)
                await ctx.send(f"🏦 AI printed {amt} coins for {member.mention}.")
                
            elif atype == "create_command":
                trigger = act.get("trigger", "").lower().replace("!", "")
                reply_txt = act.get("reply", "No reply set.")
                db["custom_commands"][trigger] = reply_txt
                save_db(db)
                await ctx.send(f"🧠 **AI Learned a New Trick!**\nYou can now type `!{trigger}` to use it.")
                
    except Exception as e:
        await ctx.send(f"❌ AI Error: {e}")

@bot.hybrid_command(name='ask', description="Ask the AI a question.")
async def ask(ctx, *, question: str):
    if not client: return await ctx.send("AI is sleeping.")
    await ctx.defer()
    try:
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": "You are habbibi mod (:, a funny, sarcastic Discord bot using internet slang."},
                {"role": "user", "content": question}
            ]
        )
        await ctx.send(completion.choices[0].message.content[:2000])
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ==========================================
# 4. STANDARD MODERATION
# ==========================================

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Caught lacking"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 **{member.name}** just got YEETED! 💨 Reason: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Crossed the line"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 {member.mention} has been banished. Reason: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason="Forgiven"):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user, reason=reason)
    await ctx.send(f"🕊️ {user.mention} revived from the dead.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int, *, reason="Yapping"):
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    await ctx.send(f"🔇 {member.mention} timed out for {minutes}m.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"🔊 {member.mention} is off the leash.")

@bot.command()
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

@bot.command()
@commands.has_permissions(administrator=True)
async def unjail(ctx, member: discord.Member):
    jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
    if jail_role in member.roles: await member.remove_roles(jail_role)
    for role_id in db["jailed"].pop(str(member.id), []):
        role = ctx.guild.get_role(role_id)
        if role: await member.add_roles(role)
    save_db(db)
    await ctx.send(f"🔓 {member.mention} made bail.")

@bot.command()
@commands.has_permissions(administrator=True)
async def nuke(ctx):
    pos = ctx.channel.position
    new_channel = await ctx.channel.clone()
    await ctx.channel.delete()
    await new_channel.edit(position=pos)
    await new_channel.send("☢️ **TACTICAL NUKE INCOMING!** 💥")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Swept {amount} messages.", delete_after=3)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Channel locked.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Channel unlocked.")

# ==========================================
# 5. WARNING SYSTEM
# ==========================================

@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason="Bad vibes"):
    uid = str(member.id)
    if uid not in db["warns"]: db["warns"][uid] = []
    db["warns"][uid].append({"id": len(db["warns"][uid])+1, "reason": reason, "mod": ctx.author.name})
    save_db(db)
    await ctx.send(f"⚠️ {member.mention} warned. Reason: {reason}")

@bot.command()
@commands.has_permissions(kick_members=True)
async def warnings(ctx, member: discord.Member):
    warns = db["warns"].get(str(member.id), [])
    if not warns: return await ctx.send("✅ Clean record.")
    embed = discord.Embed(title=f"Warnings for {member.name}", color=discord.Color.orange())
    for w in warns: embed.add_field(name=f"ID: {w['id']} | Mod: {w['mod']}", value=w['reason'], inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def clearwarns(ctx, member: discord.Member):
    db["warns"].pop(str(member.id), None)
    save_db(db)
    await ctx.send(f"🗑️ Cleared warnings for {member.mention}.")

@bot.command()
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
# 6. INFO & GAMES
# ==========================================

@bot.command()
async def ping(ctx): await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.command(aliases=['av'])
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member.name}'s Avatar", color=discord.Color.blue())
    embed.set_image(url=member.avatar.url if member.avatar else member.default_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"Server Info - {guild.name}", color=discord.Color.gold())
    embed.add_field(name="👑 Owner", value=guild.owner.mention)
    embed.add_field(name="👥 Members", value=guild.member_count)
    await ctx.send(embed=embed)

@bot.command(name="8ball")
async def eightball(ctx, *, question):
    responses = ["Yes definitely.", "Ask again later.", "My sources say no."]
    await ctx.send(f"🎱 **Question:** {question}\n**Answer:** {random.choice(responses)}")

@bot.command()
async def coinflip(ctx):
    await ctx.send(f"🪙 You flipped: **{random.choice(['Heads', 'Tails'])}**")

@bot.command()
async def hack(ctx, member: discord.Member):
    msg = await ctx.send(f"💻 Hacking {member.name}...")
    await asyncio.sleep(2)
    await msg.edit(content=f"✅ Successfully hacked {member.mention}. Selling their search history for 5 robux.")

# ==========================================
# 7. ECONOMY SYSTEM
# ==========================================

@bot.command()
async def bal(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    await ctx.send(f"💰 {member.name} has **{get_eco(uid)}** coins.")

@bot.command()
async def work(ctx):
    uid = str(ctx.author.id)
    earned = random.randint(50, 200)
    db["economy"][uid] = get_eco(uid) + earned
    save_db(db)
    await ctx.send(f"💼 You worked a grueling shift and earned **{earned} coins**!")

@bot.command()
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
# 8. AUTOMOD LISTENER
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
# 9. RENDER BOOT UP
# ==========================================
if __name__ == "__main__":
    keep_alive()
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
