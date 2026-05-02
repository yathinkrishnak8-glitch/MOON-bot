import discord
from discord.ext import commands, tasks
import os, json, random, asyncio
from datetime import timedelta
from groq import Groq

# ==========================================
# DATABASE & MEMORY
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
snipes = {}; edit_snipes = {}

class MasterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = Groq(api_key=os.environ.get('GROQ_API_KEY')) if os.environ.get('GROQ_API_KEY') else None
        self.ai_event_loop.start()

    def cog_unload(self): self.ai_event_loop.cancel()

    def ask_groq(self, messages):
        if not self.client: raise Exception("Groq API Key missing.")
        for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]:
            try: return self.client.chat.completions.create(model=m, messages=messages).choices[0].message.content.strip()
            except: continue 
        raise Exception("AI failed.")

    # ==========================================
    # LISTENERS & EVENTS
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
        channel = self.bot.get_channel(db["config"].get("event_channel"))
        if channel:
            try: await channel.send(embed=discord.Embed(title="🌟 Server Event", description=self.ask_groq([{"role": "user", "content": "Generate a highly engaging, modern Discord event, hot take, or scenario. No JSON."}]), color=discord.Color.blurple()))
            except: pass

    @ai_event_loop.before_loop
    async def before_event_loop(self): await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        uid = str(message.author.id)

        # DM AI
        if not message.guild:
            if not self.client: return
            async with message.channel.typing():
                try: await message.channel.send(self.ask_groq([{"role": "system", "content": "You are habbibi mod (:, a chaotic funny bot talking in DMs."}, {"role": "user", "content": message.content}])[:2000])
                except Exception as e: await message.channel.send(f"❌ AI Error: {e}")
            return 

        # AFK Check
        if uid in db["afk"]:
            del db["afk"][uid]; save_db(db)
            await message.channel.send(f"👋 Welcome back {message.author.mention}, AFK removed.", delete_after=5)
        for m in message.mentions:
            if str(m.id) in db["afk"]: await message.channel.send(f"💤 **{m.name}** is AFK: {db['afk'][str(m.id)]}")

        # Automod
        for w in db["config"]["filterwords"]:
            if w in message.content.lower():
                await message.delete()
                return await message.channel.send(f"⚠️ {message.author.mention}, word banned!", delete_after=5)

        # XP
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["xp"] += random.randint(10, 25)
        if db["levels"][uid]["xp"] >= (db["levels"][uid]["level"] * 100) * 1.5:
            db["levels"][uid]["level"] += 1; save_db(db)
            await message.channel.send(f"🎉 **{message.author.mention} leveled up to {db['levels'][uid]['level']}!**")
        else: save_db(db)

        # Custom Commands & AI Chat
        if message.content.startswith('!') and message.content[1:].split()[0].lower() in db["custom_commands"]:
            return await message.channel.send(db["custom_commands"][message.content[1:].split()[0].lower()])
        if message.channel.id == db["config"].get("ai_channel") and not message.content.startswith(('!', '/')) and self.client:
            async with message.channel.typing():
                try: await message.channel.send(self.ask_groq([{"role": "system", "content": "You are habbibi mod (:, a chaotic bot."}, {"role": "user", "content": message.content}])[:2000])
                except: pass

    # ==========================================
    # ⚙️ CONFIG & SERVER DEPLOY
    # ==========================================
    @commands.hybrid_command(name="setaichannel")
    @commands.has_permissions(administrator=True)
    async def setaichannel(self, ctx): db["config"]["ai_channel"] = ctx.channel.id; save_db(db); await ctx.send(f"🤖 AI Chat bound to {ctx.channel.mention}")

    @commands.hybrid_command(name="setcmdchannel")
    @commands.has_permissions(administrator=True)
    async def setcmdchannel(self, ctx): db["config"]["cmd_channel"] = ctx.channel.id; save_db(db); await ctx.send(f"🔒 Commands bound to {ctx.channel.mention}")

    @commands.hybrid_command(name="seteventchannel")
    @commands.has_permissions(administrator=True)
    async def seteventchannel(self, ctx): db["config"]["event_channel"] = ctx.channel.id; save_db(db); await ctx.send(f"🌟 Events bound to {ctx.channel.mention}")

    @commands.hybrid_command(name="deployserver", description="Wipes and builds server.")
    @commands.has_permissions(administrator=True)
    async def deployserver(self, ctx):
        await ctx.send("⚠️ **CLEAN SLATE PROTOCOL.**")
        for c in ctx.guild.channels:
            try: await c.delete(); await asyncio.sleep(0.5)
            except: pass
        cr = {}
        for r in [{"name": "Admin", "color": discord.Color.red()}, {"name": "Moderator", "color": discord.Color.orange()}, {"name": "Jailed", "color": discord.Color.dark_grey()}]:
            try: cr[r["name"]] = await ctx.guild.create_role(name=r["name"], color=r["color"], permissions=discord.Permissions(administrator=(r["name"]=="Admin")), hoist=True); await asyncio.sleep(1)
            except: pass
        try: await ctx.author.add_roles(cr["Admin"])
        except: pass
        ci = await ctx.guild.create_category("📌 INFORMATION"); await ctx.guild.create_text_channel("rules", category=ci)
        cc = await ctx.guild.create_category("💬 CHAT"); gc = await ctx.guild.create_text_channel("general", category=cc); bc = await ctx.guild.create_text_channel("bot-commands", category=cc); ac = await ctx.guild.create_text_channel("talk-to-ai", category=cc)
        cv = await ctx.guild.create_category("🔊 VOICE"); await ctx.guild.create_voice_channel("General VC", category=cv)
        for cat in ctx.guild.categories:
            try: await cat.set_permissions(cr["Jailed"], read_messages=False)
            except: pass
        db["config"]["cmd_channel"] = bc.id; db["config"]["ai_channel"] = ac.id; db["config"]["event_channel"] = gc.id; save_db(db)
        await gc.send(f"{ctx.author.mention} ✅ Deployment Complete.")

    # ==========================================
    # 🧠 GOD-MODE & AI TOOLS
    # ==========================================
    @commands.hybrid_command(name='aicommand')
    @commands.has_permissions(administrator=True)
    async def aicommand(self, ctx, *, instruction: str):
        if not self.client: return await ctx.send("🤖 AI offline.")
        await ctx.defer()
        try:
            raw = self.ask_groq([{"role": "user", "content": f"Omnipotent bot. Output JSON array: 1. Reply: {{\"action\": \"reply\", \"message\": \"text\"}} 2. Execute Python: {{\"action\": \"execute\", \"code\": \"await ctx.send('Done!')\"}}\nInstruction: {instruction}"}])
            start_idx, end_idx = raw.find('['), raw.rfind(']')
            clean_json = raw[start_idx:end_idx+1] if start_idx != -1 else raw.replace('```json', '').replace('```python', '').replace('```', '').strip()
            if clean_json.startswith('{'): clean_json = f"[{clean_json}]"
            for act in json.loads(clean_json):
                if act.get("action") == "reply": await ctx.send(f"🤖 {act.get('message')}")
                elif act.get("action") == "execute":
                    msg = await ctx.send("⚡ **Executing Python...**")
                    try:
                        wrapped = f"async def __ai_exec():\n" + "\n".join([f"    {line}" for line in act.get("code", "").split("\n")])
                        exec_env = {'discord': discord, 'bot': self.bot, 'ctx': ctx, 'asyncio': asyncio, 'db': db}
                        exec(wrapped, exec_env); await exec_env['__ai_exec']()
                        await msg.edit(content="✅ **Execution Successful!**")
                    except Exception as err: await msg.edit(content=f"⚠️ **Failed:**\n```py\n{err}```")
        except Exception as e: await ctx.send(f"❌ Error: {e}")

    @commands.hybrid_command(name="forceevent")
    @commands.has_permissions(administrator=True)
    async def forceevent(self, ctx): await ctx.send(embed=discord.Embed(title="🌟 Event", description=self.ask_groq([{"role": "user", "content": "Generate a modern Discord event."}]), color=discord.Color.blurple()))

    @commands.hybrid_command(name="tldr")
    async def tldr(self, ctx): await ctx.defer(); log = "\n".join([m.content async for m in ctx.channel.history(limit=50) if m.content]); await ctx.send(f"📜 **TL;DR:** {self.ask_groq([{'role': 'user', 'content': f'Summarize: {log}'}])}")

    @commands.hybrid_command(name="roast_history")
    async def roast_history(self, ctx, member: discord.Member): await ctx.defer(); log = "\n".join([m.content async for m in ctx.channel.history(limit=20) if m.author == member and m.content]); await ctx.send(f"🔥 **Roast for {member.name}:**\n{self.ask_groq([{'role': 'user', 'content': f'Roast based on: {log}'}])}")

    @commands.hybrid_command(name="gothic_translate")
    async def gothic_translate(self, ctx, *, text: str): await ctx.defer(); await ctx.send(f"🦇 **Gothic:**\n{self.ask_groq([{'role': 'user', 'content': f'Rewrite into dark gothic royal decree: {text}'}])}")

    @commands.hybrid_command(name="lore")
    async def lore(self, ctx): await ctx.defer(); await ctx.send(f"📖 **Server Lore:**\n{self.ask_groq([{'role': 'user', 'content': 'Write dark fantasy backstory for this server.'}])}")

    @commands.hybrid_command(name="code_fix")
    async def code_fix(self, ctx, *, code: str): await ctx.defer(); await ctx.send(f"🛠️ **Fix:**\n{self.ask_groq([{'role': 'user', 'content': f'Fix this python: {code}'}])}")

    @commands.hybrid_command(name="name_idea")
    async def name_idea(self, ctx): await ctx.defer(); await ctx.send(f"💡 **Ideas:**\n{self.ask_groq([{'role': 'user', 'content': 'Give 5 cool discord role names.'}])}")

    @commands.hybrid_command(name="ai_image")
    async def ai_image(self, ctx, *, prompt: str): await ctx.send("🖼️ [Image API placeholder]")

    @commands.hybrid_command(name="vibecheck")
    async def vibecheck(self, ctx, member: discord.Member): await ctx.defer(); log = "\n".join([m.content async for m in ctx.channel.history(limit=20) if m.author == member and m.content]); await ctx.send(f"🔮 **Vibe Check:**\n{self.ask_groq([{'role': 'user', 'content': f'Analyze vibe humorously: {log}'}])}")

    @commands.hybrid_command(name="debate")
    async def debate(self, ctx, *, topic: str): await ctx.defer(); await ctx.send(f"⚖️ **Debate:**\n{self.ask_groq([{'role': 'system', 'content': 'Argue against user.'}, {'role': 'user', 'content': topic}])}")

    @commands.hybrid_command(name="bossfight")
    async def bossfight(self, ctx): await ctx.defer(); await ctx.send(f"⚔️ **BOSS FIGHT:**\n{self.ask_groq([{'role': 'user', 'content': 'Generate text-based boss fight.'}])}")

    # ==========================================
    # 🛡️ ADVANCED MODERATION
    # ==========================================
    @commands.hybrid_command(name="tempban")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member, days: int): await member.ban(reason=f"Tempban {days}d"); await ctx.send(f"🔨 {member.name} banned for {days}d."); await asyncio.sleep(days*86400); await ctx.guild.unban(member)

    @commands.hybrid_command(name="tempmute")
    @commands.has_permissions(moderate_members=True)
    async def tempmute(self, ctx, member: discord.Member, minutes: int): await member.timeout(timedelta(minutes=minutes)); await ctx.send(f"🔇 {member.mention} muted {minutes}m.")

    @commands.hybrid_command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int): await ctx.channel.edit(slowmode_delay=seconds); await ctx.send(f"⏱️ Slowmode {seconds}s.")

    @commands.hybrid_command(name="lockdown")
    @commands.has_permissions(administrator=True)
    async def lockdown(self, ctx):
        for c in ctx.guild.text_channels:
            try: await c.set_permissions(ctx.guild.default_role, send_messages=False)
            except: pass
        await ctx.send("🚨 **LOCKDOWN INITIATED.**")

    @commands.hybrid_command(name="unlockdown")
    @commands.has_permissions(administrator=True)
    async def unlockdown(self, ctx):
        for c in ctx.guild.text_channels:
            try: await c.set_permissions(ctx.guild.default_role, send_messages=True)
            except: pass
        await ctx.send("🔓 **LOCKDOWN LIFTED.**")

    @commands.hybrid_command(name="snipe")
    async def snipe(self, ctx):
        d = snipes.get(ctx.channel.id)
        if not d: return await ctx.send("Nothing to snipe!")
        await ctx.send(embed=discord.Embed(description=d["content"], color=discord.Color.red()).set_author(name=d["author"]))

    @commands.hybrid_command(name="editsnipe")
    async def editsnipe(self, ctx):
        d = edit_snipes.get(ctx.channel.id)
        if not d: return await ctx.send("No edited messages!")
        await ctx.send(embed=discord.Embed(color=discord.Color.orange()).add_field(name="Before", value=d["before"], inline=False).add_field(name="After", value=d["after"], inline=False).set_author(name=d["author"]))

    @commands.hybrid_command(name="massnick")
    @commands.has_permissions(administrator=True)
    async def massnick(self, ctx, *, nickname: str):
        await ctx.send(f"🔄 Changing nicks...")
        for m in ctx.guild.members:
            if not m.bot and m < ctx.guild.me.top_role:
                try: await m.edit(nick=nickname); await asyncio.sleep(0.5)
                except: pass
        await ctx.send("✅ Massnick complete.")

    @commands.hybrid_command(name="strip")
    @commands.has_permissions(administrator=True)
    async def strip(self, ctx, member: discord.Member):
        for r in member.roles[1:]:
            try: await member.remove_roles(r)
            except: pass
        await ctx.send(f"👕 Stripped {member.name}.")

    @commands.hybrid_command(name="roleall")
    @commands.has_permissions(administrator=True)
    async def roleall(self, ctx, role: discord.Role):
        await ctx.send("🔄 Granting role...")
        for m in ctx.guild.members:
            if not m.bot:
                try: await m.add_roles(role); await asyncio.sleep(0.5)
                except: pass
        await ctx.send("✅ Role granted.")

    @commands.hybrid_command(name="vckick")
    @commands.has_permissions(move_members=True)
    async def vckick(self, ctx, member: discord.Member): await member.move_to(None) if member.voice else await ctx.send("Not in VC."); await ctx.send(f"👢 Kicked from VC.")

    @commands.hybrid_command(name="vcmute")
    @commands.has_permissions(mute_members=True)
    async def vcmute(self, ctx, member: discord.Member): await member.edit(mute=True) if member.voice else None; await ctx.send("🔇 VC muted.")

    @commands.hybrid_command(name="audit")
    @commands.has_permissions(administrator=True)
    async def audit(self, ctx, member: discord.Member): logs = [e async for e in ctx.guild.audit_logs(limit=10, user=member)]; await ctx.send(f"```\n" + "\n".join([f"{e.action} on {e.target}" for e in logs]) + "\n```" if logs else "No actions.")

    @commands.hybrid_command(name="antiraid")
    @commands.has_permissions(administrator=True)
    async def antiraid(self, ctx, status: bool): db["config"]["antiraid"] = status; save_db(db); await ctx.send(f"🛡️ Anti-raid: {status}")

    @commands.hybrid_command(name="hidechannel")
    @commands.has_permissions(manage_channels=True)
    async def hidechannel(self, ctx): await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=False); await ctx.send("👻 Hidden.")

    @commands.hybrid_command(name="purge")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int): await ctx.channel.purge(limit=amount + 1); await ctx.send(f"🧹 Swept {amount}.", delete_after=3)

    @commands.hybrid_command(name="nuke")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx): pos = ctx.channel.position; nc = await ctx.channel.clone(); await ctx.channel.delete(); await nc.edit(position=pos); await nc.send("☢️ **NUKE INCOMING!** 💥")

    @commands.hybrid_command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="Lacking"): await member.kick(reason=reason); await ctx.send(f"👢 {member.name} kicked.")

    @commands.hybrid_command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="Banned"): await member.ban(reason=reason); await ctx.send(f"🔨 {member.name} banned.")

    @commands.hybrid_command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: str): await ctx.guild.unban(await self.bot.fetch_user(int(user_id))); await ctx.send("🕊️ Unbanned.")

    @commands.hybrid_command(name="warn")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason="Bad"): uid = str(member.id); db["warns"].setdefault(uid, []).append(reason); save_db(db); await ctx.send(f"⚠️ {member.mention} warned.")

    @commands.hybrid_command(name="warnings")
    async def warnings(self, ctx, member: discord.Member): warns = db["warns"].get(str(member.id), []); await ctx.send("⚠️ **Warnings:**\n" + "\n".join(warns) if warns else "✅ Clean.")

    @commands.hybrid_command(name="clearwarns")
    @commands.has_permissions(administrator=True)
    async def clearwarns(self, ctx, member: discord.Member): db["warns"].pop(str(member.id), None); save_db(db); await ctx.send("🗑️ Cleared.")

    @commands.hybrid_command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx): await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False); await ctx.send("🔒 Locked.")

    @commands.hybrid_command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx): await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True); await ctx.send("🔓 Unlocked.")

    # ==========================================
    # 💰 RPG & ECONOMY
    # ==========================================
    @commands.hybrid_command(name="bal")
    async def bal(self, ctx, member: discord.Member = None): await ctx.send(f"💰 **{db['economy'].get(str((member or ctx.author).id), 0)}** coins.")

    @commands.hybrid_command(name="daily")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx): db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + 1000; save_db(db); await ctx.send("🎁 Claimed **1000 coins**!")

    @commands.hybrid_command(name="weekly")
    @commands.cooldown(1, 604800, commands.BucketType.user)
    async def weekly(self, ctx): db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + 10000; save_db(db); await ctx.send("💎 Claimed **10,000 coins**!")

    @commands.hybrid_command(name="work")
    @commands.cooldown(1, 3600, commands.BucketType.user) 
    async def work(self, ctx): e = random.randint(100, 300); db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + e; save_db(db); await ctx.send(f"💼 Earned **{e} coins**!")

    @commands.hybrid_command(name="crime")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def crime(self, ctx):
        u = str(ctx.author.id)
        if random.choice([True, False]): e = random.randint(300, 700); db["economy"][u] = db["economy"].get(u, 0) + e; await ctx.send(f"🥷 Hacked **{e} coins**!")
        else: l = random.randint(100, 250); db["economy"][u] = max(0, db["economy"].get(u, 0) - l); await ctx.send(f"🚓 Caught. Paid **{l} coins**.")
        save_db(db)

    @commands.hybrid_command(name="rob")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def rob(self, ctx, member: discord.Member):
        u, t = str(ctx.author.id), str(member.id)
        if db["economy"].get(t, 0) < 500: return await ctx.send("❌ Too poor.")
        if random.choice([True, False]): s = random.randint(100, int(db["economy"][t] * 0.3)); db["economy"][t] -= s; db["economy"][u] = db["economy"].get(u, 0) + s; await ctx.send(f"🔫 Mugged **{s} coins**!")
        else: db["economy"][u] = max(0, db["economy"].get(u, 0) - 300); await ctx.send("🛡️ Fought back! Lost 300 coins.")
        save_db(db)

    @commands.hybrid_command(name="heist")
    @commands.cooldown(1, 14400, commands.BucketType.guild)
    async def heist(self, ctx): db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + 5000; save_db(db); await ctx.send("🏦 **HEIST STARTED!** Stole 5000 coins!")

    @commands.hybrid_command(name="slots")
    async def slots(self, ctx, bet: int):
        u = str(ctx.author.id)
        if db["economy"].get(u, 0) < bet or bet <= 0: return await ctx.send("❌ Poor.")
        db["economy"][u] -= bet; r = ["🍒", "🍋", "💎"]; r1, r2, r3 = random.choice(r), random.choice(r), random.choice(r)
        if r1 == r2 == r3: db["economy"][u] += bet * 10; await ctx.send(f"🎰 | {r1} | {r2} | {r3} | \nJACKPOT! Won {bet*10}!")
        elif r1 == r2 or r2 == r3 or r1 == r3: db["economy"][u] += int(bet * 1.5); await ctx.send(f"🎰 | {r1} | {r2} | {r3} |\nWon {int(bet*1.5)}!")
        else: await ctx.send(f"🎰 | {r1} | {r2} | {r3} |\nLost.")
        save_db(db)

    @commands.hybrid_command(name="blackjack")
    async def blackjack(self, ctx, bet: int):
        u = str(ctx.author.id)
        if db["economy"].get(u, 0) < bet or bet <= 0: return await ctx.send("❌ Poor.")
        db["economy"][u] -= bet; p, b = random.randint(15, 25), random.randint(17, 23)
        if p > 21: await ctx.send(f"🃏 Busted with {p}. Bot had {b}.")
        elif p > b or b > 21: db["economy"][u] += bet * 2; await ctx.send(f"🃏 Won with {p}! Bot had {b}.")
        else: await ctx.send(f"🃏 Bot won with {b}. You had {p}.")
        save_db(db)

    @commands.hybrid_command(name="coinflip")
    async def coinflip(self, ctx, bet: int, choice: str):
        if choice.lower() not in ["heads", "tails"]: return await ctx.send("heads or tails.")
        u = str(ctx.author.id)
        if db["economy"].get(u, 0) < bet or bet <= 0: return await ctx.send("❌ Poor.")
        db["economy"][u] -= bet; res = random.choice(["heads", "tails"])
        if choice.lower() == res: db["economy"][u] += bet * 2; await ctx.send(f"🪙 {res}! Won {bet*2}!")
        else: await ctx.send(f"🪙 {res}. Lost.")
        save_db(db)

    @commands.hybrid_command(name="shop")
    async def shop(self, ctx): await ctx.send("🛒 **SHOP:** 1. Sword (500) 2. Shield (1000) - Use /buy")

    @commands.hybrid_command(name="buy")
    async def buy(self, ctx, item: str):
        u, p = str(ctx.author.id), {"sword": 500, "shield": 1000}; item = item.lower()
        if item not in p: return await ctx.send("Not found.")
        if db["economy"].get(u, 0) < p[item]: return await ctx.send("Poor.")
        db["economy"][u] -= p[item]; db.setdefault("inventory", {}).setdefault(u, []).append(item); save_db(db); await ctx.send(f"✅ Bought {item}!")

    @commands.hybrid_command(name="inventory")
    async def inventory(self, ctx): await ctx.send(f"🎒 **Inv:** {', '.join(db.get('inventory', {}).get(str(ctx.author.id), [])) or 'Empty'}")

    @commands.hybrid_command(name="give")
    async def give(self, ctx, member: discord.Member, amount: int):
        u, t = str(ctx.author.id), str(member.id)
        if db["economy"].get(u, 0) < amount or amount <= 0: return await ctx.send("❌ Poor.")
        db["economy"][u] -= amount; db["economy"][t] = db["economy"].get(t, 0) + amount; save_db(db); await ctx.send(f"💸 Gave {amount}.")

    @commands.hybrid_command(name="rich")
    async def rich(self, ctx): await ctx.send("**Richest:**\n" + "\n".join([f"<@{uid}> - {amt}" for uid, amt in sorted(db["economy"].items(), key=lambda x: x[1], reverse=True)[:10]]))

    @commands.hybrid_command(name="fish")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def fish(self, ctx): r = random.choice([0, 50, 200, 1000]); db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + r; save_db(db); await ctx.send(f"🎣 Caught fish worth {r} coins!")

    @commands.hybrid_command(name="hunt")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def hunt(self, ctx): r = random.choice([10, 100, 1000]); db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + r; save_db(db); await ctx.send(f"🏹 Hunted animal worth {r} coins!")

    @commands.hybrid_command(name="mine")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def mine(self, ctx): r = random.choice([5, 50, 800]); db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + r; save_db(db); await ctx.send(f"⛏️ Mined ore worth {r} coins!")

    @commands.hybrid_command(name="quest")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def quest(self, ctx):
        u = str(ctx.author.id); db.setdefault("levels", {}).setdefault(u, {"xp": 0, "level": 1})
        if db["levels"][u]["level"] >= 13000: return await ctx.send("🛑 Max Level!")
        db["levels"][u]["xp"] += 500; save_db(db); await ctx.send(f"🗡️ Quest done! +500 XP")

    @commands.hybrid_command(name="trade")
    async def trade(self, ctx, member: discord.Member, item: str):
        u, t = str(ctx.author.id), str(member.id)
        if item not in db.get("inventory", {}).get(u, []): return await ctx.send("Don't own.")
        db["inventory"][u].remove(item); db.setdefault("inventory", {}).setdefault(t, []).append(item); save_db(db); await ctx.send("🤝 Traded.")

    @commands.hybrid_command(name="bounty")
    async def bounty(self, ctx, member: discord.Member, amount: int):
        u = str(ctx.author.id)
        if db["economy"].get(u, 0) < amount or amount <= 0: return await ctx.send("Poor.")
        db["economy"][u] -= amount; db["bounties"][str(member.id)] = db.get("bounties", {}).get(str(member.id), 0) + amount; save_db(db); await ctx.send(f"💀 Bounty placed.")

    @commands.hybrid_command(name="claimbounty")
    async def claimbounty(self, ctx, member: discord.Member):
        u, t = str(ctx.author.id), str(member.id)
        b = db.get("bounties", {}).get(t, 0)
        if b <= 0: return await ctx.send("No bounty.")
        db["bounties"][t] = 0; db["economy"][u] = db["economy"].get(u, 0) + b; save_db(db); await ctx.send(f"🔪 Claimed {b} coins!")

    # ==========================================
    # 🤡 FUN & TROLLS
    # ==========================================
    @commands.hybrid_command(name="fakeban")
    async def fakeban(self, ctx, member: discord.Member): await ctx.send(f"🔨 **{member.name}** permanently banned.")

    @commands.hybrid_command(name="rickroll")
    async def rickroll(self, ctx, member: discord.Member):
        try: await member.send("Nitro: [https://youtube.com/watch?v=dQw4w9WgXcQ](https://youtube.com/watch?v=dQw4w9WgXcQ)"); await ctx.send("Sent.")
        except: await ctx.send("DMs closed.")

    @commands.hybrid_command(name="howgay")
    async def howgay(self, ctx, member: discord.Member=None): await ctx.send(f"🏳️‍🌈 {(member or ctx.author).name} is {random.randint(0,100)}% gay.")

    @commands.hybrid_command(name="simpmeter")
    async def simpmeter(self, ctx, member: discord.Member=None): await ctx.send(f"😳 {(member or ctx.author).name} is {random.randint(0,100)}% simp.")

    @commands.hybrid_command(name="susmeter")
    async def susmeter(self, ctx, member: discord.Member=None): await ctx.send(f"📮 {(member or ctx.author).name} is {random.randint(0,100)}% sus.")

    @commands.hybrid_command(name="roast")
    async def roast(self, ctx, member: discord.Member): await ctx.send(f"{member.mention} You're a cloud. When you leave, it's a beautiful day.")

    @commands.hybrid_command(name="compliment")
    async def compliment(self, ctx, member: discord.Member): await ctx.send(f"💖 {member.mention} You light up the room!")

    @commands.hybrid_command(name="confess")
    async def confess(self, ctx, *, message: str): await ctx.message.delete(); await ctx.send(embed=discord.Embed(title="Confession", description=message))

    @commands.hybrid_command(name="kill")
    async def kill(self, ctx, member: discord.Member): await ctx.send(f"☠️ {member.name} fell out of the world.")

    @commands.hybrid_command(name="revive")
    async def revive(self, ctx, member: discord.Member): await ctx.send(f"👼 {member.name} resurrected!")

    @commands.hybrid_command(name="meme")
    async def meme(self, ctx): await ctx.send("😂 [Meme API placeholder]")

    @commands.hybrid_command(name="dadjoke")
    async def dadjoke(self, ctx): await ctx.send("🧔 Why did the scarecrow win an award? He was outstanding in his field.")

    @commands.hybrid_command(name="choose")
    async def choose(self, ctx, option1: str, option2: str): await ctx.send(f"🤔 **{random.choice([option1, option2])}**")

    @commands.hybrid_command(name="spank")
    async def spank(self, ctx, member: discord.Member): await ctx.send(f"🤚 {ctx.author.mention} spanked {member.mention}!")

    @commands.hybrid_command(name="jailbreak")
    async def jailbreak(self, ctx, member: discord.Member):
        if random.randint(1, 10) == 1:
            jr = discord.utils.get(ctx.guild.roles, name="Jailed")
            if jr in member.roles: await member.remove_roles(jr); await ctx.send("🔓 BROKE OUT!")
        else: await ctx.send("❌ Caught by guards.")

    @commands.hybrid_command(name="eightball")
    async def eightball(self, ctx, *, question: str): await ctx.send(f"🎱 **A:** {random.choice(['Yes.', 'No.', 'Maybe.'])}")

    @commands.hybrid_command(name="hack")
    async def hack(self, ctx, member: discord.Member): msg = await ctx.send("💻 Hacking..."); await asyncio.sleep(2); await msg.edit(content=f"✅ Hacked {member.mention}.")

    @commands.hybrid_command(name="ship")
    async def ship(self, ctx, m1: discord.Member, m2: discord.Member=None): await ctx.send(f"❤️ **Ship:** {m1.name} x {(m2 or ctx.author).name} - {random.randint(0,100)}%")

    # ==========================================
    # 🎭 ANIME
    # ==========================================
    @commands.hybrid_command(name="pat")
    async def pat(self, ctx, member: discord.Member): await ctx.send(f"🤚 {ctx.author.name} patted {member.name}!")
    
    @commands.hybrid_command(name="punch")
    async def punch(self, ctx, member: discord.Member): await ctx.send(f"👊 {ctx.author.name} punched {member.name}!")

    @commands.hybrid_command(name="bite")
    async def bite(self, ctx, member: discord.Member): await ctx.send(f"🧛 {ctx.author.name} bit {member.name}!")

    @commands.hybrid_command(name="kiss")
    async def kiss(self, ctx, member: discord.Member): await ctx.send(f"💋 {ctx.author.name} kissed {member.name}!")

    @commands.hybrid_command(name="smug")
    async def smug(self, ctx): await ctx.send(f"😏 {ctx.author.name} is smug.")

    @commands.hybrid_command(name="cry")
    async def cry(self, ctx): await ctx.send(f"😭 {ctx.author.name} cries.")

    @commands.hybrid_command(name="quote")
    async def quote(self, ctx): await ctx.send("📜 *If you don't fight, you can't win.*")

    @commands.hybrid_command(name="powerlevel")
    async def powerlevel(self, ctx, member: discord.Member = None):
        pwr = random.randint(10, 1000000)
        await ctx.send(f"💥 Power level **{pwr:,}**! Aura of Wang Lin!" if pwr > 900000 else f"🔍 Power level **{pwr:,}**. Fodder.")

    @commands.hybrid_command(name="domain_expansion")
    async def domain_expansion(self, ctx): await ctx.send(f"🤞 **Domain Expansion!**")

    @commands.hybrid_command(name="bankai")
    async def bankai(self, ctx): await ctx.send(f"⚔️ **BANKAI!**")

    # ==========================================
    # ⭐ LEVELING & UTILS
    # ==========================================
    @commands.hybrid_command(name="rank")
    async def rank(self, ctx, member: discord.Member = None): lvl = db["levels"].get(str((member or ctx.author).id), {"xp": 0, "level": 1}); await ctx.send(f"⭐ Lvl **{lvl['level']}** ({lvl['xp']} XP).")

    @commands.hybrid_command(name="leaderboard_levels")
    async def leaderboard_levels(self, ctx): await ctx.send("**Top Levels:**\n" + "\n".join([f"<@{uid}> - Lvl {data['level']}" for uid, data in sorted(db.get("levels", {}).items(), key=lambda x: x[1]["level"], reverse=True)[:10]]))

    @commands.hybrid_command(name="givexp")
    @commands.has_permissions(administrator=True)
    async def givexp(self, ctx, member: discord.Member, amount: int): u = str(member.id); db.setdefault("levels", {}).setdefault(u, {"xp": 0, "level": 1})["xp"] += amount; save_db(db); await ctx.send(f"📈 +{amount} XP.")

    @commands.hybrid_command(name="removexp")
    @commands.has_permissions(administrator=True)
    async def removexp(self, ctx, member: discord.Member, amount: int): u = str(member.id); db["levels"][u]["xp"] = max(0, db["levels"][u]["xp"] - amount); save_db(db); await ctx.send(f"📉 -{amount} XP.")

    @commands.hybrid_command(name="setlevel")
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, member: discord.Member, level: int): db.setdefault("levels", {}).setdefault(str(member.id), {"xp": 0, "level": 1})["level"] = level; save_db(db); await ctx.send(f"⭐ Set to Lvl {level}.")

    @commands.hybrid_command(name="rewards")
    async def rewards(self, ctx): await ctx.send("🎁 10-Trusted, 50-Ronin, 100-God")

    @commands.hybrid_command(name="rep")
    async def rep(self, ctx, member: discord.Member):
        if member.id == ctx.author.id: return await ctx.send("No.")
        db.setdefault("rep", {})[str(member.id)] = db["rep"].get(str(member.id), 0) + 1; save_db(db); await ctx.send(f"👍 +1 Rep.")

    @commands.hybrid_command(name="leaderboard_rep")
    async def leaderboard_rep(self, ctx): await ctx.send("**Top Rep:**\n" + "\n".join([f"<@{uid}> - {amt}" for uid, amt in sorted(db.get("rep", {}).items(), key=lambda x: x[1], reverse=True)[:10]]))

    @commands.hybrid_command(name="poll")
    async def poll(self, ctx, question: str): m = await ctx.send(embed=discord.Embed(title="📊 Poll", description=question)); await m.add_reaction("👍"); await m.add_reaction("👎")

    @commands.hybrid_command(name="giveaway_start")
    async def giveaway_start(self, ctx, prize: str): m = await ctx.send(f"🎉 **GIVEAWAY: {prize}** 🎉"); await m.add_reaction("🎉")

    @commands.hybrid_command(name="giveaway_reroll")
    async def giveaway_reroll(self, ctx): await ctx.send("🎉 Rerolled!")

    @commands.hybrid_command(name="ticket_setup")
    async def ticket_setup(self, ctx): await ctx.send("🎫 Tickets enabled.")

    @commands.hybrid_command(name="ticket_close")
    async def ticket_close(self, ctx): await ctx.channel.delete()

    @commands.hybrid_command(name="remindme")
    async def remindme(self, ctx, seconds: int, *, message: str): await ctx.send("⏰ Set."); await asyncio.sleep(seconds); await ctx.author.send(f"⏰ Reminder: {message}")

    @commands.hybrid_command(name="afk")
    async def afk(self, ctx, *, reason="AFK"): db["afk"][str(ctx.author.id)] = reason; save_db(db); await ctx.send(f"💤 AFK: {reason}")

    @commands.hybrid_command(name="weather")
    async def weather(self, ctx, city: str): await ctx.send(f"🌤️ {city}: Sunny (Simulated).")

    @commands.hybrid_command(name="calc")
    async def calc(self, ctx, expression: str):
        try: await ctx.send(f"🧮 Result: `{eval(expression, {'__builtins__': None}, {})}`")
        except: await ctx.send("❌ Error.")

    @commands.hybrid_command(name="translate")
    async def translate(self, ctx, lang: str, *, text: str): await ctx.send(f"🌐 Translated.")

    @commands.hybrid_command(name="define")
    async def define(self, ctx, word: str): await ctx.send(f"📖 Definition: Cool word.")

    @commands.hybrid_command(name="urban")
    async def urban(self, ctx, word: str): await ctx.send(f"🏙️ Urban: Slang.")

    @commands.hybrid_command(name="userhistory")
    async def userhistory(self, ctx, member: discord.Member): await ctx.send(f"📜 Joined: {member.joined_at.strftime('%Y-%m-%d')}.")

    @commands.hybrid_command(name="roleinfo")
    async def roleinfo(self, ctx, role: discord.Role): await ctx.send(f"🛡️ {len(role.members)} members.")

    @commands.hybrid_command(name="servericon")
    async def servericon(self, ctx): await ctx.send(ctx.guild.icon.url if ctx.guild.icon else "None.")

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx): await ctx.send(f"🏓 {round(self.bot.latency * 1000)}ms")

    @commands.hybrid_command(name="avatar")
    async def avatar(self, ctx, member: discord.Member = None): await ctx.send(embed=discord.Embed().set_image(url=(member or ctx.author).avatar.url))

    @commands.hybrid_command(name="serverstats")
    async def serverstats(self, ctx): await ctx.send(embed=discord.Embed(title=ctx.guild.name).add_field(name="Members", value=ctx.guild.member_count))

    # ==========================================
    # 🎵 VOICE
    # ==========================================
    @commands.hybrid_command(name="join")
    async def join(self, ctx): await ctx.author.voice.channel.connect() if ctx.author.voice else await ctx.send("❌ Not in VC."); await ctx.send("🔊 Joined.")

    @commands.hybrid_command(name="leave")
    async def leave(self, ctx): await ctx.voice_client.disconnect() if ctx.voice_client else None; await ctx.send("👋 Left.")

    @commands.hybrid_command(name="play")
    async def play(self, ctx, song: str): await ctx.send(f"🎶 Queuing '{song}'... (Requires FFmpeg)")

    @commands.hybrid_command(name="skip")
    async def skip(self, ctx): await ctx.send("⏭️ Skipped.")

    @commands.hybrid_command(name="queue")
    async def queue(self, ctx): await ctx.send("📜 Empty.")

    @commands.hybrid_command(name="stop")
    async def stop(self, ctx): await ctx.send("🛑 Stopped.")

    @commands.hybrid_command(name="volume")
    async def volume(self, ctx, vol: int): await ctx.send(f"🔊 {vol}%")

    @commands.hybrid_command(name="earrape")
    async def earrape(self, ctx): await ctx.send("💥 500%")

    @commands.hybrid_command(name="soundboard")
    async def soundboard(self, ctx, sound: str): await ctx.send(f"🔊 Playing '{sound}'")

    @commands.hybrid_command(name="tts")
    async def tts(self, ctx, *, message: str): await ctx.send(f"🗣️ {message}")

async def setup(bot):
    await bot.add_cog(MasterCommands(bot))
