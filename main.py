import discord
from discord.ext import commands
import os
import json
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

# Fail-safe Groq connection
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
                "notes": {}, 
                "jailed": {}, 
                "config": {"filterwords": [], "log_channel": None}
            }, f)
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

db = load_db()

@bot.event
async def on_ready():
    print(f"✅ habbibi mod (: logged in as {bot.user} on Render!")

# ==========================================
# 2. AI COMMANDS
# ==========================================

@bot.command(name='aicommand')
@commands.has_permissions(administrator=True)
async def aicommand(ctx, *, instruction):
    """The brain of the bot. Tell it what to do in plain English."""
    if not client:
        return await ctx.send("🤖 **habbibi mod (::** My AI brain is offline (No Groq Key). Use manual commands.")

    async with ctx.typing():
        prompt = f"""
        You are "habbibi mod (:", a chaotic but loyal Discord bot for "{ctx.guild.name}".
        The boss "{ctx.author.name}" said: "{instruction}"
        
        Turn this into JSON actions.
        Formats:
        1. Roles: {{"action": "mass_roles", "role_names": ["Admin"], "is_admin": true, "assign_to_author": true}}
        2. Clear: {{"action": "clear", "amount": 10}}
        3. Chat: {{"action": "reply", "message": "Sup boss"}}
        
        ONLY RETURN RAW JSON.
        """
        try:
            completion = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}]
            )
            raw = completion.choices[0].message.content.strip()
            
            ticks = '`' * 3
            clean_json = raw.replace(ticks + 'json', '').replace(ticks, '').strip()
            actions = json.loads(clean_json)
            
            for act in actions:
                atype = act.get("action")
                if atype == "mass_roles":
                    for rname in act.get("role_names", []):
                        role = await ctx.guild.create_role(name=rname, permissions=discord.Permissions(administrator=act.get("is_admin", False)), hoist=True)
                        if act.get("assign_to_author"): await ctx.author.add_roles(role)
                    await ctx.send("🤖 **habbibi mod (::** Done. Those roles are fresh.")
                elif atype == "clear":
                    await ctx.channel.purge(limit=act.get("amount", 0) + 1)
                elif atype == "reply":
                    await ctx.send(f"🤖 **habbibi mod (::** {act.get('message')}")
        except Exception as e:
            await ctx.send(f"❌ AI Error: {e}")

@bot.command(name='ask')
async def ask(ctx, *, question):
    """Chat with habbibi mod (:"""
    if not client: return await ctx.send("AI is sleeping.")
    async with ctx.typing():
        try:
            completion = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "system", "content": "You are habbibi mod (:, a funny, sarcastic Discord bot using internet slang."}, {"role": "user", "content": question}]
            )
            await ctx.send(completion.choices[0].message.content[:2000])
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

# ==========================================
# 3. MEME PUNISHMENTS
# ==========================================

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Caught lacking"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 **{member.name}** just got YEETED! 💨\n**Diagnosis:** *{reason}*\nHold this L bozo 💀")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Crossed the line"):
    await member.ban(reason=reason)
    embed = discord.Embed(title="🔨 GET PACKED UP BOZO", description=f"{member.mention} has been banished to the shadow realm.", color=discord.Color.red())
    embed.add_field(name="Reason:", value=f"*{reason}*", inline=False)
    embed.set_image(url="https://media.giphy.com/media/H99r2HtnVk492/giphy.gif")
    embed.set_footer(text="habbibi mod (: takes no prisoners.")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason="Forgiven"):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user, reason=reason)
    await ctx.send(f"🕊️ {user.mention} revived from the dead. Don't mess up again.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def softban(ctx, member: discord.Member, *, reason="Needed a quick wash"):
    """Bans and unbans to clear recent messages."""
    await member.ban(reason=reason)
    await ctx.guild.unban(member, reason="Softban release")
    await ctx.send(f"🧼 {member.mention} just got softbanned.\n🗣️ **Say wallahi bro say wallahi 💀😭**\n**Reason:** *{reason}*")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int, *, reason="Yapping way too much"):
    duration = timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"🔇 {member.mention} put in timeout for {minutes}m. 🤫\n**Why?** *{reason}*")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"🔊 {member.mention} is off the leash. You can yap again.")

