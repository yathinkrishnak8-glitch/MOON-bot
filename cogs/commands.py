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
        "current_shop": [] # Stores the dynamic shop items
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
# INTERACTIVE UI PANELS (Buttons & Menus)
# ==========================================
class BossFightView(discord.ui.View):
    def __init__(self, ctx, boss_name, boss_hp):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.boss_name = boss_name
        self.boss_hp = boss_hp
        self.boss_max_hp = boss_hp
        self.player_hp = 1000
        self.player_max_hp = 1000

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ This is not your boss fight!", ephemeral=True)
            return False
        return True

    def generate_embed(self):
        embed = discord.Embed(title=f"⚔️ BOSS FIGHT: {self.boss_name}", color=discord.Color.dark_red())
        embed.add_field(name=f"👹 {self.boss_name} HP", value=f"{self.boss_hp} / {self.boss_max_hp}", inline=True)
        embed.add_field(name=f"🛡️ {self.ctx.author.name} HP", value=f"{self.player_hp} / {self.player_max_hp}", inline=True)
        return embed

    @discord.ui.button(label="Attack 🗡️", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        dmg = random.randint(150, 400)
        boss_dmg = random.randint(100, 300)
        
        self.boss_hp -= dmg
        self.player_hp -= boss_dmg
        
        if self.boss_hp <= 0:
            reward = random.randint(500000, 2000000)
            db["economy"][str(self.ctx.author.id)] = db["economy"].get(str(self.ctx.author.id), 0) + reward
            save_db(db)
            win_embed = discord.Embed(title="🏆 BOSS DEFEATED!", description=f"You dealt a fatal blow of {dmg} DMG!\n\n**Reward:** {reward:,} Coins!", color=discord.Color.gold())
            for child in self.children: child.disabled = True
            await interaction.response.edit_message(embed=win_embed, view=self)
            return

        if self.player_hp <= 0:
            lose_embed = discord.Embed(title="💀 YOU DIED", description=f"{self.boss_name} crushed you with {boss_dmg} DMG. You lost the fight.", color=discord.Color.dark_grey())
            for child in self.children: child.disabled = True
            await interaction.response.edit_message(embed=lose_embed, view=self)
            return

        embed = self.generate_embed()
        embed.description = f"You dealt **{dmg} DMG**!\n{self.boss_name} hit back for **{boss_dmg} DMG**!"
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Heal 🧪", style=discord.ButtonStyle.success)
    async def heal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        heal = random.randint(200, 500)
        boss_dmg = random.randint(100, 300)
        
        self.player_hp = min(self.player_max_hp, self.player_hp + heal)
        self.player_hp -= boss_dmg
        
        if self.player_hp <= 0:
            lose_embed = discord.Embed(title="💀 YOU DIED", description=f"You tried to heal, but {self.boss_name} executed you with {boss_dmg} DMG.", color=discord.Color.dark_grey())
            for child in self.children: child.disabled = True
            await interaction.response.edit_message(embed=lose_embed, view=self)
            return

        embed = self.generate_embed()
        embed.description = f"You healed for **{heal} HP**!\n{self.boss_name} attacked while you were healing for **{boss_dmg} DMG**!"
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Flee 🏃", style=discord.ButtonStyle.secondary)
    async def run_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🏃 YOU FLED", description="You ran away from the boss like a coward.", color=discord.Color.light_grey())
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)


