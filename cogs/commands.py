import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import random
import time
import asyncio
from datetime import timedelta
from groq import Groq

# ==========================================
# DATABASE SETUP
# ==========================================
DB_FILE = "database.json"

def get_default_db():
    return {
        "warns": {}, "jailed": {}, 
        "config": {"filterwords": [], "ai_channel": None, "cmd_channel": None, "event_channel": None}, 
        "economy": {}, "levels": {}, "custom_commands": {}, "afk": {}
    }

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f: json.dump(get_default_db(), f)
    with open(DB_FILE, "r") as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

db = load_db()

class MasterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
        self.client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.ai_event_loop.start()

    def cog_unload(self):
        self.ai_event_loop.cancel()

    # --- HELPERS ---
    def ask_groq(self, messages):
        if not self.client: raise Exception("Groq API Key missing.")
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]:
            try:
                return self.client.chat.completions.create(model=model, messages=messages).choices[0].message.content.strip()
            except Exception: continue 
        raise Exception("All AI models failed.")

    def find_member(self, ctx, search_term):
        if not search_term: return None
        search_term = search_term.replace("<@", "").replace(">", "").replace("!", "")
        if search_term.isdigit(): return ctx.guild.get_member(int(search_term))
        for m in ctx.guild.members:
            if m.name.lower() == search_term.lower() or m.display_name.lower() == search_term.lower(): return m
        return None

    # ==========================================
    # 🌟 AI EVENT LOOP & LISTENERS
    # ==========================================
    @tasks.loop(minutes=60)
    async def ai_event_loop(self):
        if not self.client: return
        channel_id = db["config"].get("event_channel")
        if not channel_id: return
        channel = self.bot.get_channel(channel_id)
        if not channel: return
        try:
            prompt = "You are an AI community manager. Generate a highly engaging, modern Discord event, hot take, or scenario to spark chat activity. Keep it short. No JSON."
            reply = self.ask_groq([{"role": "user", "content": prompt}])
            embed = discord.Embed(title="🌟 Community Event", description=reply, color=discord.Color.blurple())
            await channel.send(embed=embed)
        except Exception as e: print(f"Event Error: {e}")

    @ai_event_loop.before_loop
    async def before_event_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        uid = str(message.author.id)

        # AFK Check
        if uid in db["afk"]:
            del db["afk"][uid]
            save_db(db)
            await message.channel.send(f"👋 Welcome back {message.author.mention}, I removed your AFK status.", delete_after=5)
        for mention in message.mentions:
            if str(mention.id) in db["afk"]:
                await message.channel.send(f"💤 **{mention.name}** is AFK: {db['afk'][str(mention.id)]}")

        # Automod
        for word in db["config"]["filterwords"]:
            if word in message.content.lower():
                await message.delete()
                return await message.channel.send(f"⚠️ {message.author.mention}, that word is banned!", delete_after=5)

        # XP System
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["xp"] += random.randint(10, 25)
        if db["levels"][uid]["xp"] >= (db["levels"][uid]["level"] * 100) * 1.5:
            db["levels"][uid]["level"] += 1
            save_db(db)
            await message.channel.send(f"🎉 **{message.author.mention} leveled up to Level {db['levels'][uid]['level']}!**")
        else: save_db(db)

        # Custom Commands
        if message.content.startswith('!') and len(message.content) > 1:
            cmd = message.content[1:].split()[0].lower()
            if cmd in db["custom_commands"]: return await message.channel.send(db["custom_commands"][cmd])

        # AI Auto-Chat
        if message.channel.id == db["config"].get("ai_channel") and not message.content.startswith(('!', '/')):
            if not self.client: return
            async with message.channel.typing():
                try:
                    reply = self.ask_groq([{"role": "system", "content": "You are habbibi mod (:, a chaotic, funny Discord bot."}, {"role": "user", "content": message.content}])
                    await message.channel.send(reply[:2000])
                except Exception as e: await message.channel.send(f"❌ AI glitched: {e}")

    # ==========================================
    # ⚙️ SERVER CONFIGURATION & DEPLOYER
    # ==========================================
    @commands.hybrid_command(name="setaichannel", description="Sets the current channel for the AI to auto-reply.")
    @commands.has_permissions(administrator=True)
    async def setaichannel(self, ctx):
        db["config"]["ai_channel"] = ctx.channel.id
        save_db(db)
        await ctx.send(f"🤖 **AI Channel Set!** I will now auto-reply to everything in {ctx.channel.mention}.")

    @commands.hybrid_command(name="setcmdchannel", description="Locks normal bot commands to the current channel.")
    @commands.has_permissions(administrator=True)
    async def setcmdchannel(self, ctx):
        db["config"]["cmd_channel"] = ctx.channel.id
        save_db(db)
        await ctx.send(f"🔒 **Command Channel Set!** Normal users must now use commands in {ctx.channel.mention}.")

    @commands.hybrid_command(name="seteventchannel", description="Sets where the hourly AI events will trigger.")
    @commands.has_permissions(administrator=True)
    async def seteventchannel(self, ctx):
        db["config"]["event_channel"] = ctx.channel.id
        save_db(db)
        await ctx.send(f"🌟 **Event Channel Set!** Hourly AI drops will happen in {ctx.channel.mention}.")

    @commands.hybrid_command(name="deployserver", description="Wipes the server and builds a Modern Community layout.")
    @commands.has_permissions(administrator=True)
    async def deployserver(self, ctx):
        await ctx.send("⚠️ **CLEAN SLATE PROTOCOL.** Wiping and building modern layout. Please wait...")
        guild = ctx.guild
        for channel in guild.channels:
            try: await channel.delete(); await asyncio.sleep(0.5)
            except: pass
        for role in guild.roles:
            if role.name != "@everyone" and not role.managed and role < ctx.guild.me.top_role:
                try: await role.delete(); await asyncio.sleep(0.5)
                except: pass

        roles_to_make = [{"name": "Admin", "color": discord.Color.red()}, {"name": "Moderator", "color": discord.Color.orange()}, {"name": "Jailed", "color": discord.Color.dark_grey()}]
        created_roles = {}
        for r in roles_to_make:
            created_roles[r["name"]] = await guild.create_role(name=r["name"], color=r["color"], permissions=discord.Permissions(administrator=(r["name"]=="Admin")), hoist=True)
            await asyncio.sleep(1)
        await ctx.author.add_roles(created_roles["Admin"])

        cat_info = await guild.create_category("📌 INFORMATION")
        await guild.create_text_channel("rules", category=cat_info)
        
        cat_chat = await guild.create_category("💬 CHAT")
        gen_chat = await guild.create_text_channel("general", category=cat_chat)
        bot_cmds = await guild.create_text_channel("bot-commands", category=cat_chat)
        ai_chat = await guild.create_text_channel("talk-to-ai", category=cat_chat)
        
        await guild.create_category("🔊 VOICE")
        await guild.create_voice_channel("General VC", category=discord.utils.get(guild.categories, name="🔊 VOICE"))

        for cat in guild.categories: await cat.set_permissions(created_roles["Jailed"], read_messages=False)

        db["config"]["cmd_channel"] = bot_cmds.id
        db["config"]["ai_channel"] = ai_chat.id
        db["config"]["event_channel"] = gen_chat.id
        save_db(db)
        await gen_chat.send(f"{ctx.author.mention} ✅ Deployment Complete. Setup bound.")

    # ==========================================
    # 🧠 GOD-MODE AI & INTELLIGENCE
    # ==========================================
    @commands.hybrid_command(name='aicommand', description="Master AI brain. Execute any command or dynamic python code.")
    @app_commands.describe(instruction="What do you want the bot to do?")
    @commands.has_permissions(administrator=True)
    async def aicommand(self, ctx, *, instruction: str):
        if not self.client: return await ctx.send("🤖 AI offline.")
        await ctx.defer()
        
        prompt = f"""
        You are an omnipotent Discord bot. The boss said: "{instruction}"
        Output a JSON array of actions:
        1. Reply: {{"action": "reply", "message": "text"}}
        2. Ban: {{"action": "ban", "target": "username"}}
        3. Execute Python: {{"action": "execute", "code": "await ctx.send('Done!')"}}
        
        EXECUTE RULES:
        - Write valid discord.py async code. Access: 'ctx', 'bot', 'discord', 'asyncio', 'db'.
        - Use \\n for newlines.
        - Add 'await asyncio.sleep(2)' between channel edits.
        STRICTLY OUTPUT A JSON ARRAY.
        """
        try:
            raw = self.ask_groq([{"role": "user", "content": prompt}])
            start_idx, end_idx = raw.find('['), raw.rfind(']')
            clean_json = raw[start_idx:end_idx+1] if start_idx != -1 else raw.replace('```json', '').replace('```python', '').replace('```', '').strip()
            if clean_json.startswith('{'): clean_json = f"[{clean_json}]"
                
            actions = json.loads(clean_json)
            for act in actions:
                atype = act.get("action")
                if atype == "reply": await ctx.send(f"🤖 {act.get('message')}")
                elif atype == "ban":
                    m = self.find_member(ctx, act.get("target"))
                    if m: await m.ban(reason="AI Ban"); await ctx.send(f"✅ Banned {m.mention}")
                elif atype == "execute":
                    code = act.get("code", "")
                    msg = await ctx.send("⚡ **Executing Python...**")
                    try:
                        wrapped = f"async def __ai_exec():\n" + "\n".join([f"    {line}" for line in code.split("\n")])
                        exec_env = {'discord': discord, 'bot': self.bot, 'ctx': ctx, 'asyncio': asyncio, 'db': db}
                        exec(wrapped, exec_env)
                        await exec_env['__ai_exec']()
                        await msg.edit(content="✅ **Execution Successful!**")
                    except Exception as err: await msg.edit(content=f"⚠️ **Failed:**\n```py\n{err}```")
        except Exception as e: await ctx.send(f"❌ Error: {e}")

    @commands.hybrid_command(name="tldr", description="AI summarizes the last 50 messages.")
    async def tldr(self, ctx):
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        messages = [msg.content async for msg in ctx.channel.history(limit=50) if msg.content]
        chat_log = "\n".join(messages)
        reply = self.ask_groq([{"role": "system", "content": "Summarize this chat log briefly."}, {"role": "user", "content": chat_log}])
        await ctx.send(f"📜 **TL;DR:** {reply}")

    @commands.hybrid_command(name="vibecheck", description="AI analyzes a user's recent vibe.")
    async def vibecheck(self, ctx, member: discord.Member):
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        messages = [msg.content async for msg in ctx.channel.history(limit=100) if msg.author == member and msg.content]
        if not messages: return await ctx.send("No recent messages to analyze.")
        reply = self.ask_groq([{"role": "system", "content": "Analyze the vibe of these messages. Are they toxic, chill, funny? Be brutal but funny."}, {"role": "user", "content": "\n".join(messages[:10])}])
        await ctx.send(f"🔮 **Vibe Check for {member.name}:**\n{reply}")

    # ==========================================
    # 🛡️ ADVANCED MODERATION
    # ==========================================
    @commands.hybrid_command(name="purge", description="Deletes multiple messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 Swept {amount} messages.", delete_after=3)

    @commands.hybrid_command(name="mute", description="Time out a member.")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, minutes: int, *, reason: str="No reason"):
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await ctx.send(f"🔇 {member.mention} timed out for {minutes}m.")
        
    @commands.hybrid_command(name="unmute", description="Un-timeout a member.")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(f"🔊 {member.mention} has been unmuted.")

    @commands.hybrid_command(name="jail", description="Strips roles and locks user.")
    @commands.has_permissions(administrator=True)
    async def jail(self, ctx, member: discord.Member):
        db["jailed"][str(member.id)] = [role.id for role in member.roles if role.id != ctx.guild.default_role.id]
        save_db(db)
        for role in member.roles[1:]:
            try: await member.remove_roles(role)
            except: pass
        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jail_role: await member.add_roles(jail_role)
        await ctx.send(f"⛓️ {member.mention} locked up in federal prison.")

    @commands.hybrid_command(name="unjail", description="Releases user from jail.")
    @commands.has_permissions(administrator=True)
    async def unjail(self, ctx, member: discord.Member):
        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jail_role in member.roles: await member.remove_roles(jail_role)
        for role_id in db["jailed"].pop(str(member.id), []):
            role = ctx.guild.get_role(role_id)
            if role: await member.add_roles(role)
        save_db(db)
        await ctx.send(f"🔓 {member.mention} made bail.")

    @commands.hybrid_command(name="nuke", description="Clones and deletes channel.")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx):
        pos = ctx.channel.position
        new_channel = await ctx.channel.clone()
        await ctx.channel.delete()
        await new_channel.edit(position=pos)
        await new_channel.send("☢️ **TACTICAL NUKE INCOMING!** 💥")

    @commands.hybrid_command(name="kick", description="Kicks a user.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="Caught lacking"):
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.name} was kicked.")

    @commands.hybrid_command(name="ban", description="Bans a user.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="Crossed the line"):
        await member.ban(reason=reason)
        await ctx.send(f"🔨 {member.name} banished to the shadow realm.")

    @commands.hybrid_command(name="warn", description="Warns a user.")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason="Bad vibes"):
        uid = str(member.id)
        if uid not in db["warns"]: db["warns"][uid] = []
        db["warns"][uid].append(reason)
        save_db(db)
        await ctx.send(f"⚠️ {member.mention} warned. Reason: {reason}")

    @commands.hybrid_command(name="warnings", description="Shows a user's warnings.")
    async def warnings(self, ctx, member: discord.Member):
        warns = db["warns"].get(str(member.id), [])
        if not warns: return await ctx.send("✅ Clean record.")
        await ctx.send(f"⚠️ **Warnings for {member.name}:**\n" + "\n".join([f"- {w}" for w in warns]))

    @commands.hybrid_command(name="clearwarns", description="Clears all warnings.")
    @commands.has_permissions(administrator=True)
    async def clearwarns(self, ctx, member: discord.Member):
        db["warns"].pop(str(member.id), None)
        save_db(db)
        await ctx.send(f"🗑️ Cleared warnings for {member.name}.")

    @commands.hybrid_command(name="lock", description="Locks current channel.")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🔒 Channel locked.")

    @commands.hybrid_command(name="unlock", description="Unlocks current channel.")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send("🔓 Channel unlocked.")

    @commands.hybrid_command(name="slowmode", description="Sets slowmode.")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"⏱️ Slowmode set to {seconds}s.")

    # ==========================================
    # 💰 RPG & ECONOMY (THE GRIND)
    # ==========================================
    @commands.hybrid_command(name="bal", description="Check coin balance.")
    async def bal(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        if str(member.id) not in db["economy"]: db["economy"][str(member.id)] = 0
        await ctx.send(f"💰 {member.name} has **{db['economy'][str(member.id)]}** coins.")

    @commands.hybrid_command(name="work", description="Work for coins.")
    @commands.cooldown(1, 3600, commands.BucketType.user) 
    async def work(self, ctx):
        uid = str(ctx.author.id)
        earned = random.randint(100, 300)
        if uid not in db["economy"]: db["economy"][uid] = 0
        db["economy"][uid] += earned
        save_db(db)
        await ctx.send(f"💼 Earned **{earned} coins**!")

    @commands.hybrid_command(name="crime", description="Commit a crime.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def crime(self, ctx):
        uid = str(ctx.author.id)
        if uid not in db["economy"]: db["economy"][uid] = 0
        if random.choice([True, False]):
            earned = random.randint(300, 700)
            db["economy"][uid] += earned
            await ctx.send(f"🥷 You hacked the mainframe for **{earned} coins**!")
        else:
            lost = random.randint(100, 250)
            db["economy"][uid] = max(0, db["economy"][uid] - lost)
            await ctx.send(f"🚓 Feds caught you. Paid **{lost} coins** fine.")
        save_db(db)

    @commands.hybrid_command(name="rob", description="Steal from another user.")
    @commands.cooldown(1, 7200, commands.BucketType.user)
    async def rob(self, ctx, member: discord.Member):
        uid, tid = str(ctx.author.id), str(member.id)
        if uid not in db["economy"]: db["economy"][uid] = 0
        if tid not in db["economy"]: db["economy"][tid] = 0
        if db["economy"][tid] < 100: return await ctx.send("❌ They are too poor to rob.")
        
        if random.choice([True, False]):
            stolen = random.randint(50, int(db["economy"][tid] * 0.2))
            db["economy"][tid] -= stolen
            db["economy"][uid] += stolen
            await ctx.send(f"🔫 You mugged {member.name} for **{stolen} coins**!")
        else:
            db["economy"][uid] = max(0, db["economy"][uid] - 200)
            await ctx.send(f"🛡️ They fought back! You lost **200 coins**.")
        save_db(db)

    @commands.hybrid_command(name="daily", description="Claim daily coins.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx):
        uid = str(ctx.author.id)
        if uid not in db["economy"]: db["economy"][uid] = 0
        db["economy"][uid] += 500
        save_db(db)
        await ctx.send("🎁 You claimed your daily **500 coins**!")

    @commands.hybrid_command(name="slots", description="Gamble coins on slots.")
    async def slots(self, ctx, bet: int):
        uid = str(ctx.author.id)
        if uid not in db["economy"] or db["economy"][uid] < bet or bet <= 0: return await ctx.send("❌ Not enough coins.")
        db["economy"][uid] -= bet
        reels = ["🍒", "🍋", "🍉", "⭐", "💎"]
        r1, r2, r3 = random.choice(reels), random.choice(reels), random.choice(reels)
        msg = f"🎰 | {r1} | {r2} | {r3} | 🎰\n"
        if r1 == r2 == r3:
            winnings = bet * 10
            db["economy"][uid] += winnings
            await ctx.send(msg + f"JACKPOT! You won **{winnings} coins**!")
        elif r1 == r2 or r2 == r3 or r1 == r3:
            winnings = int(bet * 1.5)
            db["economy"][uid] += winnings
            await ctx.send(msg + f"Small win! You got **{winnings} coins**.")
        else:
            await ctx.send(msg + "You lost. Better luck next time.")
        save_db(db)

    @commands.hybrid_command(name="coinflip", description="Gamble 50/50.")
    async def coinflip(self, ctx, bet: int, choice: str):
        choice = choice.lower()
        if choice not in ["heads", "tails"]: return await ctx.send("Pick heads or tails.")
        uid = str(ctx.author.id)
        if uid not in db["economy"] or db["economy"][uid] < bet or bet <= 0: return await ctx.send("❌ Not enough coins.")
        db["economy"][uid] -= bet
        result = random.choice(["heads", "tails"])
        if choice == result:
            db["economy"][uid] += bet * 2
            await ctx.send(f"🪙 It landed on {result}! You won **{bet*2} coins**!")
        else:
            await ctx.send(f"🪙 It landed on {result}. You lost.")
        save_db(db)

    @commands.hybrid_command(name="pay", description="Give someone coins.")
    async def pay(self, ctx, member: discord.Member, amount: int):
        uid, tid = str(ctx.author.id), str(member.id)
        if amount <= 0 or db["economy"].get(uid, 0) < amount: return await ctx.send("❌ Insufficient funds.")
        db["economy"][uid] -= amount
        db["economy"][tid] = db["economy"].get(tid, 0) + amount
        save_db(db)
        await ctx.send(f"💸 Paid {member.name} **{amount} coins**.")

    @commands.hybrid_command(name="level", description="Check chat Level.")
    async def level(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        lvl_data = db["levels"].get(str(member.id), {"xp": 0, "level": 1})
        await ctx.send(f"⭐ **{member.name}** is Level **{lvl_data['level']}** ({lvl_data['xp']} XP).")

    @commands.hybrid_command(name="quest", description="Go on an RPG quest.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def quest(self, ctx):
        uid = str(ctx.author.id)
        xp_gain = random.randint(50, 150)
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        if db["levels"][uid]["level"] >= 13000: return await ctx.send("🛑 Max Level 13,000 Reached!")
        db["levels"][uid]["xp"] += xp_gain
        save_db(db)
        await ctx.send(f"🗡️ Quest completed! Earned **{xp_gain} XP**! (Level {db['levels'][uid]['level']})")

    @commands.hybrid_command(name="hunt", description="Hunt for monsters.")
    @commands.cooldown(1, 1800, commands.BucketType.user)
    async def hunt(self, ctx):
        animal = random.choice(["Slime", "Goblin", "Dragon", "Rat"])
        reward = {"Slime": 50, "Goblin": 100, "Dragon": 1000, "Rat": 10}[animal]
        uid = str(ctx.author.id)
        if uid not in db["economy"]: db["economy"][uid] = 0
        db["economy"][uid] += reward
        save_db(db)
        await ctx.send(f"🏹 You hunted a **{animal}** and sold it for **{reward} coins**!")

    @commands.hybrid_command(name="mine", description="Mine for ores.")
    @commands.cooldown(1, 1800, commands.BucketType.user)
    async def mine(self, ctx):
        ore = random.choice(["Stone", "Iron", "Gold", "Diamond"])
        reward = {"Stone": 5, "Iron": 50, "Gold": 200, "Diamond": 800}[ore]
        uid = str(ctx.author.id)
        if uid not in db["economy"]: db["economy"][uid] = 0
        db["economy"][uid] += reward
        save_db(db)
        await ctx.send(f"⛏️ You mined **{ore}** and sold it for **{reward} coins**!")

    # ==========================================
    # 🤡 FUN, WEEB, & UTILITY
    # ==========================================
    @commands.hybrid_command(name="avatar", description="Get user PFP.")
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"{member.name}'s Avatar", color=discord.Color.blue())
        embed.set_image(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ping", description="Bot latency.")
    async def ping(self, ctx):
        await ctx.send(f"🏓 Pong! {round(self.bot.latency * 1000)}ms")

    @commands.hybrid_command(name="eightball", description="Ask a question.")
    async def eightball(self, ctx, *, question: str):
        res = random.choice(["Yes.", "No.", "Maybe.", "Definitely not.", "Without a doubt."])
        await ctx.send(f"🎱 **Q:** {question}\n**A:** {res}")

    @commands.hybrid_command(name="hack", description="Fake hack someone.")
    async def hack(self, ctx, member: discord.Member):
        msg = await ctx.send(f"💻 Hacking {member.name}...")
        await asyncio.sleep(1)
        await msg.edit(content="🕵️‍♂️ Finding IP Address...")
        await asyncio.sleep(1)
        await msg.edit(content=f"🌍 IP Found: 192.168.{random.randint(1,255)}.{random.randint(1,255)}")
        await asyncio.sleep(1)
        await msg.edit(content=f"✅ Successfully hacked {member.mention}. Selling history for 5 robux.")

    @commands.hybrid_command(name="powerlevel", description="Scan power level.")
    async def powerlevel(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        pwr = random.randint(10, 1000000)
        if pwr > 900000: await ctx.send(f"💥 {member.mention}'s power level is **{pwr:,}**! God tier!")
        else: await ctx.send(f"🔍 {member.mention}'s power level is **{pwr:,}**. Fodder.")

    @commands.hybrid_command(name="ship", description="Matchmake two people.")
    async def ship(self, ctx, m1: discord.Member, m2: discord.Member=None):
        m2 = m2 or ctx.author
        await ctx.send(f"❤️ **Ship:** {m1.name} x {m2.name}\n**Rating:** {random.randint(0,100)}%")

    @commands.hybrid_command(name="roast", description="Roast a user.")
    async def roast(self, ctx, member: discord.Member):
        roasts = ["You're like a cloud. When you disappear, it's a beautiful day.", "I'd agree with you but then we’d both be wrong."]
        await ctx.send(f"{member.mention} {random.choice(roasts)}")

    @commands.hybrid_command(name="susmeter", description="How sus are they?")
    async def susmeter(self, ctx, member: discord.Member=None):
        member = member or ctx.author
        await ctx.send(f"📮 {member.name} is **{random.randint(0,100)}%** sus.")

    @commands.hybrid_command(name="simpmeter", description="How much of a simp are they?")
    async def simpmeter(self, ctx, member: discord.Member=None):
        member = member or ctx.author
        await ctx.send(f"😳 {member.name} is **{random.randint(0,100)}%** simp.")

    @commands.hybrid_command(name="fakeban", description="Troll ban message.")
    async def fakeban(self, ctx, member: discord.Member):
        await ctx.send(f"🔨 **{member.name}** has been banned from the server.\nReason: Being too cringe.")

    @commands.hybrid_command(name="slap", description="Slap someone.")
    async def slap(self, ctx, member: discord.Member):
        await ctx.send(f"🤚 {ctx.author.mention} slapped {member.mention} straight across the face!")

    @commands.hybrid_command(name="hug", description="Hug someone.")
    async def hug(self, ctx, member: discord.Member):
        await ctx.send(f"🫂 {ctx.author.mention} gave {member.mention} a warm hug.")

    @commands.hybrid_command(name="afk", description="Set AFK status.")
    async def afk(self, ctx, *, reason: str="AFK"):
        db["afk"][str(ctx.author.id)] = reason
        save_db(db)
        await ctx.send(f"💤 {ctx.author.mention} is now AFK: {reason}")

    @commands.hybrid_command(name="poll", description="Create a poll.")
    async def poll(self, ctx, question: str):
        embed = discord.Embed(title="📊 Poll", description=question, color=discord.Color.green())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    @commands.hybrid_command(name="calc", description="Calculate math.")
    async def calc(self, ctx, expression: str):
        try: await ctx.send(f"🧮 Result: `{eval(expression, {'__builtins__': None}, {})}`")
        except: await ctx.send("❌ Invalid math expression.")

async def setup(bot):
    await bot.add_cog(MasterCommands(bot))