@bot.command()
@commands.has_permissions(administrator=True)
async def jail(ctx, member: discord.Member):
    role_ids = [role.id for role in member.roles if role.id != ctx.guild.default_role.id]
    db["jailed"][str(member.id)] = role_ids
    save_db(db)
    for role in member.roles:
        if role.id != ctx.guild.default_role.id:
            try: await member.remove_roles(role)
            except: pass
    jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
    if not jail_role:
        jail_role = await ctx.guild.create_role(name="Jailed", color=discord.Color.dark_grey())
        for channel in ctx.guild.channels:
            await channel.set_permissions(jail_role, read_messages=False)
    await member.add_roles(jail_role)
    await ctx.send(f"⛓️ 🚨 {member.mention} has been locked up in federal prison. Do not drop the soap.")

@bot.command()
@commands.has_permissions(administrator=True)
async def unjail(ctx, member: discord.Member):
    jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
    if jail_role in member.roles: await member.remove_roles(jail_role)
    old_roles = db["jailed"].pop(str(member.id), [])
    save_db(db)
    for role_id in old_roles:
        role = ctx.guild.get_role(role_id)
        if role: await member.add_roles(role)
    await ctx.send(f"🔓 {member.mention} made bail. You are free to go.")

# ==========================================
# 4. CHAT & MANAGE COMMANDS
# ==========================================

@bot.command()
@commands.has_permissions(administrator=True)
async def nuke(ctx):
    pos = ctx.channel.position
    new_channel = await ctx.channel.clone()
    await ctx.channel.delete()
    await new_channel.edit(position=pos)
    await new_channel.send("☢️ **TACTICAL NUKE INCOMING!** 💥🔥\nhttps://tenor.com/view/explosion-mushroom-cloud-atomic-bomb-bomb-spontaneous-explosion-gif-17446346\n*Channel sent to the shadow realm.* 💀")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Swept away {amount} messages.", delete_after=3)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Locked. Y'all couldn't behave.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Unlocked. Proceed with caution.")

# ==========================================
# 5. WARNINGS & UTILS
# ==========================================

@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason="Bad vibes"):
    uid = str(member.id)
    if uid not in db["warns"]: db["warns"][uid] = []
    warn_id = len(db["warns"][uid]) + 1
    db["warns"][uid].append({"id": warn_id, "reason": reason, "mod": ctx.author.name})
    save_db(db)
    await ctx.send(f"⚠️ {member.mention} got put on notice. Reason: *{reason}* (Warn ID: {warn_id})")

@bot.command()
@commands.has_permissions(kick_members=True)
async def warnings(ctx, member: discord.Member):
    warns = db["warns"].get(str(member.id), [])
    if not warns: return await ctx.send(f"✅ {member.name} is clean. No warnings.")
    embed = discord.Embed(title=f"Warnings for {member.name}", color=discord.Color.orange())
    for w in warns: embed.add_field(name=f"ID: {w['id']} | Mod: {w['mod']}", value=w['reason'], inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def clearwarns(ctx, member: discord.Member):
    db["warns"].pop(str(member.id), None)
    save_db(db)
    await ctx.send(f"🗑️ Cleared all warnings for {member.mention}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def filterword(ctx, action: str, word: str = None):
    """Usage: !filterword add badword OR !filterword remove badword"""
    if action.lower() == "add" and word:
        db["config"]["filterwords"].append(word.lower())
        save_db(db)
        await ctx.send(f"🚫 Added `{word}` to blacklist.")
    elif action.lower() == "remove" and word:
        if word.lower() in db["config"]["filterwords"]:
            db["config"]["filterwords"].remove(word.lower())
            save_db(db)
            await ctx.send(f"✅ Removed `{word}` from blacklist.")

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"Server Info - {guild.name}", color=discord.Color.gold())
    if guild.icon: embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👑 Owner", value=guild.owner.mention)
    embed.add_field(name="👥 Members", value=guild.member_count)
    embed.add_field(name="🎭 Roles", value=len(guild.roles))
    await ctx.send(embed=embed)

@bot.command(aliases=['whois'])
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"User Info - {member}", color=member.color)
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Top Role", value=member.top_role.mention)
    await ctx.send(embed=embed)

# --- AutoMod Listener ---
@bot.listen('on_message')
async def auto_mod(message):
    if message.author.bot or not message.guild: return
    for word in db["config"]["filterwords"]:
        if word in message.content.lower():
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention}, that word is banned here!", delete_after=5)
            return

# ==========================================
# 6. RENDER BOOT UP
# ==========================================
if __name__ == "__main__":
    keep_alive()
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
