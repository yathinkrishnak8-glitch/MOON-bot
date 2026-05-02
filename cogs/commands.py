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
        "warns": {}, 
        "jailed": {}, 
        "config": {"filterwords": [], "ai_channel": None, "cmd_channel": None, "event_channel": None, "antiraid": False}, 
        "economy": {}, 
        "levels": {}, 
        "custom_commands": {}, 
        "afk": {}, 
        "inventory": {}, 
        "rep": {}, 
        "bounties": {},
        "current_shop": [] # Stores dynamic shop items
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

# ==========================================
# INTERACTIVE UI: DYNAMIC SHOP
# ==========================================
class BuyButton(discord.ui.Button):
    def __init__(self, item):
        super().__init__(label=f"Buy {item['name']} ({item['price']:,})", style=discord.ButtonStyle.success)
        self.item = item

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if db["economy"].get(uid, 0) < self.item["price"]:
            return await interaction.response.send_message(f"❌ You don't have enough coins for **{self.item['name']}**.", ephemeral=True)
            
        db["economy"][uid] -= self.item["price"]
        if uid not in db["inventory"]: db["inventory"][uid] = []
        db["inventory"][uid].append(self.item["name"])
        save_db(db)
        
        await interaction.response.send_message(f"✅ **Transaction Successful!** You bought **{self.item['name']}**.", ephemeral=True)

class DynamicShopView(discord.ui.View):
    def __init__(self, shop_items):
        super().__init__(timeout=300)
        for item in shop_items:
            self.add_item(BuyButton(item))

# ==========================================
# INTERACTIVE UI: AI DUNGEON MASTER
# ==========================================
class AIBossFightView(discord.ui.View):
    def __init__(self, ctx, ai_client, chat_history):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.ai_client = ai_client
        self.chat_history = chat_history # Stores the ongoing story

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ This is not your boss fight!", ephemeral=True)
            return False
        return True

    async def process_turn(self, interaction: discord.Interaction, action: str):
        await interaction.response.defer()
        
        # Tell the AI what the player did
        self.chat_history.append({"role": "user", "content": f"I choose to: {action}. Describe the outcome of my action, the boss's counter-attack, and the environment. Keep it under 100 words. At the very end of your response, output exactly '[CONTINUE]', '[WIN]', or '[LOSE]' so the system knows the battle state."})
        
        # Ask Groq to generate the next phase of the fight
        try:
            response = self.ai_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=self.chat_history
            ).choices[0].message.content.strip()
        except:
            return await interaction.edit_original_response(content="❌ AI Dungeon Master disconnected. Fight aborted.")

        self.chat_history.append({"role": "assistant", "content": response})

        # Check win/loss conditions written by AI
        if "[WIN]" in response.upper():
            clean_text = response.replace("[WIN]", "").replace("[win]", "").strip()
            reward = random.randint(500000, 2000000)
            db["economy"][str(self.ctx.author.id)] = db["economy"].get(str(self.ctx.author.id), 0) + reward
            save_db(db)
            
            embed = discord.Embed(title="🏆 BOSS SLAIN!", description=f"{clean_text}\n\n**Rewards Claimed:** {reward:,} Coins!", color=discord.Color.gold())
            for child in self.children: child.disabled = True
            await interaction.edit_original_response(embed=embed, view=self)
            
        elif "[LOSE]" in response.upper():
            clean_text = response.replace("[LOSE]", "").replace("[lose]", "").strip()
            embed = discord.Embed(title="💀 YOU DIED", description=clean_text, color=discord.Color.dark_red())
            for child in self.children: child.disabled = True
            await interaction.edit_original_response(embed=embed, view=self)
            
        else:
            clean_text = response.replace("[CONTINUE]", "").replace("[continue]", "").strip()
            embed = discord.Embed(title="⚔️ BOSS FIGHT CONTINUES", description=clean_text, color=discord.Color.dark_theme())
            await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Attack 🗡️", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, "Aggressively attack the boss with my weapon.")

    @discord.ui.button(label="Use Magic ✨", style=discord.ButtonStyle.primary)
    async def magic_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, "Cast a powerful offensive magic spell at the boss.")

    @discord.ui.button(label="Defend 🛡️", style=discord.ButtonStyle.success)
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, "Take a defensive stance to block the next attack and look for an opening.")

    @discord.ui.button(label="Flee 🏃", style=discord.ButtonStyle.secondary)
    async def run_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🏃 YOU FLED", description="You ran away from the boss like a coward.", color=discord.Color.light_grey())
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

class MasterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
        self.client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.ai_event_loop.start()
        self.shop_refresh_loop.start()

    def cog_unload(self):
        self.ai_event_loop.cancel()
        self.shop_refresh_loop.cancel()

    def ask_groq(self, messages):
        if not self.client: raise Exception("Groq API Key missing.")
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]:
            try: return self.client.chat.completions.create(model=model, messages=messages).choices[0].message.content.strip()
            except: continue 
        raise Exception("All AI models failed.")

    # ==========================================
    # AUTO-LOOPS
    # ==========================================
    @tasks.loop(minutes=60)
    async def shop_refresh_loop(self):
        master_items = [
            {"name": "True Bankai Awakening", "price": 5000000, "desc": "Unlocks your ultimate soul reaper potential."},
            {"name": "Gomu Gomu no Mi", "price": 10000000, "desc": "A legendary devil fruit. Tastes terrible."},
            {"name": "Heaven Defying Bead", "price": 50000000, "desc": "Wang Lin's ultimate artifact. Bends reality."},
            {"name": "Sukuna's Finger", "price": 2500000, "desc": "Eat it for immense power (and severe side effects)."},
            {"name": "Infinity Stone", "price": 25000000, "desc": "Glows with immense universal energy."},
            {"name": "Death Note", "price": 8000000, "desc": "A strange black notebook. Handle with care."},
            {"name": "Aura of the Conqueror", "price": 3000000, "desc": "Makes enemies faint when you walk by."},
            {"name": "Philosopher's Stone", "price": 15000000, "desc": "Equivalent exchange is a myth with this."}
        ]
        
        new_shop = random.sample(master_items, 4)
        db["current_shop"] = new_shop
        save_db(db)
        
        if not self.client: return
        channel_id = db["config"].get("event_channel")
        if not channel_id: return
        channel = self.bot.get_channel(channel_id)
        if channel:
            embed = discord.Embed(title="🏪 THE MYSTIC SHOP HAS RESTOCKED", description="The traveling merchant has arrived with new legendary artifacts! Use `/shop` to view them.", color=discord.Color.magenta())
            await channel.send(embed=embed)

    @shop_refresh_loop.before_loop
    async def before_shop_loop(self): await self.bot.wait_until_ready()

    @tasks.loop(minutes=60)
    async def ai_event_loop(self):
        if not self.client: return
        channel_id = db["config"].get("event_channel")
        if not channel_id: return
        channel = self.bot.get_channel(channel_id)
        if channel:
            try: 
                reply = self.ask_groq([{"role": "user", "content": "Generate a highly engaging, modern Discord event, hot take, or scenario to spark chat activity. Keep it short. Do not use JSON."}])
                await channel.send(embed=discord.Embed(title="🌟 Server Event", description=reply, color=discord.Color.blurple()))
            except: pass

    @ai_event_loop.before_loop
    async def before_event_loop(self): await self.bot.wait_until_ready()

    # ==========================================
    # CORE LISTENERS (AFK, DMs, XP)
    # ==========================================
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        uid = str(message.author.id)

        # DM AI Handler
        if not message.guild:
            if not self.client: return
            async with message.channel.typing():
                try: 
                    reply = self.ask_groq([{"role": "system", "content": "You are habbibi mod (:, a chaotic bot in DMs."}, {"role": "user", "content": message.content}])
                    await message.channel.send(reply[:2000])
                except: pass
            return 

        # AFK
        if uid in db["afk"]:
            del db["afk"][uid]; save_db(db)
            await message.channel.send(embed=discord.Embed(description=f"👋 Welcome back {message.author.mention}, AFK removed.", color=discord.Color.green()), delete_after=5)
        for mention in message.mentions:
            if str(mention.id) in db["afk"]: 
                await message.channel.send(embed=discord.Embed(description=f"💤 **{mention.name}** is AFK: {db['afk'][str(mention.id)]}", color=discord.Color.dark_grey()))

        # Automod
        for word in db["config"]["filterwords"]:
            if word in message.content.lower():
                try:
                    await message.delete()
                    await message.channel.send(embed=discord.Embed(description=f"⚠️ {message.author.mention}, that word is blacklisted!", color=discord.Color.red()), delete_after=5)
                except: pass
                return

        # XP
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["xp"] += random.randint(10, 25)
        if db["levels"][uid]["xp"] >= (db["levels"][uid]["level"] * 100) * 1.5 and db["levels"][uid]["level"] < 13000:
            db["levels"][uid]["level"] += 1; save_db(db)
            await message.channel.send(embed=discord.Embed(title="Level Up!", description=f"🎉 **{message.author.mention}** leveled up to **Level {db['levels'][uid]['level']}**!", color=discord.Color.gold()))
        else: save_db(db)

        # Prefix Commands
        if message.content.startswith('!') and len(message.content) > 1:
            cmd = message.content[1:].split()[0].lower()
            if cmd in db["custom_commands"]: return await message.channel.send(db["custom_commands"][cmd])

        # Server AI Chat
        if message.channel.id == db["config"].get("ai_channel") and not message.content.startswith(('!', '/')) and self.client:
            async with message.channel.typing():
                try: 
                    reply = self.ask_groq([{"role": "system", "content": "You are habbibi mod (:, a sarcastic bot."}, {"role": "user", "content": message.content}])
                    await message.channel.send(reply[:2000])
                except: pass

    # ==========================================
    # CONFIG & SERVER DEPLOY
    # ==========================================
    @commands.hybrid_command(name="setaichannel", description="Sets the AI auto-reply channel.")
    @commands.has_permissions(administrator=True)
    async def setaichannel(self, ctx): db["config"]["ai_channel"] = ctx.channel.id; save_db(db); await ctx.send(f"🤖 AI Chat bound to {ctx.channel.mention}")

    @commands.hybrid_command(name="setcmdchannel", description="Locks commands to channel.")
    @commands.has_permissions(administrator=True)
    async def setcmdchannel(self, ctx): db["config"]["cmd_channel"] = ctx.channel.id; save_db(db); await ctx.send(f"🔒 Commands bound to {ctx.channel.mention}")

    @commands.hybrid_command(name="seteventchannel", description="Sets AI event channel.")
    @commands.has_permissions(administrator=True)
    async def seteventchannel(self, ctx): db["config"]["event_channel"] = ctx.channel.id; save_db(db); await ctx.send(f"🌟 Events bound to {ctx.channel.mention}")

    @commands.hybrid_command(name="deployserver", description="Wipes and builds server layout.")
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
    # 🧠 AI UTILITIES & AI BOSS FIGHT
    # ==========================================
    @commands.hybrid_command(name='aicommand', description="Master AI brain. Execute any python code dynamically.")
    @commands.has_permissions(administrator=True)
    async def aicommand(self, ctx, *, instruction: str):
        if not self.client: return await ctx.send("🤖 AI offline.")
        await ctx.defer()
        prompt = f"""Omnipotent bot. Output JSON array: 1. Reply: {{"action": "reply", "message": "text"}} 2. Execute Python: {{"action": "execute", "code": "await ctx.send('Done!')"}}
        STRICT RULES: JSON ARRAY ONLY. Write discord.py async code. Access: 'ctx', 'bot', 'discord', 'asyncio', 'db'.\nInstruction: {instruction}"""
        try:
            raw = self.ask_groq([{"role": "user", "content": prompt}])
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

    @commands.hybrid_command(name="bossfight", description="Start an interactive UI Boss Fight powered by AI.")
    async def bossfight(self, ctx):
        if not self.client: 
            return await ctx.send(embed=discord.Embed(description="❌ AI is offline. The Dungeon Master is sleeping.", color=discord.Color.red()))
        await ctx.defer()
        
        # 1. Ask AI to generate the scenario
        setup_prompt = "You are an epic Dungeon Master. Generate the absolute beginning of a dark fantasy boss fight. Describe the terrifying boss appearing before the player. Keep it under 150 words. Do NOT resolve the fight yet. End with the boss preparing to strike."
        
        chat_history = [
            {"role": "system", "content": "You are a ruthless Dungeon Master. The player will make choices. You must describe the outcome, the damage taken, and the environment. Keep responses under 100 words. At the end of every response, you must append '[CONTINUE]' if the fight goes on, '[WIN]' if the boss dies, or '[LOSE]' if the player dies."},
            {"role": "user", "content": setup_prompt}
        ]
        
        try:
            scenario = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=chat_history
            ).choices[0].message.content.strip()
        except:
            return await ctx.send("❌ Failed to connect to AI Dungeon Master.")

        # 2. Save the AI's response to the history so it remembers
        chat_history.append({"role": "assistant", "content": scenario})
        
        # 3. Create the View and attach the memory
        view = AIBossFightView(ctx, self.client, chat_history)
        embed = discord.Embed(title="⚔️ BOSS ENCOUNTER", description=scenario, color=discord.Color.dark_red())
        embed.set_footer(text="Choose your action below...")
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="define", description="AI powered dictionary definition.")
    async def define(self, ctx, word: str): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = self.ask_groq([{"role": "user", "content": f"Give a precise dictionary definition for the word: '{word}'"}])
        await ctx.send(embed=discord.Embed(title=f"📖 Definition: {word.title()}", description=reply, color=discord.Color.dark_blue()))

    @commands.hybrid_command(name="urban", description="AI powered Urban Dictionary.")
    async def urban(self, ctx, word: str): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = self.ask_groq([{"role": "user", "content": f"Give an internet slang 'Urban Dictionary' style definition for: '{word}'. Safe for work."}])
        await ctx.send(embed=discord.Embed(title=f"🏙️ Urban Dictionary: {word.title()}", description=reply, color=discord.Color.dark_green()))

    @commands.hybrid_command(name="forceevent", description="Force hourly event.")
    @commands.has_permissions(administrator=True)
    async def forceevent(self, ctx): await ctx.send(embed=discord.Embed(title="🌟 Event", description=self.ask_groq([{"role": "user", "content": "Generate a modern Discord event."}]), color=discord.Color.blurple()))

    @commands.hybrid_command(name="tldr", description="AI summarizes chat.")
    async def tldr(self, ctx): await ctx.defer(); log = "\n".join([m.content async for m in ctx.channel.history(limit=50) if m.content]); await ctx.send(f"📜 **TL;DR:** {self.ask_groq([{'role': 'user', 'content': f'Summarize: {log}'}])}")

    @commands.hybrid_command(name="roast_history", description="AI roasts history.")
    async def roast_history(self, ctx, member: discord.Member): await ctx.defer(); log = "\n".join([m.content async for m in ctx.channel.history(limit=20) if m.author == member and m.content]); await ctx.send(f"🔥 **Roast for {member.name}:**\n{self.ask_groq([{'role': 'user', 'content': f'Roast based on: {log}'}])}")

    @commands.hybrid_command(name="gothic_translate", description="Translate to dark fantasy.")
    async def gothic_translate(self, ctx, *, text: str): await ctx.defer(); await ctx.send(f"🦇 **Gothic:**\n{self.ask_groq([{'role': 'user', 'content': f'Rewrite into dark gothic royal decree: {text}'}])}")

    @commands.hybrid_command(name="lore", description="AI generates server lore.")
    async def lore(self, ctx): await ctx.defer(); await ctx.send(f"📖 **Server Lore:**\n{self.ask_groq([{'role': 'user', 'content': 'Write dark fantasy backstory for this server.'}])}")

    @commands.hybrid_command(name="vibecheck", description="AI vibe check.")
    async def vibecheck(self, ctx, member: discord.Member): await ctx.defer(); log = "\n".join([m.content async for m in ctx.channel.history(limit=20) if m.author == member and m.content]); await ctx.send(f"🔮 **Vibe Check:**\n{self.ask_groq([{'role': 'user', 'content': f'Analyze vibe humorously: {log}'}])}")

    # ==========================================
    # 💰 HIGH-TIER DYNAMIC ECONOMY & SHOP UI
    # ==========================================
    @commands.hybrid_command(name="shop", description="View the interactive rotating Legendary Shop.")
    async def shop(self, ctx): 
        items = db.get("current_shop", [])
        if not items:
            return await ctx.send(embed=discord.Embed(description="🛒 The merchant is currently traveling. The shop will restock soon.", color=discord.Color.dark_grey()))
            
        embed = discord.Embed(title="🛒 The Mystic Merchant", description="The shop restocks randomly every 60 minutes.\nClick the buttons below to purchase an artifact.", color=discord.Color.gold())
        for item in items:
            embed.add_field(name=f"✨ {item['name']}", value=f"**Price:** {item['price']:,} Coins\n*{item['desc']}*", inline=False)
            
        # Attach the dynamic UI View
        view = DynamicShopView(items)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="inventory", description="Check your legendary items.")
    async def inventory(self, ctx): 
        uid = str(ctx.author.id)
        items = db.get("inventory", {}).get(uid, [])
        embed = discord.Embed(title=f"🎒 {ctx.author.name}'s Relics", description="\n".join([f"- {i}" for i in items]) if items else "Inventory is empty.", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="bal", description="Check your coin balance.")
    async def bal(self, ctx, member: discord.Member = None): 
        target = member or ctx.author
        balance = db["economy"].get(str(target.id), 0)
        await ctx.send(embed=discord.Embed(title="🏦 Bank Account", description=f"💰 **{target.name}** has **{balance:,}** coins.", color=discord.Color.green()))

    @commands.hybrid_command(name="daily", description="Claim daily coins.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx): 
        uid = str(ctx.author.id); db["economy"][uid] = db["economy"].get(uid, 0) + 500000; save_db(db)
        await ctx.send(embed=discord.Embed(description="🎁 **You claimed your daily 500,000 coins!**", color=discord.Color.gold()))

    @commands.hybrid_command(name="weekly", description="Claim weekly coins.")
    @commands.cooldown(1, 604800, commands.BucketType.user)
    async def weekly(self, ctx): 
        uid = str(ctx.author.id); db["economy"][uid] = db["economy"].get(uid, 0) + 5000000; save_db(db)
        await ctx.send(embed=discord.Embed(description="💎 **You claimed massive 5,000,000 weekly coins!**", color=discord.Color.purple()))

    @commands.hybrid_command(name="work", description="Work for coins.")
    @commands.cooldown(1, 3600, commands.BucketType.user) 
    async def work(self, ctx): 
        earned = random.randint(50000, 150000)
        uid = str(ctx.author.id); db["economy"][uid] = db["economy"].get(uid, 0) + earned; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"💼 **You worked and earned {earned:,} coins!**", color=discord.Color.green()))

    @commands.hybrid_command(name="crime", description="Commit a crime for coins (risky).")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def crime(self, ctx):
        uid = str(ctx.author.id)
        if random.choice([True, False]): 
            earned = random.randint(100000, 400000)
            db["economy"][uid] = db["economy"].get(uid, 0) + earned
            await ctx.send(embed=discord.Embed(description=f"🥷 **You hacked the mainframe and stole {earned:,} coins!**", color=discord.Color.purple()))
        else: 
            lost = random.randint(50000, 150000)
            db["economy"][uid] = max(0, db["economy"].get(uid, 0) - lost)
            await ctx.send(embed=discord.Embed(description=f"🚓 **The feds caught you! You paid a fine of {lost:,} coins.**", color=discord.Color.red()))
        save_db(db)

    @commands.hybrid_command(name="rob", description="Steal from another user.")
    @commands.cooldown(1, 7200, commands.BucketType.user)
    async def rob(self, ctx, member: discord.Member):
        uid, tid = str(ctx.author.id), str(member.id)
        if db["economy"].get(tid, 0) < 100000: return await ctx.send(embed=discord.Embed(description=f"❌ **{member.name} is too poor to rob.**", color=discord.Color.red()))
        if random.choice([True, False]): 
            stolen = random.randint(50000, int(db["economy"][tid] * 0.25))
            db["economy"][tid] -= stolen; db["economy"][uid] = db["economy"].get(uid, 0) + stolen
            await ctx.send(embed=discord.Embed(description=f"🔫 **You mugged {member.name} and stole {stolen:,} coins!**", color=discord.Color.dark_green()))
        else: 
            fine = 100000
            db["economy"][uid] = max(0, db["economy"].get(uid, 0) - fine)
            await ctx.send(embed=discord.Embed(description=f"🛡️ **{member.name} fought back! You paid a {fine:,} coin hospital bill.**", color=discord.Color.dark_red()))
        save_db(db)

    @commands.hybrid_command(name="heist", description="Start a bank heist event.")
    @commands.cooldown(1, 14400, commands.BucketType.guild)
    async def heist(self, ctx): 
        payout = random.randint(1000000, 5000000)
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + payout; save_db(db)
        await ctx.send(embed=discord.Embed(title="🏦 BANK HEIST SUCCESSFUL!", description=f"You blew the vault and escaped with **{payout:,} coins!**", color=discord.Color.gold()))

    @commands.hybrid_command(name="slots", description="Virtual slot machine for millionaires.")
    async def slots(self, ctx, bet: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: return await ctx.send(embed=discord.Embed(description="❌ **Not enough coins.**", color=discord.Color.red()))
        db["economy"][uid] -= bet
        reels = ["🍒", "🍋", "💎", "⭐", "🔔"]
        r1, r2, r3 = random.choice(reels), random.choice(reels), random.choice(reels)
        msg = f"**SLOTS**\n| {r1} | {r2} | {r3} |\n\n"
        if r1 == r2 == r3: 
            db["economy"][uid] += bet * 10; embed = discord.Embed(description=msg + f"🎉 **JACKPOT!** You won **{bet*10:,} coins!**", color=discord.Color.gold())
        elif r1 == r2 or r2 == r3 or r1 == r3: 
            db["economy"][uid] += int(bet * 1.5); embed = discord.Embed(description=msg + f"✨ **Small Win!** You got **{int(bet*1.5):,} coins!**", color=discord.Color.green())
        else: embed = discord.Embed(description=msg + "💥 **You lost.**", color=discord.Color.red())
        save_db(db); await ctx.send(embed=embed)
    # ==========================================
    # 🛡️ EMBEDDED MODERATION & UTILITY
    # ==========================================
    @commands.hybrid_command(name="tempban", description="Bans a user temporarily.")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member, days: int, *, reason: str="Temp Ban"): 
        await member.ban(reason=reason)
        await ctx.send(embed=discord.Embed(title="🔨 User Temp-Banned", description=f"**{member.name}** banned for {days} days.\nReason: {reason}", color=discord.Color.red()))
        await asyncio.sleep(days * 86400)
        await ctx.guild.unban(member, reason="Tempban expired.")

    @commands.hybrid_command(name="tempmute", description="Mutes a user.")
    @commands.has_permissions(moderate_members=True)
    async def tempmute(self, ctx, member: discord.Member, minutes: int, *, reason: str="Temp Mute"): 
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await ctx.send(embed=discord.Embed(title="🔇 User Muted", description=f"**{member.name}** timed out for {minutes}m.\nReason: {reason}", color=discord.Color.orange()))

    @commands.hybrid_command(name="warn", description="Warns a user.")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str="Violation"): 
        uid = str(member.id)
        if uid not in db["warns"]: db["warns"][uid] = []
        db["warns"][uid].append(reason); save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⚠️ **{member.mention} has been warned.**\nReason: {reason}", color=discord.Color.yellow()))

    @commands.hybrid_command(name="warnings", description="Shows warnings.")
    async def warnings(self, ctx, member: discord.Member): 
        warns = db["warns"].get(str(member.id), [])
        if not warns: return await ctx.send(embed=discord.Embed(description=f"✅ **{member.name} has a clean record.**", color=discord.Color.green()))
        embed = discord.Embed(title=f"⚠️ Warnings for {member.name}", color=discord.Color.orange())
        for i, w in enumerate(warns): embed.add_field(name=f"Warning {i+1}", value=w, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="purge", description="Deletes multiple messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int): 
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(embed=discord.Embed(description=f"🧹 **Swept {amount} messages.**", color=discord.Color.green()), delete_after=4)

    @commands.hybrid_command(name="snipe", description="Recovers the last deleted message.")
    async def snipe(self, ctx):
        data = snipes.get(ctx.channel.id)
        if not data: return await ctx.send(embed=discord.Embed(description="Nothing to snipe!", color=discord.Color.red()))
        embed = discord.Embed(description=data["content"], color=discord.Color.red())
        embed.set_author(name=data["author"], icon_url=data["avatar"])
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="editsnipe", description="Shows original text of edited message.")
    async def editsnipe(self, ctx):
        data = edit_snipes.get(ctx.channel.id)
        if not data: return await ctx.send(embed=discord.Embed(description="No edited messages!", color=discord.Color.red()))
        embed = discord.Embed(title="Edited Message", color=discord.Color.orange()).set_author(name=data["author"])
        embed.add_field(name="Before", value=data["before"], inline=False).add_field(name="After", value=data["after"], inline=False)
        await ctx.send(embed=embed)

    # ==========================================
    # 🤡 FUN, TROLLING & ANIME (PREFIX COMMANDS)
    # ==========================================
    @commands.command(name="fakeban")
    async def fakeban(self, ctx, member: discord.Member): 
        await ctx.send(embed=discord.Embed(title="User Banned", description=f"🔨 **{member.name}** has been permanently banned from the server.\n\n*Reason: Caught lacking.*", color=discord.Color.red()))

    @commands.command(name="rickroll")
    async def rickroll(self, ctx, member: discord.Member):
        try: 
            await member.send("🎁 **You have been gifted Discord Nitro!** Claim it here: [https://www.youtube.com/watch?v=dQw4w9WgXcQ](https://www.youtube.com/watch?v=dQw4w9WgXcQ)")
            await ctx.send(embed=discord.Embed(description=f"🤫 **Sent a disguised package to {member.name}.**", color=discord.Color.green()))
        except: 
            await ctx.send(embed=discord.Embed(description="❌ **Their DMs are closed.**", color=discord.Color.red()))

    @commands.command(name="howgay")
    async def howgay(self, ctx, member: discord.Member=None): 
        target = member or ctx.author
        await ctx.send(embed=discord.Embed(description=f"🏳️‍🌈 **{target.name}** is **{random.randint(0,100)}%** gay.", color=discord.Color.magenta()))

    @commands.command(name="simpmeter")
    async def simpmeter(self, ctx, member: discord.Member=None): 
        target = member or ctx.author
        await ctx.send(embed=discord.Embed(description=f"😳 **{target.name}** is a **{random.randint(0,100)}%** simp.", color=discord.Color.purple()))

    @commands.command(name="roast")
    async def roast(self, ctx, member: discord.Member):
        roasts = ["You're like a cloud. When you disappear, it's a beautiful day.", "I'd agree with you but then we’d both be wrong."]
        await ctx.send(embed=discord.Embed(description=f"{member.mention} 🔥 {random.choice(roasts)}", color=discord.Color.dark_orange()))

    @commands.command(name="pat")
    async def pat(self, ctx, member: discord.Member): 
        await ctx.send(embed=discord.Embed(description=f"🤚 **{ctx.author.name} gently patted {member.name} on the head!**", color=discord.Color.pink()))
    
    @commands.command(name="punch")
    async def punch(self, ctx, member: discord.Member): 
        await ctx.send(embed=discord.Embed(description=f"👊 **{ctx.author.name} totally decked {member.name}!**", color=discord.Color.red()))

    @commands.command(name="bite")
    async def bite(self, ctx, member: discord.Member): 
        await ctx.send(embed=discord.Embed(description=f"🧛 **{ctx.author.name} bit {member.name}!**", color=discord.Color.dark_red()))

    @commands.command(name="quote")
    async def quote(self, ctx):
        quotes = ["If you don't fight, you can't win.", "Since when were you under the impression that I wasn't using Kyoka Suigetsu?"]
        await ctx.send(embed=discord.Embed(description=f"📜 *\"{random.choice(quotes)}\"*", color=discord.Color.dark_theme()))

    @commands.command(name="powerlevel")
    async def powerlevel(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        pwr = random.randint(10, 10000000)
        if pwr > 5000000: 
            await ctx.send(embed=discord.Embed(description=f"💥 **{target.mention}'s power level is {pwr:,}!** Wang Lin aura!", color=discord.Color.gold()))
        else: 
            await ctx.send(embed=discord.Embed(description=f"🔍 **{target.mention}'s power level is {pwr:,}.** Fodder.", color=discord.Color.light_grey()))

    @commands.command(name="domain_expansion")
    async def domain_expansion(self, ctx): 
        await ctx.send(embed=discord.Embed(description=f"🤞 **Domain Expansion!** {ctx.author.mention} trapped the chat in their domain!", color=discord.Color.dark_blue()))

# ==========================================
# FINAL SETUP SINK
# ==========================================
async def setup(bot):
    await bot.add_cog(MasterCommands(bot))