class MasterlistView(discord.ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.current_page = 0

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == len(self.embeds) - 1

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
    # AUTO-LOOPS (Shop Refresh & AI Events)
    # ==========================================
    @tasks.loop(minutes=60)
    async def shop_refresh_loop(self):
        # Massive pool of high-tier items in the Millions
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
        
        # Pick 4 random items for the shop
        new_shop = random.sample(master_items, 4)
        db["current_shop"] = new_shop
        save_db(db)
        
        # AI Event Drop for the restock
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
    # BEAUTIFUL COMMAND MASTERLIST
    # ==========================================
    @commands.hybrid_command(name="masterlist", description="View all bot commands in an interactive panel.")
    async def masterlist(self, ctx):
        embeds = []
        
        e1 = discord.Embed(title="🤖 Masterlist: AI & Setup (Page 1/4)", color=discord.Color.blue())
        e1.add_field(name="/deployserver", value="Wipes and builds a modern server layout.", inline=False)
        e1.add_field(name="/aicommand", value="God-Mode AI executor.", inline=False)
        e1.add_field(name="/define & /urban", value="AI-powered dictionaries.", inline=False)
        e1.add_field(name="/lore & /bossfight", value="AI generates interactive lore and bosses.", inline=False)
        e1.add_field(name="/vibecheck & /roast_history", value="AI analyzes user chats.", inline=False)
        embeds.append(e1)

        e2 = discord.Embed(title="🛡️ Masterlist: Moderation (Page 2/4)", color=discord.Color.red())
        e2.add_field(name="/tempban & /tempmute", value="Temporary punishments.", inline=False)
        e2.add_field(name="/lockdown & /unlockdown", value="Server security protocols.", inline=False)
        e2.add_field(name="/snipe & /editsnipe", value="Catch deleted/edited messages.", inline=False)
        e2.add_field(name="/jail & /unjail", value="Strips roles and locks user in jail.", inline=False)
        e2.add_field(name="/warn & /warnings", value="Warning system.", inline=False)
        embeds.append(e2)

        e3 = discord.Embed(title="💰 Masterlist: RPG & Economy (Page 3/4)", color=discord.Color.gold())
        e3.add_field(name="/shop & /buy", value="Dynamic million-coin artifact shop.", inline=False)
        e3.add_field(name="/daily & /work & /crime", value="Earn massive amounts of coins.", inline=False)
        e3.add_field(name="/slots & /blackjack & /coinflip", value="Gamble your millions.", inline=False)
        e3.add_field(name="/heist & /rob", value="Steal from others.", inline=False)
        e3.add_field(name="/level & /rank", value="Check your XP.", inline=False)
        embeds.append(e3)

        e4 = discord.Embed(title="🤡 Masterlist: Fun & Anime [PREFIX] (Page 4/4)", color=discord.Color.purple())
        e4.add_field(name="!pat, !punch, !kiss, !bite", value="Anime roleplay actions.", inline=False)
        e4.add_field(name="!fakeban & !rickroll", value="Troll your friends.", inline=False)
        e4.add_field(name="!powerlevel & !domain_expansion", value="Weeb mechanics.", inline=False)
        e4.add_field(name="!susmeter & !simpmeter", value="Rate users.", inline=False)
        embeds.append(e4)

        view = MasterlistView(embeds)
        await ctx.send(embed=embeds[0], view=view)

    # ==========================================
    # 🧠 AI UTILITIES (Fixed Dictionary) & BOSS
    # ==========================================
    @commands.hybrid_command(name="define", description="AI powered dictionary definition.")
    async def define(self, ctx, word: str): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = self.ask_groq([{"role": "user", "content": f"Give a precise, comprehensive dictionary definition for the word: '{word}'"}])
        await ctx.send(embed=discord.Embed(title=f"📖 Definition: {word.title()}", description=reply, color=discord.Color.dark_blue()))

    @commands.hybrid_command(name="urban", description="AI powered Urban Dictionary.")
    async def urban(self, ctx, word: str): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = self.ask_groq([{"role": "user", "content": f"Give an internet slang 'Urban Dictionary' style definition for: '{word}'. Keep it funny but safe."}])
        await ctx.send(embed=discord.Embed(title=f"🏙️ Urban Dictionary: {word.title()}", description=reply, color=discord.Color.dark_green()))

    @commands.hybrid_command(name="bossfight", description="Start an interactive UI Boss Fight.")
    async def bossfight(self, ctx):
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        # Generate Boss Name via AI
        boss_name = self.ask_groq([{"role": "user", "content": "Generate ONLY the name of an epic dark fantasy boss monster. Nothing else."}])
        boss_hp = random.randint(3000, 8000)
        
        view = BossFightView(ctx, boss_name, boss_hp)
        embed = view.generate_embed()
        embed.description = f"**{boss_name} has appeared!** What will you do?"
        await ctx.send(embed=embed, view=view)

    # ==========================================
    # 💰 HIGH-TIER DYNAMIC ECONOMY & SHOP
    # ==========================================
    @commands.hybrid_command(name="bal", description="Check your coin balance.")
    async def bal(self, ctx, member: discord.Member = None): 
        target = member or ctx.author
        balance = db["economy"].get(str(target.id), 0)
        await ctx.send(embed=discord.Embed(title="🏦 Bank Account", description=f"💰 **{target.name}** has **{balance:,}** coins.", color=discord.Color.green()))

    @commands.hybrid_command(name="daily", description="Claim daily coins.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx): 
        uid = str(ctx.author.id)
        db["economy"][uid] = db["economy"].get(uid, 0) + 500000
        save_db(db)
        await ctx.send(embed=discord.Embed(description="🎁 **You claimed your daily 500,000 coins!**", color=discord.Color.gold()))

    @commands.hybrid_command(name="work", description="Work for coins.")
    @commands.cooldown(1, 3600, commands.BucketType.user) 
    async def work(self, ctx): 
        earned = random.randint(50000, 150000)
        uid = str(ctx.author.id)
        db["economy"][uid] = db["economy"].get(uid, 0) + earned
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"💼 **You worked a grueling shift and earned {earned:,} coins!**", color=discord.Color.green()))

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

    @commands.hybrid_command(name="shop", description="View the rotating Legendary Shop.")
    async def shop(self, ctx): 
        items = db.get("current_shop", [])
        if not items:
            return await ctx.send(embed=discord.Embed(description="🛒 The merchant is currently traveling. The shop will open soon.", color=discord.Color.dark_grey()))
            
        embed = discord.Embed(title="🛒 The Mystic Merchant", description="The shop restocks randomly every 60 minutes.\nUse `/buy <item>` to purchase.", color=discord.Color.gold())
        for item in items:
            embed.add_field(name=f"✨ {item['name']}", value=f"**Price:** {item['price']:,} Coins\n*{item['desc']}*", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="buy", description="Buy an item from the rotating shop.")
    async def buy(self, ctx, *, item_name: str):
        uid = str(ctx.author.id)
        current_shop = db.get("current_shop", [])
        
        # Find item in shop
        target_item = next((i for i in current_shop if i["name"].lower() == item_name.lower()), None)
        
        if not target_item: 
            return await ctx.send(embed=discord.Embed(description="❌ **That item is not currently in the shop.**", color=discord.Color.red()))
        if db["economy"].get(uid, 0) < target_item["price"]: 
            return await ctx.send(embed=discord.Embed(description="❌ **You are too broke for this legendary artifact.**", color=discord.Color.red()))
            
        db["economy"][uid] -= target_item["price"]
        if uid not in db["inventory"]: db["inventory"][uid] = []
        db["inventory"][uid].append(target_item["name"])
        save_db(db)
        
        await ctx.send(embed=discord.Embed(title="✅ Item Purchased!", description=f"You successfully bought **{target_item['name']}** for {target_item['price']:,} coins!\nIt has been added to your `/inventory`.", color=discord.Color.green()))

    @commands.hybrid_command(name="inventory", description="Check your legendary items.")
    async def inventory(self, ctx): 
        uid = str(ctx.author.id)
        items = db.get("inventory", {}).get(uid, [])
        embed = discord.Embed(title=f"🎒 {ctx.author.name}'s Relics", description="\n".join([f"- {i}" for i in items]) if items else "Inventory is empty.", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="slots", description="Virtual slot machine for millionaires.")
    async def slots(self, ctx, bet: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: 
            return await ctx.send(embed=discord.Embed(description="❌ **Not enough coins.**", color=discord.Color.red()))
            
        db["economy"][uid] -= bet
        reels = ["🍒", "🍋", "💎", "⭐", "🔔"]
        r1, r2, r3 = random.choice(reels), random.choice(reels), random.choice(reels)
        
        msg = f"**SLOTS**\n| {r1} | {r2} | {r3} |\n\n"
        
        if r1 == r2 == r3: 
            winnings = bet * 10
            db["economy"][uid] += winnings
            embed = discord.Embed(description=msg + f"🎉 **JACKPOT!** You won **{winnings:,} coins!**", color=discord.Color.gold())
        elif r1 == r2 or r2 == r3 or r1 == r3: 
            winnings = int(bet * 1.5)
            db["economy"][uid] += winnings
            embed = discord.Embed(description=msg + f"✨ **Small Win!** You got **{winnings:,} coins!**", color=discord.Color.green())
        else: 
            embed = discord.Embed(description=msg + "💥 **You lost.**", color=discord.Color.red())
            
        save_db(db)
        await ctx.send(embed=embed)

    # ==========================================
    # 🛡️ EMBEDDED MODERATION
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

    # ==========================================
    # 🤡 FUN, TROLLING & ANIME (PREFIX COMMANDS)
    # ==========================================
    @commands.command(name="fakeban")
    async def fakeban(self, ctx, member: discord.Member): 
        await ctx.send(embed=discord.Embed(title="User Banned", description=f"🔨 **{member.name}** has been permanently banned from the server.\n\n*Reason: Caught lacking.*", color=discord.Color.red()))

    @commands.command(name="rickroll")
    async def rickroll(self, ctx, member: discord.Member):
        try: 
            await member.send("🎁 **You have been gifted Discord Nitro!** Claim it here: https://www.youtube.com/watch?v=dQw4w9WgXcQ")
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

