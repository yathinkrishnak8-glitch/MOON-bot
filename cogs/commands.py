import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import random
import asyncio
from datetime import timedelta
from groq import Groq

# ==========================================
# DATABASE & MEMORY SETUP
# ==========================================
DB_FILE = "database.json"

def get_default_db():
    return {
        "warns": {}, "jailed": {}, "config": {"filterwords": [], "ai_channel": None, "cmd_channel": None, "event_channel": None, "antiraid": False}, 
        "economy": {}, "levels": {}, "custom_commands": {}, "afk": {}, "inventory": {}, "rep": {}, "bounties": {}
    }

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f: json.dump(get_default_db(), f)
    with open(DB_FILE, "r") as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

db = load_db()
snipes = {}
edit_snipes = {}

class MasterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
        self.client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.ai_event_loop.start()

    def cog_unload(self):
        self.ai_event_loop.cancel()

    def ask_groq(self, messages):
        if not self.client: raise Exception("Groq API Key missing.")
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]:
            try: return self.client.chat.completions.create(model=model, messages=messages).choices[0].message.content.strip()
            except: continue 
        raise Exception("AI failed.")

    def find_member(self, ctx, search_term):
        if not search_term: return None
        search_term = search_term.replace("<@", "").replace(">", "").replace("!", "")
        if search_term.isdigit(): return ctx.guild.get_member(int(search_term))
        for m in ctx.guild.members:
            if m.name.lower() == search_term.lower() or m.display_name.lower() == search_term.lower(): return m
        return None

    # ==========================================
    # LISTENERS (EVENTS, SNIPE, AFK, XP, DMs)
    # ==========================================
    @commands.Cog.listener()
    async def on_member_join(self, member):
        if db["config"].get("antiraid", False):
            try: await member.kick(reason="Anti-Raid is ON."); return
            except: pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.author.bot: snipes[message.channel.id] = {"content": message.content, "author": message.author.name}

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.author.bot: edit_snipes[before.channel.id] = {"before": before.content, "after": after.content, "author": before.author.name}

    @tasks.loop(minutes=60)
    async def ai_event_loop(self):
        if not self.client: return
        channel_id = db["config"].get("event_channel")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not channel: return
        try:
            prompt = "Generate a highly engaging, modern Discord event, hot take, or scenario to spark chat activity. Keep it short. No JSON."
            reply = self.ask_groq([{"role": "user", "content": prompt}])
            embed = discord.Embed(title="🌟 Community Event", description=reply, color=discord.Color.blurple())
            await channel.send(embed=embed)
        except: pass

    @ai_event_loop.before_loop
    async def before_event_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return

        # DM AI Chat Handler
        if not message.guild:
            if not self.client: return
            async with message.channel.typing():
                try:
                    reply = self.ask_groq([{"role": "system", "content": "You are habbibi mod (:, a chaotic, funny Discord bot. You are talking in private DMs."}, {"role": "user", "content": message.content}])
                    await message.channel.send(reply[:2000])
                except Exception as e: await message.channel.send(f"❌ AI glitched: {e}")
            return 

        uid = str(message.author.id)

        # AFK
        if uid in db["afk"]:
            del db["afk"][uid]; save_db(db)
            await message.channel.send(f"👋 {message.author.mention} removed your AFK status.", delete_after=5)
        for mention in message.mentions:
            if str(mention.id) in db["afk"]: await message.channel.send(f"💤 **{mention.name}** is AFK: {db['afk'][str(mention.id)]}")

        # Automod
        for word in db["config"]["filterwords"]:
            if word in message.content.lower():
                await message.delete()
                return await message.channel.send(f"⚠️ {message.author.mention}, that word is banned!", delete_after=5)

        # XP
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["xp"] += random.randint(10, 25)
        if db["levels"][uid]["xp"] >= (db["levels"][uid]["level"] * 100) * 1.5:
            db["levels"][uid]["level"] += 1; save_db(db)
            await message.channel.send(f"🎉 **{message.author.mention} leveled up to Level {db['levels'][uid]['level']}!**")
        else: save_db(db)

        # Custom commands
        if message.content.startswith('!') and len(message.content) > 1:
            cmd = message.content[1:].split()[0].lower()
            if cmd in db["custom_commands"]: return await message.channel.send(db["custom_commands"][cmd])

        # Server AI Auto-chat
        if message.channel.id == db["config"].get("ai_channel") and not message.content.startswith(('!', '/')):
            if not self.client: return
            async with message.channel.typing():
                try:
                    reply = self.ask_groq([{"role": "system", "content": "You are habbibi mod (:, a chaotic Discord bot."}, {"role": "user", "content": message.content}])
                    await message.channel.send(reply[:2000])
                except: pass

    # ==========================================
    # SERVER CONFIG & GOD MODE
    # ==========================================
    @commands.hybrid_command(name="setaichannel", description="Sets the AI auto-reply channel.")
    @commands.has_permissions(administrator=True)
    async def setaichannel(self, ctx):
        db["config"]["ai_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(f"🤖 **AI Channel Set!** {ctx.channel.mention}")

    @commands.hybrid_command(name="setcmdchannel", description="Locks commands to this channel.")
    @commands.has_permissions(administrator=True)
    async def setcmdchannel(self, ctx):
        db["config"]["cmd_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(f"🔒 **Command Channel Set!** {ctx.channel.mention}")

    @commands.hybrid_command(name="seteventchannel", description="Sets AI event channel.")
    @commands.has_permissions(administrator=True)
    async def seteventchannel(self, ctx):
        db["config"]["event_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(f"🌟 **Event Channel Set!** {ctx.channel.mention}")

    @commands.hybrid_command(name="deployserver", description="Wipes and builds server.")
    @commands.has_permissions(administrator=True)
    async def deployserver(self, ctx):
        await ctx.send("⚠️ **CLEAN SLATE PROTOCOL.**")
        guild = ctx.guild
        for c in guild.channels:
            try: await c.delete(); await asyncio.sleep(0.5)
            except: pass
        for r in guild.roles:
            if r.name != "@everyone" and not r.managed and r < ctx.guild.me.top_role:
                try: await r.delete(); await asyncio.sleep(0.5)
                except: pass
        roles = [{"name": "Admin", "color": discord.Color.red()}, {"name": "Moderator", "color": discord.Color.orange()}, {"name": "Jailed", "color": discord.Color.dark_grey()}]
        cr = {}
        for r in roles:
            try: cr[r["name"]] = await guild.create_role(name=r["name"], color=r["color"], permissions=discord.Permissions(administrator=(r["name"]=="Admin")), hoist=True); await asyncio.sleep(1)
            except: pass
        try: await ctx.author.add_roles(cr["Admin"])
        except: pass
        ci = await guild.create_category("📌 INFORMATION"); await guild.create_text_channel("rules", category=ci)
        cc = await guild.create_category("💬 CHAT"); gc = await guild.create_text_channel("general", category=cc); bc = await guild.create_text_channel("bot-commands", category=cc); ac = await guild.create_text_channel("talk-to-ai", category=cc)
        cv = await guild.create_category("🔊 VOICE"); await guild.create_voice_channel("General VC", category=cv)
        for cat in guild.categories:
            try: await cat.set_permissions(cr["Jailed"], read_messages=False)
            except: pass
        db["config"]["cmd_channel"] = bc.id; db["config"]["ai_channel"] = ac.id; db["config"]["event_channel"] = gc.id; save_db(db)
        await gc.send(f"{ctx.author.mention} ✅ Deployment Complete.")

    @commands.hybrid_command(name='aicommand', description="Master AI brain.")
    @commands.has_permissions(administrator=True)
    async def aicommand(self, ctx, *, instruction: str):
        if not self.client: return await ctx.send("🤖 AI offline.")
        await ctx.defer()
        prompt = f"""Omnipotent Discord bot. Boss says: "{instruction}"
        Output JSON array: 1. Reply: {{"action": "reply", "message": "text"}} 2. Execute Python: {{"action": "execute", "code": "await ctx.send('Done!')"}}
        STRICT RULES: JSON ARRAY ONLY. discord.py async code. Access: 'ctx', 'bot', 'discord', 'asyncio', 'db'."""
        try:
            raw = self.ask_groq([{"role": "user", "content": prompt}])
            start_idx, end_idx = raw.find('['), raw.rfind(']')
            clean_json = raw[start_idx:end_idx+1] if start_idx != -1 else raw.replace('```json', '').replace('```python', '').replace('```', '').strip()
            if clean_json.startswith('{'): clean_json = f"[{clean_json}]"
            actions = json.loads(clean_json)
            for act in actions:
                atype = act.get("action")
                if atype == "reply": await ctx.send(f"🤖 {act.get('message')}")
                elif atype == "execute":
                    msg = await ctx.send("⚡ **Executing Python...**")
                    try:
                        wrapped = f"async def __ai_exec():\n" + "\n".join([f"    {line}" for line in act.get("code", "").split("\n")])
                        exec_env = {'discord': discord, 'bot': self.bot, 'ctx': ctx, 'asyncio': asyncio, 'db': db}
                        exec(wrapped, exec_env); await exec_env['__ai_exec']()
                        await msg.edit(content="✅ **Execution Successful!**")
                    except Exception as err: await msg.edit(content=f"⚠️ **Failed:**\n```py\n{err}```")
        except Exception as e: await ctx.send(f"❌ Error: {e}")

    @commands.hybrid_command(name="forceevent", description="Force hourly event.")
    @commands.has_permissions(administrator=True)
    async def forceevent(self, ctx):
        await ctx.send("⏳ **Forcing AI Event...**")
        embed = discord.Embed(title="🌟 Event", description=self.ask_groq([{"role": "user", "content": "Generate a modern Discord event."}]), color=discord.Color.blurple())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="tldr", description="AI summarizes chat.")
    async def tldr(self, ctx):
        await ctx.defer(); log = "\n".join([m.content async for m in ctx.channel.history(limit=50) if m.content])
        await ctx.send(f"📜 **TL;DR:** {self.ask_groq([{'role': 'user', 'content': f'Summarize: {log}'}])}")

    @commands.hybrid_command(name="roast_history", description="AI roasts history.")
    async def roast_history(self, ctx, member: discord.Member):
        await ctx.defer(); log = "\n".join([m.content async for m in ctx.channel.history(limit=20) if m.author == member and m.content])
        await ctx.send(f"🔥 **Roast for {member.name}:**\n{self.ask_groq([{'role': 'user', 'content': f'Brutally roast this user based on these messages: {log}'}])}")

    @commands.hybrid_command(name="gothic_translate", description="Translate to dark fantasy.")
    async def gothic_translate(self, ctx, *, text: str):
        await ctx.defer()
        await ctx.send(f"🦇 **Gothic:**\n{self.ask_groq([{'role': 'user', 'content': f'Rewrite into dark gothic royal decree: {text}'}])}")

    @commands.hybrid_command(name="lore", description="AI generates server lore.")
    async def lore(self, ctx):
        await ctx.defer()
        await ctx.send(f"📖 **Server Lore:**\n{self.ask_groq([{'role': 'user', 'content': 'Write an epic dark fantasy backstory for this Discord server.'}])}")

    @commands.hybrid_command(name="code_fix", description="AI fixes broken code.")
    async def code_fix(self, ctx, *, code: str):
        await ctx.defer()
        await ctx.send(f"🛠️ **Code Fix:**\n{self.ask_groq([{'role': 'user', 'content': f'Fix this python code and explain briefly: {code}'}])}")

    @commands.hybrid_command(name="name_idea", description="AI suggests names.")
    async def name_idea(self, ctx):
        await ctx.defer()
        await ctx.send(f"💡 **Ideas:**\n{self.ask_groq([{'role': 'user', 'content': 'Give 5 cool discord role names.'}])}")

    @commands.hybrid_command(name="ai_image", description="Generate image.")
    async def ai_image(self, ctx, *, prompt: str): await ctx.send("🖼️ [Image generation API placeholder]")

    @commands.hybrid_command(name="vibecheck", description="AI vibe check.")
    async def vibecheck(self, ctx, member: discord.Member):
        await ctx.defer(); log = "\n".join([m.content async for m in ctx.channel.history(limit=20) if m.author == member and m.content])
        await ctx.send(f"🔮 **Vibe Check:**\n{self.ask_groq([{'role': 'user', 'content': f'Analyze the vibe of this user, be funny: {log}'}])}")

    @commands.hybrid_command(name="debate", description="Debate AI.")
    async def debate(self, ctx, *, topic: str):
        await ctx.defer(); await ctx.send(f"⚖️ **Debate:**\n{self.ask_groq([{'role': 'system', 'content': 'Argue against the user passionately.'}, {'role': 'user', 'content': topic}])}")

    @commands.hybrid_command(name="bossfight", description="AI runs a boss fight.")
    async def bossfight(self, ctx):
        await ctx.defer(); await ctx.send(f"⚔️ **BOSS FIGHT:**\n{self.ask_groq([{'role': 'user', 'content': 'Generate a short text-based boss fight scenario for chat.'}])}")
    # ==========================================
    # 🛡️ THE IRON FIST (Moderation)
    # ==========================================
    @commands.hybrid_command(name="tempban", description="Bans a user temporarily (in days).")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member, days: int):
        await member.ban(reason=f"Tempban for {days} days")
        await ctx.send(f"🔨 {member.name} temp-banned for {days} days.")
        await asyncio.sleep(days * 86400)
        await ctx.guild.unban(member, reason="Tempban expired")

    @commands.hybrid_command(name="tempmute", description="Mutes a user for a specific duration in minutes.")
    @commands.has_permissions(moderate_members=True)
    async def tempmute(self, ctx, member: discord.Member, minutes: int):
        await member.timeout(timedelta(minutes=minutes))
        await ctx.send(f"🔇 {member.mention} timed out for {minutes} minutes.")

    @commands.hybrid_command(name="slowmode", description="Sets slowmode in the channel.")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"⏱️ Slowmode set to {seconds}s.")

    @commands.hybrid_command(name="lockdown", description="Instantly locks all channels.")
    @commands.has_permissions(administrator=True)
    async def lockdown(self, ctx):
        for channel in ctx.guild.text_channels:
            try: await channel.set_permissions(ctx.guild.default_role, send_messages=False)
            except: pass
        await ctx.send("🚨 **SERVER LOCKDOWN INITIATED.**")

    @commands.hybrid_command(name="unlockdown", description="Reverses the lockdown.")
    @commands.has_permissions(administrator=True)
    async def unlockdown(self, ctx):
        for channel in ctx.guild.text_channels:
            try: await channel.set_permissions(ctx.guild.default_role, send_messages=True)
            except: pass
        await ctx.send("🔓 **SERVER LOCKDOWN LIFTED.**")

    @commands.hybrid_command(name="snipe", description="Recovers the last deleted message.")
    async def snipe(self, ctx):
        data = snipes.get(ctx.channel.id)
        if not data: return await ctx.send("Nothing to snipe!")
        embed = discord.Embed(description=data["content"], color=discord.Color.red())
        embed.set_author(name=data["author"])
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="editsnipe", description="Shows the original text of an edited message.")
    async def editsnipe(self, ctx):
        data = edit_snipes.get(ctx.channel.id)
        if not data: return await ctx.send("No recently edited messages!")
        embed = discord.Embed(title="Edited Message", color=discord.Color.orange())
        embed.add_field(name="Before", value=data["before"], inline=False)
        embed.add_field(name="After", value=data["after"], inline=False)
        embed.set_author(name=data["author"])
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="massnick", description="Changes everyone's nickname (Troll).")
    @commands.has_permissions(administrator=True)
    async def massnick(self, ctx, *, nickname: str):
        await ctx.send(f"🔄 Changing nicknames to {nickname}...")
        for member in ctx.guild.members:
            if not member.bot and member < ctx.guild.me.top_role:
                try: await member.edit(nick=nickname); await asyncio.sleep(0.5)
                except: pass
        await ctx.send("✅ Finished mass nickname change.")

    @commands.hybrid_command(name="strip", description="Removes all roles from a user.")
    @commands.has_permissions(administrator=True)
    async def strip(self, ctx, member: discord.Member):
        for role in member.roles[1:]:
            try: await member.remove_roles(role)
            except: pass
        await ctx.send(f"👕 Stripped {member.name} of all roles.")

    @commands.hybrid_command(name="roleall", description="Gives a specific role to everyone.")
    @commands.has_permissions(administrator=True)
    async def roleall(self, ctx, role: discord.Role):
        await ctx.send(f"🔄 Giving {role.name} to everyone...")
        for member in ctx.guild.members:
            if not member.bot:
                try: await member.add_roles(role); await asyncio.sleep(0.5)
                except: pass
        await ctx.send(f"✅ Everyone now has the {role.name} role.")

    @commands.hybrid_command(name="vckick", description="Disconnects a user from a voice channel.")
    @commands.has_permissions(move_members=True)
    async def vckick(self, ctx, member: discord.Member):
        if member.voice: await member.move_to(None); await ctx.send(f"👢 Kicked {member.name} from VC.")
        else: await ctx.send("User is not in a voice channel.")

    @commands.hybrid_command(name="vcmute", description="Server-mutes a user in VC.")
    @commands.has_permissions(mute_members=True)
    async def vcmute(self, ctx, member: discord.Member):
        if member.voice: await member.edit(mute=True); await ctx.send(f"🔇 Server-muted {member.name}.")

    @commands.hybrid_command(name="audit", description="Pulls a list of moderation actions.")
    @commands.has_permissions(administrator=True)
    async def audit(self, ctx, member: discord.Member):
        logs = [entry async for entry in ctx.guild.audit_logs(limit=10, user=member)]
        if not logs: return await ctx.send("No recent actions found.")
        await ctx.send(f"```\n" + "\n".join([f"- {e.action} on {e.target}" for e in logs]) + "\n```")

    @commands.hybrid_command(name="antiraid", description="Toggles anti-raid mode.")
    @commands.has_permissions(administrator=True)
    async def antiraid(self, ctx, status: bool):
        db["config"]["antiraid"] = status; save_db(db)
        await ctx.send(f"🛡️ Anti-raid is now **{'ON' if status else 'OFF'}**.")

    @commands.hybrid_command(name="hidechannel", description="Makes channel invisible.")
    @commands.has_permissions(manage_channels=True)
    async def hidechannel(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.send("👻 Channel hidden.")

    @commands.hybrid_command(name="purge", description="Deletes multiple messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        await ctx.channel.purge(limit=amount + 1); await ctx.send(f"🧹 Swept {amount} messages.", delete_after=3)

    @commands.hybrid_command(name="nuke", description="Clones and deletes channel.")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx):
        pos = ctx.channel.position
        new_ch = await ctx.channel.clone()
        await ctx.channel.delete()
        await new_ch.edit(position=pos)
        await new_ch.send("☢️ **TACTICAL NUKE INCOMING!** 💥")

    @commands.hybrid_command(name="kick", description="Kicks a user.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="Caught lacking"):
        await member.kick(reason=reason); await ctx.send(f"👢 {member.name} kicked.")

    @commands.hybrid_command(name="ban", description="Bans a user.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="Crossed the line"):
        await member.ban(reason=reason); await ctx.send(f"🔨 {member.name} banished.")

    @commands.hybrid_command(name="unban", description="Unbans a user.")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: str):
        user = await self.bot.fetch_user(int(user_id))
        await ctx.guild.unban(user); await ctx.send(f"🕊️ {user.mention} revived.")

    @commands.hybrid_command(name="warn", description="Warns a user.")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason="Bad vibes"):
        uid = str(member.id)
        if uid not in db["warns"]: db["warns"][uid] = []
        db["warns"][uid].append(reason); save_db(db)
        await ctx.send(f"⚠️ {member.mention} warned.")

    @commands.hybrid_command(name="warnings", description="Shows user's warnings.")
    async def warnings(self, ctx, member: discord.Member):
        warns = db["warns"].get(str(member.id), [])
        if not warns: return await ctx.send("✅ Clean record.")
        await ctx.send(f"⚠️ **Warnings:**\n" + "\n".join([f"- {w}" for w in warns]))

    @commands.hybrid_command(name="clearwarns", description="Clears all warnings.")
    @commands.has_permissions(administrator=True)
    async def clearwarns(self, ctx, member: discord.Member):
        db["warns"].pop(str(member.id), None); save_db(db); await ctx.send(f"🗑️ Cleared warnings.")

    @commands.hybrid_command(name="lock", description="Locks current channel.")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False); await ctx.send("🔒 Channel locked.")

    @commands.hybrid_command(name="unlock", description="Unlocks current channel.")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True); await ctx.send("🔓 Channel unlocked.")

    @commands.hybrid_command(name="jail", description="Strips roles and locks user.")
    @commands.has_permissions(administrator=True)
    async def jail(self, ctx, member: discord.Member):
        db["jailed"][str(member.id)] = [r.id for r in member.roles if r.id != ctx.guild.default_role.id]
        save_db(db)
        for r in member.roles[1:]:
            try: await member.remove_roles(r)
            except: pass
        jr = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jr: await member.add_roles(jr)
        await ctx.send(f"⛓️ {member.mention} locked up in federal prison.")

    @commands.hybrid_command(name="unjail", description="Releases user from jail.")
    @commands.has_permissions(administrator=True)
    async def unjail(self, ctx, member: discord.Member):
        jr = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jr in member.roles: await member.remove_roles(jr)
        for r_id in db["jailed"].pop(str(member.id), []):
            role = ctx.guild.get_role(r_id)
            if role: await member.add_roles(role)
        save_db(db)
        await ctx.send(f"🔓 {member.mention} made bail.")

    # ==========================================
    # ⭐ LEVELING & REPUTATION & UTILITY
    # ==========================================
    @commands.hybrid_command(name="rank", description="Check XP Level.")
    async def rank(self, ctx, member: discord.Member = None):
        uid = str((member or ctx.author).id)
        lvl = db["levels"].get(uid, {"xp": 0, "level": 1})
        await ctx.send(f"⭐ **{(member or ctx.author).name}** is Level **{lvl['level']}** ({lvl['xp']} XP).")

    @commands.hybrid_command(name="leaderboard_levels", description="Top 10 levels.")
    async def leaderboard_levels(self, ctx):
        sorted_lvls = sorted(db["levels"].items(), key=lambda x: x[1]["level"], reverse=True)[:10]
        res = "**Top 10 Highest Levels:**\n"
        for i, (uid, data) in enumerate(sorted_lvls): res += f"{i+1}. <@{uid}> - Lvl {data['level']}\n"
        await ctx.send(res)

    @commands.hybrid_command(name="givexp", description="Admin give XP.")
    @commands.has_permissions(administrator=True)
    async def givexp(self, ctx, member: discord.Member, amount: int):
        uid = str(member.id)
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["xp"] += amount; save_db(db)
        await ctx.send(f"📈 Gave {amount} XP to {member.name}.")

    @commands.hybrid_command(name="removexp", description="Admin remove XP.")
    @commands.has_permissions(administrator=True)
    async def removexp(self, ctx, member: discord.Member, amount: int):
        uid = str(member.id)
        if uid in db["levels"]: db["levels"][uid]["xp"] = max(0, db["levels"][uid]["xp"] - amount); save_db(db)
        await ctx.send(f"📉 Removed {amount} XP from {member.name}.")

    @commands.hybrid_command(name="setlevel", description="Admin set level.")
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, member: discord.Member, level: int):
        uid = str(member.id)
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["level"] = level; save_db(db)
        await ctx.send(f"⭐ Set {member.name} to Level {level}.")

    @commands.hybrid_command(name="rewards", description="View level rewards.")
    async def rewards(self, ctx): await ctx.send("🎁 **Level Rewards:**\nLevel 10 - Trusted\nLevel 50 - Ronin\nLevel 100 - God")

    @commands.hybrid_command(name="rep", description="Give reputation.")
    async def rep(self, ctx, member: discord.Member):
        if member.id == ctx.author.id: return await ctx.send("Can't rep yourself.")
        uid = str(member.id)
        db["rep"][uid] = db["rep"].get(uid, 0) + 1; save_db(db)
        await ctx.send(f"👍 Gave +1 Rep to {member.name}. Total: {db['rep'][uid]}")

    @commands.hybrid_command(name="leaderboard_rep", description="Top 10 rep.")
    async def leaderboard_rep(self, ctx):
        sorted_rep = sorted(db.get("rep", {}).items(), key=lambda x: x[1], reverse=True)[:10]
        res = "**Top 10 Most Reputable:**\n"
        for i, (uid, amt) in enumerate(sorted_rep): res += f"{i+1}. <@{uid}> - {amt} Rep\n"
        await ctx.send(res)

    @commands.hybrid_command(name="poll", description="Create a poll.")
    async def poll(self, ctx, question: str):
        embed = discord.Embed(title="📊 Poll", description=question, color=discord.Color.green())
        msg = await ctx.send(embed=embed); await msg.add_reaction("👍"); await msg.add_reaction("👎")

    @commands.hybrid_command(name="giveaway_start", description="Start giveaway.")
    async def giveaway_start(self, ctx, prize: str):
        msg = await ctx.send(f"🎉 **GIVEAWAY: {prize}** 🎉\nReact with 🎉 to enter!")
        await msg.add_reaction("🎉")

    @commands.hybrid_command(name="giveaway_reroll", description="Reroll giveaway.")
    async def giveaway_reroll(self, ctx): await ctx.send("🎉 Giveaway rerolled! Winner: @someone")

    @commands.hybrid_command(name="ticket_setup", description="Setup tickets.")
    async def ticket_setup(self, ctx): await ctx.send("🎫 Support tickets enabled. (Placeholder UI)")

    @commands.hybrid_command(name="ticket_close", description="Close ticket.")
    async def ticket_close(self, ctx): await ctx.channel.delete()

    @commands.hybrid_command(name="remindme", description="Set reminder.")
    async def remindme(self, ctx, seconds: int, *, message: str):
        await ctx.send(f"⏰ Reminder set for {seconds}s.")
        await asyncio.sleep(seconds); await ctx.author.send(f"⏰ Reminder: {message}")

    @commands.hybrid_command(name="afk", description="Set AFK status.")
    async def afk(self, ctx, *, reason: str="AFK"):
        db["afk"][str(ctx.author.id)] = reason; save_db(db); await ctx.send(f"💤 {ctx.author.mention} is now AFK: {reason}")

    @commands.hybrid_command(name="weather", description="Check weather.")
    async def weather(self, ctx, city: str): await ctx.send(f"🌤️ The weather in {city} is sunny, 75°F (Simulated).")

    @commands.hybrid_command(name="calc", description="Calculate math.")
    async def calc(self, ctx, expression: str):
        try: await ctx.send(f"🧮 Result: `{eval(expression, {'__builtins__': None}, {})}`")
        except: await ctx.send("❌ Invalid math expression.")

    @commands.hybrid_command(name="translate", description="Translate text.")
    async def translate(self, ctx, lang: str, *, text: str): await ctx.send(f"🌐 Translated to {lang}: {text} (API simulated).")

    @commands.hybrid_command(name="define", description="Dictionary definition.")
    async def define(self, ctx, word: str): await ctx.send(f"📖 Definition of {word}: A very cool word. (API simulated).")

    @commands.hybrid_command(name="urban", description="Urban Dictionary.")
    async def urban(self, ctx, word: str): await ctx.send(f"🏙️ Urban definition for {word}: Slang term. (API simulated).")

    @commands.hybrid_command(name="userhistory", description="Check user history.")
    async def userhistory(self, ctx, member: discord.Member): await ctx.send(f"📜 {member.name} joined on {member.joined_at.strftime('%Y-%m-%d')}.")

    @commands.hybrid_command(name="roleinfo", description="Check role info.")
    async def roleinfo(self, ctx, role: discord.Role): await ctx.send(f"🛡️ Role {role.name} has {len(role.members)} members.")

    @commands.hybrid_command(name="servericon", description="Get server icon.")
    async def servericon(self, ctx): await ctx.send(ctx.guild.icon.url if ctx.guild.icon else "No icon.")

    @commands.hybrid_command(name="ping", description="Bot latency.")
    async def ping(self, ctx): await ctx.send(f"🏓 Pong! {round(self.bot.latency * 1000)}ms")

    @commands.hybrid_command(name="avatar", description="Get user PFP.")
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"{member.name}'s Avatar", color=discord.Color.blue())
        embed.set_image(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="View server stats.")
    async def serverinfo(self, ctx):
        embed = discord.Embed(title=f"Server Info - {ctx.guild.name}", color=discord.Color.gold())
        embed.add_field(name="👑 Owner", value=ctx.guild.owner.mention)
        embed.add_field(name="👥 Members", value=ctx.guild.member_count)
        await ctx.send(embed=embed)

    # ==========================================
    # 🎭 ANIME & ACTION ROLEPLAY
    # ==========================================
    @commands.hybrid_command(name="pat", description="Headpat.")
    async def pat(self, ctx, member: discord.Member): await ctx.send(f"🤚 {ctx.author.name} patted {member.name}!")
    
    @commands.hybrid_command(name="punch", description="Punch.")
    async def punch(self, ctx, member: discord.Member): await ctx.send(f"👊 {ctx.author.name} punched {member.name}!")

    @commands.hybrid_command(name="bite", description="Bite.")
    async def bite(self, ctx, member: discord.Member): await ctx.send(f"🧛 {ctx.author.name} bit {member.name}!")

    @commands.hybrid_command(name="kiss", description="Kiss.")
    async def kiss(self, ctx, member: discord.Member): await ctx.send(f"💋 {ctx.author.name} kissed {member.name}!")

    @commands.hybrid_command(name="smug", description="Smug face.")
    async def smug(self, ctx): await ctx.send(f"😏 {ctx.author.name} looks extremely smug.")

    @commands.hybrid_command(name="cry", description="Crying.")
    async def cry(self, ctx): await ctx.send(f"😭 {ctx.author.name} is crying.")

    @commands.hybrid_command(name="quote", description="Anime Quote.")
    async def quote(self, ctx):
        quotes = ["If you don't fight, you can't win.", "Since when were you under the impression that I wasn't using Kyoka Suigetsu?"]
        await ctx.send(f"📜 *\"{random.choice(quotes)}\"*")

    @commands.hybrid_command(name="powerlevel", description="Scan power level.")
    async def powerlevel(self, ctx, member: discord.Member = None):
        pwr = random.randint(10, 1000000)
        if pwr > 900000: await ctx.send(f"💥 {(member or ctx.author).mention}'s power level is **{pwr:,}**! Wang Lin aura!")
        else: await ctx.send(f"🔍 {(member or ctx.author).mention}'s power level is **{pwr:,}**. Fodder.")

    @commands.hybrid_command(name="domain_expansion", description="Domain Expansion!")
    async def domain_expansion(self, ctx): await ctx.send(f"🤞 **Domain Expansion:** {ctx.author.mention} trapped the chat in their domain!")

    @commands.hybrid_command(name="bankai", description="Bankai!")
    async def bankai(self, ctx): await ctx.send(f"⚔️ **BANKAI!** {ctx.author.mention}'s spiritual pressure is crushing the server!")
    # ==========================================
    # 💰 ECONOMY & RPG (The Grind)
    # ==========================================
    @commands.hybrid_command(name="bal", description="Check balance.")
    async def bal(self, ctx, member: discord.Member = None):
        uid = str((member or ctx.author).id)
        await ctx.send(f"💰 {(member or ctx.author).name} has **{db['economy'].get(uid, 0)}** coins.")

    @commands.hybrid_command(name="daily", description="Claim daily coins.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx):
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + 1000; save_db(db)
        await ctx.send("🎁 Claimed **1000 daily coins**!")

    @commands.hybrid_command(name="weekly", description="Claim weekly coins.")
    @commands.cooldown(1, 604800, commands.BucketType.user)
    async def weekly(self, ctx):
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + 10000; save_db(db)
        await ctx.send("💎 Claimed massive **10,000 weekly coins**!")

    @commands.hybrid_command(name="rob", description="Steal from another user.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def rob(self, ctx, member: discord.Member):
        uid, tid = str(ctx.author.id), str(member.id)
        if db["economy"].get(tid, 0) < 500: return await ctx.send("❌ Too poor to rob.")
        if random.choice([True, False]):
            stolen = random.randint(100, int(db["economy"][tid] * 0.3))
            db["economy"][tid] -= stolen
            db["economy"][uid] = db["economy"].get(uid, 0) + stolen
            await ctx.send(f"🔫 Mugged {member.name} for **{stolen} coins**!")
        else:
            db["economy"][uid] = max(0, db["economy"].get(uid, 0) - 300)
            await ctx.send("🛡️ They fought back! You paid a 300 coin hospital bill.")
        save_db(db)

    @commands.hybrid_command(name="heist", description="Start a bank heist.")
    @commands.cooldown(1, 14400, commands.BucketType.guild)
    async def heist(self, ctx):
        await ctx.send("🏦 **A BANK HEIST HAS STARTED!** (This feature is a placeholder event, you stole 5000 coins!)")
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + 5000; save_db(db)

    @commands.hybrid_command(name="slots", description="Virtual slot machine.")
    async def slots(self, ctx, bet: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: return await ctx.send("❌ Not enough coins.")
        db["economy"][uid] -= bet
        reels = ["🍒", "🍋", "💎"]
        r1, r2, r3 = random.choice(reels), random.choice(reels), random.choice(reels)
        msg = f"🎰 | {r1} | {r2} | {r3} | 🎰\n"
        if r1 == r2 == r3:
            db["economy"][uid] += bet * 10; await ctx.send(msg + f"JACKPOT! Won **{bet*10} coins**!")
        elif r1 == r2 or r2 == r3 or r1 == r3:
            db["economy"][uid] += int(bet * 1.5); await ctx.send(msg + f"Small win! Got **{int(bet*1.5)} coins**.")
        else: await ctx.send(msg + "You lost.")
        save_db(db)

    @commands.hybrid_command(name="blackjack", description="Play 21 against the bot.")
    async def blackjack(self, ctx, bet: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: return await ctx.send("❌ Not enough coins.")
        db["economy"][uid] -= bet
        player = random.randint(15, 25); bot_score = random.randint(17, 23)
        if player > 21: await ctx.send(f"🃏 You busted with {player}. Bot had {bot_score}.")
        elif player > bot_score or bot_score > 21: 
            db["economy"][uid] += bet * 2; await ctx.send(f"🃏 You won with {player}! Bot had {bot_score}.")
        else: await ctx.send(f"🃏 Bot won with {bot_score}. You had {player}.")
        save_db(db)

    @commands.hybrid_command(name="coinflip", description="Gamble 50/50.")
    async def coinflip(self, ctx, bet: int, choice: str):
        if choice.lower() not in ["heads", "tails"]: return await ctx.send("Pick heads or tails.")
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: return await ctx.send("❌ Not enough coins.")
        db["economy"][uid] -= bet
        res = random.choice(["heads", "tails"])
        if choice.lower() == res:
            db["economy"][uid] += bet * 2; await ctx.send(f"🪙 {res.capitalize()}! Won **{bet*2} coins**!")
        else: await ctx.send(f"🪙 {res.capitalize()}. You lost.")
        save_db(db)

    @commands.hybrid_command(name="shop", description="View store.")
    async def shop(self, ctx):
        await ctx.send("🛒 **SHOP:**\n1. Sword - 500 Coins\n2. Shield - 1000 Coins\n*(Use /buy <item>)*")

    @commands.hybrid_command(name="buy", description="Buy an item.")
    async def buy(self, ctx, item: str):
        uid = str(ctx.author.id)
        prices = {"sword": 500, "shield": 1000}
        item = item.lower()
        if item not in prices: return await ctx.send("Item not found.")
        if db["economy"].get(uid, 0) < prices[item]: return await ctx.send("Not enough coins.")
        db["economy"][uid] -= prices[item]
        if uid not in db["inventory"]: db["inventory"][uid] = []
        db["inventory"][uid].append(item); save_db(db)
        await ctx.send(f"✅ Bought {item.capitalize()}!")

    @commands.hybrid_command(name="inventory", description="Check items.")
    async def inventory(self, ctx):
        uid = str(ctx.author.id)
        items = db.get("inventory", {}).get(uid, [])
        await ctx.send(f"🎒 **Inventory:** {', '.join(items) if items else 'Empty'}")

    @commands.hybrid_command(name="give", description="Give coins.")
    async def give(self, ctx, member: discord.Member, amount: int):
        uid, tid = str(ctx.author.id), str(member.id)
        if db["economy"].get(uid, 0) < amount or amount <= 0: return await ctx.send("❌ Insufficient funds.")
        db["economy"][uid] -= amount; db["economy"][tid] = db["economy"].get(tid, 0) + amount; save_db(db)
        await ctx.send(f"💸 Gave {member.name} **{amount} coins**.")

    @commands.hybrid_command(name="rich", description="Top 10 richest.")
    async def rich(self, ctx):
        sorted_eco = sorted(db["economy"].items(), key=lambda x: x[1], reverse=True)[:10]
        res = "**Top 10 Richest Players:**\n"
        for i, (uid, amt) in enumerate(sorted_eco):
            user = self.bot.get_user(int(uid))
            name = user.name if user else f"Unknown ({uid})"
            res += f"{i+1}. {name} - **{amt}** coins\n"
        await ctx.send(res)

    @commands.hybrid_command(name="fish", description="Catch fish.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def fish(self, ctx):
        fish = random.choice(["Boot", "Common Carp", "Rare Salmon", "Legendary Shark"])
        reward = {"Boot": 0, "Common Carp": 50, "Rare Salmon": 200, "Legendary Shark": 1000}[fish]
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward; save_db(db)
        await ctx.send(f"🎣 Caught a **{fish}** worth **{reward} coins**!")

    @commands.hybrid_command(name="hunt", description="Hunt animals.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def hunt(self, ctx):
        mob = random.choice(["Rat", "Goblin", "Dragon"])
        reward = {"Rat": 10, "Goblin": 100, "Dragon": 1000}[mob]
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward; save_db(db)
        await ctx.send(f"🏹 Hunted a **{mob}** for **{reward} coins**!")

    @commands.hybrid_command(name="mine", description="Mine ores.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def mine(self, ctx):
        ore = random.choice(["Stone", "Iron", "Diamond"])
        reward = {"Stone": 5, "Iron": 50, "Diamond": 800}[ore]
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward; save_db(db)
        await ctx.send(f"⛏️ Mined **{ore}** for **{reward} coins**!")

    @commands.hybrid_command(name="quest", description="RPG quest.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def quest(self, ctx):
        uid = str(ctx.author.id)
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        if db["levels"][uid]["level"] >= 13000: return await ctx.send("🛑 Max Level 13,000 Reached!")
        db["levels"][uid]["xp"] += 500; save_db(db)
        await ctx.send(f"🗡️ Quest completed! Earned **500 XP**! (Level {db['levels'][uid]['level']})")

    @commands.hybrid_command(name="trade", description="Trade items.")
    async def trade(self, ctx, member: discord.Member, item: str):
        uid, tid = str(ctx.author.id), str(member.id)
        if item not in db.get("inventory", {}).get(uid, []): return await ctx.send("You don't own this item.")
        if tid not in db["inventory"]: db["inventory"][tid] = []
        db["inventory"][uid].remove(item); db["inventory"][tid].append(item); save_db(db)
        await ctx.send(f"🤝 Traded {item} to {member.name}.")

    @commands.hybrid_command(name="bounty", description="Put bounty on user.")
    async def bounty(self, ctx, member: discord.Member, amount: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < amount or amount <= 0: return await ctx.send("Not enough coins.")
        db["economy"][uid] -= amount
        db["bounties"][str(member.id)] = db["bounties"].get(str(member.id), 0) + amount; save_db(db)
        await ctx.send(f"💀 Placed a {amount} coin bounty on {member.name}!")

    @commands.hybrid_command(name="claimbounty", description="Claim a bounty.")
    async def claimbounty(self, ctx, member: discord.Member):
        uid, tid = str(ctx.author.id), str(member.id)
        bounty = db["bounties"].get(tid, 0)
        if bounty <= 0: return await ctx.send("No bounty exists.")
        db["bounties"][tid] = 0; db["economy"][uid] = db["economy"].get(uid, 0) + bounty; save_db(db)
        await ctx.send(f"🔪 You claimed the **{bounty} coin** bounty on {member.name}!")

    # ==========================================
    # 🤡 FUN & TROLLING
    # ==========================================
    @commands.hybrid_command(name="fakeban", description="Troll ban message.")
    async def fakeban(self, ctx, member: discord.Member):
        await ctx.send(f"🔨 **{member.name}** has been permanently banned from the server.\n*Reason: Caught lacking.*")

    @commands.hybrid_command(name="rickroll", description="Disguised DM.")
    async def rickroll(self, ctx, member: discord.Member):
        try: await member.send("You have been gifted Discord Nitro! Claim here: [https://www.youtube.com/watch?v=dQw4w9WgXcQ](https://www.youtube.com/watch?v=dQw4w9WgXcQ)"); await ctx.send(f"Sent a package to {member.name}.")
        except: await ctx.send("DMs are closed.")

    @commands.hybrid_command(name="howgay", description="Gay rater.")
    async def howgay(self, ctx, member: discord.Member=None):
        await ctx.send(f"🏳️‍🌈 {(member or ctx.author).name} is **{random.randint(0,100)}%** gay.")

    @commands.hybrid_command(name="simpmeter", description="Simp rater.")
    async def simpmeter(self, ctx, member: discord.Member=None):
        await ctx.send(f"😳 {(member or ctx.author).name} is a **{random.randint(0,100)}%** simp.")

    @commands.hybrid_command(name="susmeter", description="Sus rater.")
    async def susmeter(self, ctx, member: discord.Member=None):
        await ctx.send(f"📮 {(member or ctx.author).name} is **{random.randint(0,100)}%** sus.")

    @commands.hybrid_command(name="roast", description="Roast a user.")
    async def roast(self, ctx, member: discord.Member):
        roasts = ["You're the reason the gene pool needs a lifeguard.", "You bring everyone so much joy when you leave the room."]
        await ctx.send(f"{member.mention} {random.choice(roasts)}")

    @commands.hybrid_command(name="compliment", description="Compliment a user.")
    async def compliment(self, ctx, member: discord.Member):
        comps = ["You have a great sense of humor!", "You light up the room!"]
        await ctx.send(f"💖 {member.mention} {random.choice(comps)}")

    @commands.hybrid_command(name="confess", description="Anonymous confession.")
    async def confess(self, ctx, *, message: str):
        await ctx.message.delete()
        embed = discord.Embed(title="Anonymous Confession", description=message, color=discord.Color.dark_theme())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="kill", description="Funny death message.")
    async def kill(self, ctx, member: discord.Member):
        deaths = ["fell out of the world.", "was obliterated by a rogue AI.", "forgot how to breathe."]
        await ctx.send(f"☠️ {member.name} {random.choice(deaths)}")

    @commands.hybrid_command(name="revive", description="Revive user.")
    async def revive(self, ctx, member: discord.Member):
        await ctx.send(f"👼 {member.name} has been resurrected!")

    @commands.hybrid_command(name="meme", description="Random meme (simulated).")
    async def meme(self, ctx):
        await ctx.send("😂 *Imagine a really funny meme right here.* (API placeholder)")

    @commands.hybrid_command(name="dadjoke", description="Tells a dad joke.")
    async def dadjoke(self, ctx):
        jokes = ["I'm afraid for the calendar. Its days are numbered.", "Why do fathers take an extra pair of socks when they go golfing? In case they get a hole in one!"]
        await ctx.send(f"🧔 {random.choice(jokes)}")

    @commands.hybrid_command(name="choose", description="Bot makes a choice.")
    async def choose(self, ctx, option1: str, option2: str):
        await ctx.send(f"🤔 I choose... **{random.choice([option1, option2])}**")

    @commands.hybrid_command(name="spank", description="Spank someone.")
    async def spank(self, ctx, member: discord.Member):
        await ctx.send(f"🤚 {ctx.author.mention} viciously spanked {member.mention}!")

    @commands.hybrid_command(name="jailbreak", description="Attempt jailbreak.")
    async def jailbreak(self, ctx, member: discord.Member):
        if random.randint(1, 10) == 1:
            jr = discord.utils.get(ctx.guild.roles, name="Jailed")
            if jr in member.roles: await member.remove_roles(jr); await ctx.send(f"🔓 SUCCESS! Broke {member.name} out!")
        else: await ctx.send("❌ Jailbreak failed. The guards caught you.")

    @commands.hybrid_command(name="eightball", description="Ask a question.")
    async def eightball(self, ctx, *, question: str):
        res = random.choice(["Yes.", "No.", "Maybe.", "Definitely not.", "Without a doubt."])
        await ctx.send(f"🎱 **Q:** {question}\n**A:** {res}")

    @commands.hybrid_command(name="hack", description="Fake hack someone.")
    async def hack(self, ctx, member: discord.Member):
        msg = await ctx.send(f"💻 Hacking {member.name}...")
        await asyncio.sleep(2)
        await msg.edit(content=f"✅ Successfully hacked {member.mention}. Selling history for 5 robux.")

    @commands.hybrid_command(name="ship", description="Matchmake two people.")
    async def ship(self, ctx, m1: discord.Member, m2: discord.Member=None):
        m2 = m2 or ctx.author
        await ctx.send(f"❤️ **Ship:** {m1.name} x {m2.name}\n**Rating:** {random.randint(0,100)}%")

    # ==========================================
    # 🎵 VOICE & MEDIA (Basic Placeholders)
    # ==========================================
    @commands.hybrid_command(name="join", description="Joins your Voice Channel.")
    async def join(self, ctx):
        if not ctx.author.voice: return await ctx.send("❌ You are not in a voice channel.")
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"🔊 Joined {channel.name}.")

    @commands.hybrid_command(name="leave", description="Leaves the Voice Channel.")
    async def leave(self, ctx):
        if ctx.voice_client: await ctx.voice_client.disconnect(); await ctx.send("👋 Disconnected from VC.")
        else: await ctx.send("I am not in a voice channel.")

    @commands.hybrid_command(name="play", description="Plays music.")
    async def play(self, ctx, song: str): await ctx.send(f"🎶 Searching and queuing '{song}'... (Requires FFmpeg)")

    @commands.hybrid_command(name="skip", description="Skips song.")
    async def skip(self, ctx): await ctx.send("⏭️ Skipped current track.")

    @commands.hybrid_command(name="queue", description="Shows queue.")
    async def queue(self, ctx): await ctx.send("📜 Music Queue is currently empty.")

    @commands.hybrid_command(name="stop", description="Stops music.")
    async def stop(self, ctx): await ctx.send("🛑 Stopped music and cleared queue.")

    @commands.hybrid_command(name="volume", description="Changes volume.")
    async def volume(self, ctx, vol: int): await ctx.send(f"🔊 Volume set to {vol}%.")

    @commands.hybrid_command(name="earrape", description="Troll volume.")
    async def earrape(self, ctx): await ctx.send("💥 Volume set to 500%. WARNING.")

    @commands.hybrid_command(name="soundboard", description="Play sound bite.")
    async def soundboard(self, ctx, sound: str): await ctx.send(f"🔊 Playing '{sound}' sound effect in VC.")

    @commands.hybrid_command(name="tts", description="Text to speech.")
    async def tts(self, ctx, *, message: str): await ctx.send(f"🗣️ TTS Reading: {message}")

# ==========================================
# FINAL SETUP SINK
# ==========================================
async def setup(bot):
    await bot.add_cog(MasterCommands(bot))
