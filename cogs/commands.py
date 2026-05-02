import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import random
import asyncio
from datetime import timedelta
from groq import AsyncGroq

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
        "current_shop": []
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
snipes = {}
edit_snipes = {}

# ==========================================
# OVERPOWERED UI PANELS (Buttons)
# ==========================================
class ConfirmView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("❌ This is not your button!", ephemeral=True)
        self.value = True
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("❌ This is not your button!", ephemeral=True)
        self.value = False
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

class PaginationView(discord.ui.View):
    def __init__(self, ctx, embeds):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.embeds = embeds
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.primary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not yours!", ephemeral=True)
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not yours!", ephemeral=True)
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

class BuyButton(discord.ui.Button):
    def __init__(self, item):
        super().__init__(label=f"Buy {item['name']} ({item['price']:,})", style=discord.ButtonStyle.success)
        self.item = item

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if db["economy"].get(uid, 0) < self.item["price"]:
            return await interaction.response.send_message(embed=discord.Embed(description=f"❌ You need **{self.item['price']:,} coins** for **{self.item['name']}**.", color=discord.Color.red()), ephemeral=True)
            
        db["economy"][uid] -= self.item["price"]
        if uid not in db["inventory"]: db["inventory"][uid] = []
        db["inventory"][uid].append(self.item["name"])
        save_db(db)
        
        await interaction.response.send_message(embed=discord.Embed(description=f"✅ **Purchased!** Added **{self.item['name']}** to your inventory.", color=discord.Color.green()), ephemeral=True)

class DynamicShopView(discord.ui.View):
    def __init__(self, shop_items):
        super().__init__(timeout=300)
        for item in shop_items:
            self.add_item(BuyButton(item))

class AIBossFightView(discord.ui.View):
    def __init__(self, ctx, ai_client, chat_history):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.ai_client = ai_client
        self.chat_history = chat_history

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ Run `/bossfight` to spawn your own boss!", ephemeral=True)
            return False
        return True

    async def process_turn(self, interaction: discord.Interaction, action: str):
        await interaction.response.defer()
        self.chat_history.append({
            "role": "user", 
            "content": f"I choose to: {action}. Describe the outcome of my action, the boss's counter-attack, and the environment. Keep it under 100 words. At the very end, output exactly '[CONTINUE]', '[WIN]', or '[LOSE]'."
        })
        
        try:
            response = await self.ai_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=self.chat_history
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            return await interaction.edit_original_response(content=f"❌ Dungeon Master disconnected: {e}")

        self.chat_history.append({"role": "assistant", "content": reply})

        if "[WIN]" in reply.upper():
            clean_text = reply.replace("[WIN]", "").replace("[win]", "").strip()
            reward = random.randint(1000000, 5000000)
            db["economy"][str(self.ctx.author.id)] = db["economy"].get(str(self.ctx.author.id), 0) + reward
            save_db(db)
            
            embed = discord.Embed(title="🏆 BOSS SLAIN!", description=f"{clean_text}\n\n💰 **Rewards:** {reward:,} Coins!", color=discord.Color.gold())
            embed.set_image(url="https://media1.tenor.com/m/6Z3aU2_7_8QAAAAd/anime-win.gif")
            for child in self.children: child.disabled = True
            await interaction.edit_original_response(embed=embed, view=self)
            
        elif "[LOSE]" in reply.upper():
            clean_text = reply.replace("[LOSE]", "").replace("[lose]", "").strip()
            embed = discord.Embed(title="💀 YOU DIED", description=clean_text, color=discord.Color.dark_red())
            embed.set_image(url="https://media1.tenor.com/m/8Y_2v_3_45wAAAAd/anime-dead.gif")
            for child in self.children: child.disabled = True
            await interaction.edit_original_response(embed=embed, view=self)
            
        else:
            clean_text = reply.replace("[CONTINUE]", "").replace("[continue]", "").strip()
            embed = discord.Embed(title="⚔️ BOSS FIGHT CONTINUES", description=clean_text, color=discord.Color.dark_theme())
            embed.set_image(url="https://media1.tenor.com/m/2Y4Z8v3_45wAAAAd/anime-fight.gif")
            await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Attack 🗡️", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, "Aggressively attack the boss with my primary weapon.")

    @discord.ui.button(label="Use Magic ✨", style=discord.ButtonStyle.primary)
    async def magic_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, "Cast a powerful offensive magic spell at the boss.")

    @discord.ui.button(label="Defend 🛡️", style=discord.ButtonStyle.success)
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, "Take a defensive stance to block the next attack.")

    @discord.ui.button(label="Flee 🏃", style=discord.ButtonStyle.secondary)
    async def run_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🏃 YOU FLED", description="You ran away from the boss like a coward.", color=discord.Color.light_grey())
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

# ==========================================
# CORE COG, AUTO-LOOPS & LISTENERS
# ==========================================
class MasterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
        self.client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.ai_event_loop.start()
        self.shop_refresh_loop.start()

    def cog_unload(self):
        self.ai_event_loop.cancel()
        self.shop_refresh_loop.cancel()

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandOnCooldown):
            m, s = divmod(int(error.retry_after), 60)
            h, m = divmod(m, 60)
            time_left = f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"
            embed = discord.Embed(description=f"⏳ **Hold up!** You are on cooldown. Try again in **{time_left}**.", color=discord.Color.red())
            
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx.send(embed=embed, delete_after=10)
        elif isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(description="❌ **You lack the permissions to use this command.**", color=discord.Color.red())
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx.send(embed=embed, delete_after=5)
        else:
            print(f"Ignored Error: {error}")

    async def ask_groq(self, messages):
        if not self.client: 
            raise Exception("Groq API Key missing.")
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]:
            try: 
                response = await self.client.chat.completions.create(model=model, messages=messages)
                return response.choices[0].message.content.strip()
            except: 
                continue 
        raise Exception("All AI models failed.")

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
        
        db["current_shop"] = random.sample(master_items, 4)
        save_db(db)
        
        channel_id = db["config"].get("event_channel")
        if channel_id and self.client: 
            channel = self.bot.get_channel(channel_id)
            if channel:
                embed = discord.Embed(title="🏪 THE MYSTIC SHOP HAS RESTOCKED", description="The traveling merchant has arrived with new legendary artifacts!\nUse `/shop` to view and interact with the store.", color=discord.Color.magenta())
                await channel.send(embed=embed)

    @shop_refresh_loop.before_loop
    async def before_shop_loop(self): 
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=60)
    async def ai_event_loop(self):
        channel_id = db["config"].get("event_channel")
        if channel_id and self.client:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try: 
                    reply = await self.ask_groq([{"role": "user", "content": "Generate a highly engaging, modern Discord event, hot take, or scenario to spark chat activity. Keep it short. Do not use JSON."}])
                    embed = discord.Embed(title="🌟 Server Event", description=reply, color=discord.Color.blurple())
                    await channel.send(embed=embed)
                except: 
                    pass

    @ai_event_loop.before_loop
    async def before_event_loop(self): 
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if db["config"].get("antiraid", False):
            try: await member.kick(reason="Anti-Raid protection active.")
            except: pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.author.bot: 
            snipes[message.channel.id] = {
                "content": message.content, 
                "author": message.author.name,
                "avatar": message.author.avatar.url if message.author.avatar else message.author.default_avatar.url
            }

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.author.bot: 
            edit_snipes[before.channel.id] = {"before": before.content, "after": after.content, "author": before.author.name}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        uid = str(message.author.id)

        if not message.guild:
            if not self.client: return
            async with message.channel.typing():
                try: 
                    reply = await self.ask_groq([
                        {"role": "system", "content": "You are habbibi mod (:, a chaotic, funny Discord bot. You are talking in private DMs."}, 
                        {"role": "user", "content": message.content}
                    ])
                    await message.channel.send(embed=discord.Embed(description=reply[:2000], color=discord.Color.blurple()))
                except Exception as e: 
                    await message.channel.send(embed=discord.Embed(description=f"❌ AI Error: {e}", color=discord.Color.red()))
            return 

        if uid in db["afk"]:
            del db["afk"][uid]
            save_db(db)
            await message.channel.send(embed=discord.Embed(description=f"👋 Welcome back {message.author.mention}, AFK removed.", color=discord.Color.green()), delete_after=10)
            
        for mention in message.mentions:
            if str(mention.id) in db["afk"]: 
                await message.channel.send(embed=discord.Embed(description=f"💤 **{mention.name}** is currently AFK: {db['afk'][str(mention.id)]}", color=discord.Color.dark_grey()))

        for word in db["config"]["filterwords"]:
            if word in message.content.lower():
                try:
                    await message.delete()
                    await message.channel.send(embed=discord.Embed(description=f"⚠️ {message.author.mention}, that word is blacklisted!", color=discord.Color.red()), delete_after=5)
                except: pass
                return

        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["xp"] += random.randint(10, 25)
        if db["levels"][uid]["xp"] >= (db["levels"][uid]["level"] * 100) * 1.5 and db["levels"][uid]["level"] < 13000:
            db["levels"][uid]["level"] += 1
            save_db(db)
            lvl_up = discord.Embed(title="Level Up!", description=f"🎉 **{message.author.mention}** leveled up to **Level {db['levels'][uid]['level']}**!", color=discord.Color.gold())
            lvl_up.set_image(url="https://media1.tenor.com/m/7_3X2v2X14YAAAAd/anime-level-up.gif")
            await message.channel.send(embed=lvl_up)
        else: 
            save_db(db)

        if message.content.startswith('!') and len(message.content) > 1:
            cmd = message.content[1:].split()[0].lower()
            if cmd in db["custom_commands"]: 
                return await message.channel.send(embed=discord.Embed(description=db["custom_commands"][cmd], color=discord.Color.blue()))

        ai_chan = db["config"].get("ai_channel")
        if message.channel.id == ai_chan and not message.content.startswith(('!', '/')) and self.client:
            async with message.channel.typing():
                try: 
                    reply = await self.ask_groq([
                        {"role": "system", "content": "You are habbibi mod (:, a chaotic and sarcastic Discord bot."}, 
                        {"role": "user", "content": message.content}
                    ])
                    await message.channel.send(embed=discord.Embed(description=reply[:2000], color=discord.Color.purple()))
                except: pass


    # ==========================================
    # CONFIG & MASTERLIST
    # ==========================================
    @commands.hybrid_command(name="setaichannel", description="Sets the AI auto-reply channel.")
    @commands.has_permissions(administrator=True)
    async def setaichannel(self, ctx): 
        db["config"]["ai_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🤖 **AI Auto-Chat bound to** {ctx.channel.mention}", color=discord.Color.green()))

    @commands.hybrid_command(name="setcmdchannel", description="Locks commands to a channel.")
    @commands.has_permissions(administrator=True)
    async def setcmdchannel(self, ctx): 
        db["config"]["cmd_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🔒 **Commands locked to** {ctx.channel.mention}", color=discord.Color.green()))

    @commands.hybrid_command(name="seteventchannel", description="Sets the hourly AI event channel.")
    @commands.has_permissions(administrator=True)
    async def seteventchannel(self, ctx): 
        db["config"]["event_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🌟 **AI Events bound to** {ctx.channel.mention}", color=discord.Color.green()))

    @commands.hybrid_command(name="unsetchannel", description="Unbinds a specific bot channel (ai, cmd, event).")
    @commands.has_permissions(administrator=True)
    async def unsetchannel(self, ctx, channel_type: str):
        valid_choices = {"ai": "ai_channel", "cmd": "cmd_channel", "event": "event_channel"}
        choice = channel_type.lower()
        if choice not in valid_choices:
            return await ctx.send(embed=discord.Embed(description="❌ **Invalid choice.** Please use `ai`, `cmd`, or `event`.", color=discord.Color.red()))
        
        db["config"][valid_choices[choice]] = None
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"✅ **Successfully unbound the {choice.upper()} channel.**", color=discord.Color.green()))

    @commands.hybrid_command(name="deployserver", description="Wipes the server and builds a Modern Layout.")
    @commands.has_permissions(administrator=True)
    async def deployserver(self, ctx):
        view = ConfirmView(ctx)
        msg = await ctx.send(embed=discord.Embed(title="⚠️ CLEAN SLATE PROTOCOL", description="Are you absolutely sure you want to WIPE the server and rebuild the layout?", color=discord.Color.red()), view=view)
        await view.wait()
        if not view.value: 
            return await msg.edit(embed=discord.Embed(description="🛑 Deployment Cancelled.", color=discord.Color.grey()), view=None)

        await msg.edit(embed=discord.Embed(description="⚙️ Wiping channels and roles...", color=discord.Color.orange()), view=None)
        guild = ctx.guild
        for c in guild.channels:
            try: await c.delete(); await asyncio.sleep(0.5)
            except: pass
        for r in guild.roles:
            if r.name != "@everyone" and not r.managed and r < ctx.guild.me.top_role:
                try: await r.delete(); await asyncio.sleep(0.5)
                except: pass
                    
        roles_to_make = [{"name": "Admin", "color": discord.Color.red()}, {"name": "Moderator", "color": discord.Color.orange()}, {"name": "Jailed", "color": discord.Color.dark_grey()}]
        created_roles = {}
        for r in roles_to_make:
            try: 
                perms = discord.Permissions(administrator=(r["name"] == "Admin"))
                created_roles[r["name"]] = await guild.create_role(name=r["name"], color=r["color"], permissions=perms, hoist=True)
                await asyncio.sleep(1)
            except: pass
                
        try: await ctx.author.add_roles(created_roles.get("Admin"))
        except: pass

        cat_info = await guild.create_category("📌 INFORMATION")
        await guild.create_text_channel("rules", category=cat_info)
        cat_chat = await guild.create_category("💬 CHAT")
        gen_chat = await guild.create_text_channel("general", category=cat_chat)
        bot_cmds = await guild.create_text_channel("bot-commands", category=cat_chat)
        ai_chat = await guild.create_text_channel("talk-to-ai", category=cat_chat)
        cat_voice = await guild.create_category("🔊 VOICE")
        await guild.create_voice_channel("General VC", category=cat_voice)

        if "Jailed" in created_roles:
            for cat in guild.categories:
                try: await cat.set_permissions(created_roles["Jailed"], read_messages=False, connect=False)
                except: pass

        db["config"]["cmd_channel"] = bot_cmds.id
        db["config"]["ai_channel"] = ai_chat.id
        db["config"]["event_channel"] = gen_chat.id
        save_db(db)
        
        await gen_chat.send(embed=discord.Embed(title="✅ Deployment Complete", description=f"{ctx.author.mention}, the server is fully operational.", color=discord.Color.green()))

    @commands.hybrid_command(name="masterlist", description="View all bot commands in an interactive panel.")
    async def masterlist(self, ctx):
        embeds = []
        e1 = discord.Embed(title="🤖 Masterlist: AI & Setup (Page 1/4)", color=discord.Color.blue())
        e1.add_field(name="/deployserver", value="Wipes and builds a modern server layout.", inline=False)
        e1.add_field(name="/aicommand", value="God-Mode AI python executor.", inline=False)
        e1.add_field(name="/define & /urban", value="AI-powered dictionaries.", inline=False)
        e1.add_field(name="/lore & /bossfight", value="AI generates interactive lore and UI bosses.", inline=False)
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
        e3.add_field(name="/shop & /buy", value="Dynamic million-coin UI artifact shop.", inline=False)
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

        view = PaginationView(ctx, embeds)
        await ctx.send(embed=embeds[0], view=view)

    # ==========================================
    # GOD-MODE & AI TOOLS
    # ==========================================
    @commands.hybrid_command(name='aicommand', description="Master AI brain. Execute any python code dynamically.")
    @commands.has_permissions(administrator=True)
    async def aicommand(self, ctx, *, instruction: str):
        if not self.client: 
            return await ctx.send(embed=discord.Embed(description="🤖 **AI is offline.**", color=discord.Color.red()))
        await ctx.defer()
        prompt = f"""You are an omnipotent Discord bot. The server owner has commanded: "{instruction}"
        Output a JSON array of actions: 1. Reply: {{"action": "reply", "message": "text"}} 2. Execute Python: {{"action": "execute", "code": "await ctx.send('Task complete!')"}}
        STRICT RULES: Output ONLY a valid JSON array. Write valid discord.py async code."""
        
        try:
            raw_response = await self.ask_groq([{"role": "user", "content": prompt}])
            start_idx = raw_response.find('[')
            end_idx = raw_response.rfind(']')
            clean_json = raw_response[start_idx:end_idx+1] if start_idx != -1 else raw_response.replace('```json', '').replace('```python', '').replace('```', '').strip()
            if clean_json.startswith('{'): clean_json = f"[{clean_json}]"
                    
            actions = json.loads(clean_json)
            for act in actions:
                if act.get("action") == "reply": 
                    await ctx.send(embed=discord.Embed(description=f"🤖 {act.get('message')}", color=discord.Color.blurple()))
                elif act.get("action") == "execute":
                    status_msg = await ctx.send(embed=discord.Embed(description="⚡ **Executing dynamic Python code...**", color=discord.Color.orange()))
                    try:
                        code_lines = act.get("code", "").split("\n")
                        wrapped_code = "async def __ai_exec():\n"
                        for line in code_lines: wrapped_code += f"    {line}\n"
                        exec_env = {'discord': discord, 'bot': self.bot, 'ctx': ctx, 'asyncio': asyncio, 'db': db}
                        exec(wrapped_code, exec_env)
                        await exec_env['__ai_exec']()
                        await status_msg.edit(embed=discord.Embed(description="✅ **AI Code Execution Successful!**", color=discord.Color.green()))
                    except Exception as err: 
                        await status_msg.edit(embed=discord.Embed(description=f"⚠️ **AI Execution Failed:**\n```py\n{err}\n```", color=discord.Color.red()))
        except Exception as e: 
            await ctx.send(embed=discord.Embed(description=f"❌ **Error parsing AI response:** {e}", color=discord.Color.red()))

    @commands.hybrid_command(name="bossfight", description="Start an interactive UI Boss Fight powered by AI.")
    async def bossfight(self, ctx):
        if not self.client: 
            return await ctx.send(embed=discord.Embed(description="❌ AI is offline. The Dungeon Master is sleeping.", color=discord.Color.red()))
        await ctx.defer()
        
        setup_prompt = "You are an epic Dungeon Master. Generate the absolute beginning of a dark fantasy boss fight. Describe the terrifying boss appearing before the player. Keep it under 150 words. Do NOT resolve the fight yet. End with the boss preparing to strike."
        chat_history = [
            {"role": "system", "content": "You are a ruthless Dungeon Master. The player will make choices. You must describe the outcome, damage taken, and environment. Keep responses under 100 words. Append '[CONTINUE]', '[WIN]', or '[LOSE]' at the end."},
            {"role": "user", "content": setup_prompt}
        ]
        
        try:
            scenario = await self.ask_groq(chat_history)
        except:
            return await ctx.send(embed=discord.Embed(description="❌ Failed to connect to AI Dungeon Master.", color=discord.Color.red()))

        chat_history.append({"role": "assistant", "content": scenario})
        view = AIBossFightView(ctx, self.client, chat_history)
        embed = discord.Embed(title="⚔️ BOSS ENCOUNTER", description=scenario, color=discord.Color.dark_red())
        embed.set_image(url="[https://media1.tenor.com/m/ZzR7vT1wS4gAAAAd/anime-fight.gif](https://media1.tenor.com/m/ZzR7vT1wS4gAAAAd/anime-fight.gif)")
        embed.set_footer(text="Choose your action below...")
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="define", description="AI powered dictionary definition.")
    async def define(self, ctx, word: str): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = await self.ask_groq([{"role": "user", "content": f"Give a precise dictionary definition for the word: '{word}'"}])
        await ctx.send(embed=discord.Embed(title=f"📖 Definition: {word.title()}", description=reply, color=discord.Color.dark_blue()))

    @commands.hybrid_command(name="urban", description="AI powered Urban Dictionary.")
    async def urban(self, ctx, word: str): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = await self.ask_groq([{"role": "user", "content": f"Give an internet slang 'Urban Dictionary' style definition for: '{word}'. Safe for work."}])
        await ctx.send(embed=discord.Embed(title=f"🏙️ Urban Dictionary: {word.title()}", description=reply, color=discord.Color.dark_green()))

    @commands.hybrid_command(name="forceevent", description="Force an hourly AI event instantly.")
    @commands.has_permissions(administrator=True)
    async def forceevent(self, ctx): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI is offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = await self.ask_groq([{"role": "user", "content": "Generate a modern Discord event or question to spark chat."}])
        await ctx.send(embed=discord.Embed(title="🌟 Forced Server Event", description=reply, color=discord.Color.blurple()))

    @commands.hybrid_command(name="tldr", description="AI summarizes the last 50 messages.")
    async def tldr(self, ctx): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        chat_log = "\n".join([m.content async for m in ctx.channel.history(limit=50) if m.content])
        reply = await self.ask_groq([{"role": "user", "content": f"Summarize this chat log briefly:\n{chat_log}"}])
        await ctx.send(embed=discord.Embed(title="📜 Chat TL;DR", description=reply, color=discord.Color.light_grey()))

    @commands.hybrid_command(name="roast_history", description="AI roasts a user based on their recent messages.")
    async def roast_history(self, ctx, member: discord.Member): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        chat_log = "\n".join([m.content async for m in ctx.channel.history(limit=25) if m.author == member and m.content])
        if not chat_log: return await ctx.send(embed=discord.Embed(description=f"I don't have enough recent messages from {member.name}.", color=discord.Color.red()))
        reply = await self.ask_groq([{"role": "user", "content": f"Brutally roast this user based strictly on their message history:\n{chat_log}"}])
        await ctx.send(embed=discord.Embed(title=f"🔥 AI Roast for {member.name}", description=reply, color=discord.Color.dark_orange()))

    @commands.hybrid_command(name="gothic_translate", description="Translates text into dark fantasy royal decree.")
    async def gothic_translate(self, ctx, *, text: str): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = await self.ask_groq([{"role": "user", "content": f"Rewrite the following text into dark, brooding gothic royal decree:\n{text}"}])
        await ctx.send(embed=discord.Embed(title="🦇 Gothic Translation", description=reply, color=discord.Color.purple()))

    @commands.hybrid_command(name="lore", description="AI generates an epic backstory for the server.")
    async def lore(self, ctx): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = await self.ask_groq([{"role": "user", "content": f"Write an epic dark fantasy backstory for the Discord server named {ctx.guild.name}."}])
        await ctx.send(embed=discord.Embed(title="📖 Server Lore", description=reply, color=discord.Color.dark_theme()))

    @commands.hybrid_command(name="debate", description="AI will argue against your topic.")
    async def debate(self, ctx, *, topic: str): 
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        await ctx.defer()
        reply = await self.ask_groq([
            {"role": "system", "content": "You are a master debater. Take the opposite stance of the user and passionately argue against them."}, 
            {"role": "user", "content": topic}
        ])
        await ctx.send(embed=discord.Embed(title=f"⚖️ Debating: {topic}", description=reply, color=discord.Color.dark_grey()))


    # ==========================================
    # ADVANCED MODERATION
    # ==========================================
    @commands.hybrid_command(name="tempban", description="Bans a user temporarily (in days).")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member, days: int, *, reason: str="Temp Ban"): 
        await member.ban(reason=reason)
        await ctx.send(embed=discord.Embed(title="🔨 User Temp-Banned", description=f"**{member.name}** has been banned for {days} days.\nReason: {reason}", color=discord.Color.red()))
        await asyncio.sleep(days * 86400)
        await ctx.guild.unban(member, reason="Tempban expired automatically.")

    @commands.hybrid_command(name="tempmute", description="Mutes a user for a specific duration in minutes.")
    @commands.has_permissions(moderate_members=True)
    async def tempmute(self, ctx, member: discord.Member, minutes: int, *, reason: str="Temp Mute"): 
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await ctx.send(embed=discord.Embed(title="🔇 User Muted", description=f"**{member.name}** has been timed out for {minutes} minutes.\nReason: {reason}", color=discord.Color.orange()))

    @commands.hybrid_command(name="slowmode", description="Sets slowmode for the current channel.")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int): 
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(embed=discord.Embed(description=f"⏱️ **Slowmode set to {seconds} seconds.**", color=discord.Color.blue()))

    @commands.hybrid_command(name="lockdown", description="Instantly locks all channels.")
    @commands.has_permissions(administrator=True)
    async def lockdown(self, ctx):
        await ctx.send(embed=discord.Embed(description="🚨 **SERVER LOCKDOWN INITIATED. Securing channels...**", color=discord.Color.red()))
        for c in ctx.guild.text_channels:
            try: await c.set_permissions(ctx.guild.default_role, send_messages=False)
            except: pass
        await ctx.send(embed=discord.Embed(description="🔒 **All channels have been locked down.**", color=discord.Color.dark_red()))

    @commands.hybrid_command(name="unlockdown", description="Reverses the lockdown.")
    @commands.has_permissions(administrator=True)
    async def unlockdown(self, ctx):
        await ctx.send(embed=discord.Embed(description="🔓 **SERVER LOCKDOWN LIFTED. Unlocking channels...**", color=discord.Color.green()))
        for c in ctx.guild.text_channels:
            try: await c.set_permissions(ctx.guild.default_role, send_messages=True)
            except: pass
        await ctx.send(embed=discord.Embed(description="✅ **All channels are now unlocked.**", color=discord.Color.dark_green()))

    @commands.hybrid_command(name="snipe", description="Recovers the last deleted message.")
    async def snipe(self, ctx):
        data = snipes.get(ctx.channel.id)
        if not data: 
            return await ctx.send(embed=discord.Embed(description="Nothing to snipe!", color=discord.Color.red()))
        embed = discord.Embed(description=data["content"], color=discord.Color.red())
        embed.set_author(name=data["author"], icon_url=data["avatar"])
        embed.set_footer(text="Message recovered via snipe.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="editsnipe", description="Shows the original text of an edited message.")
    async def editsnipe(self, ctx):
        data = edit_snipes.get(ctx.channel.id)
        if not data: 
            return await ctx.send(embed=discord.Embed(description="No recently edited messages found!", color=discord.Color.red()))
        embed = discord.Embed(title="Message Edited", color=discord.Color.orange())
        embed.set_author(name=data["author"])
        embed.add_field(name="Before", value=data["before"], inline=False)
        embed.add_field(name="After", value=data["after"], inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="purge", description="Deletes multiple messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int): 
        view = ConfirmView(ctx)
        msg = await ctx.send(embed=discord.Embed(description=f"⚠️ Are you sure you want to delete {amount} messages?", color=discord.Color.orange()), view=view)
        await view.wait()
        if not view.value: 
            return await msg.edit(embed=discord.Embed(description="🛑 Purge Cancelled.", color=discord.Color.grey()), view=None)
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(embed=discord.Embed(description=f"🧹 **Swept {amount} messages.**", color=discord.Color.green()), delete_after=4)

    @commands.hybrid_command(name="nuke", description="Clones and deletes the channel.")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx): 
        view = ConfirmView(ctx)
        msg = await ctx.send(embed=discord.Embed(title="☢️ TACTICAL NUKE", description="Are you absolutely sure you want to nuke this channel? It cannot be undone.", color=discord.Color.red()), view=view)
        await view.wait()
        if not view.value: 
            return await msg.edit(embed=discord.Embed(description="🛑 Nuke Cancelled.", color=discord.Color.grey()), view=None)
        
        pos = ctx.channel.position
        nc = await ctx.channel.clone()
        await ctx.channel.delete()
        await nc.edit(position=pos)
        
        embed = discord.Embed(description="☢️ **TACTICAL NUKE DEPLOYED!** 💥\nChannel has been wiped.", color=discord.Color.dark_red())
        embed.set_image(url="[https://media1.tenor.com/m/1_bY-sZ_4nQAAAAd/nuke.gif](https://media1.tenor.com/m/1_bY-sZ_4nQAAAAd/nuke.gif)")
        await nc.send(embed=embed)

    @commands.hybrid_command(name="kick", description="Kicks a user.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str="Caught lacking"): 
        await member.kick(reason=reason)
        await ctx.send(embed=discord.Embed(description=f"👢 **{member.name} was kicked.** Reason: {reason}", color=discord.Color.red()))

    @commands.hybrid_command(name="ban", description="Bans a user.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str="Banned by Admin"): 
        await member.ban(reason=reason)
        await ctx.send(embed=discord.Embed(description=f"🔨 **{member.name} has been permanently banned.**", color=discord.Color.dark_red()))

    @commands.hybrid_command(name="warn", description="Warns a user.")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str="Rule Violation"): 
        uid = str(member.id)
        if uid not in db["warns"]: db["warns"][uid] = []
        db["warns"][uid].append(reason)
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⚠️ **{member.mention} has been warned.** Reason: {reason}", color=discord.Color.yellow()))

    @commands.hybrid_command(name="warnings", description="Shows a user's warnings.")
    async def warnings(self, ctx, member: discord.Member): 
        warns = db["warns"].get(str(member.id), [])
        if not warns: 
            return await ctx.send(embed=discord.Embed(description=f"✅ **{member.name} has a clean record.**", color=discord.Color.green()))
        embed = discord.Embed(title=f"⚠️ Warnings for {member.name}", color=discord.Color.orange())
        for i, w in enumerate(warns):
            embed.add_field(name=f"Warning {i+1}", value=w, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarns", description="Clears all warnings for a user.")
    @commands.has_permissions(administrator=True)
    async def clearwarns(self, ctx, member: discord.Member): 
        view = ConfirmView(ctx)
        msg = await ctx.send(embed=discord.Embed(description=f"⚠️ Are you sure you want to clear all warnings for {member.name}?", color=discord.Color.orange()), view=view)
        await view.wait()
        if not view.value: 
            return await msg.edit(embed=discord.Embed(description="🛑 Cancelled.", color=discord.Color.grey()), view=None)
        
        if str(member.id) in db["warns"]:
            del db["warns"][str(member.id)]
            save_db(db)
            await msg.edit(embed=discord.Embed(description=f"🗑️ **Cleared all warnings for {member.name}.**", color=discord.Color.green()), view=None)
        else:
            await msg.edit(embed=discord.Embed(description="User has no warnings.", color=discord.Color.grey()), view=None)

    @commands.hybrid_command(name="jail", description="Strips roles and locks user in jail.")
    @commands.has_permissions(administrator=True)
    async def jail(self, ctx, member: discord.Member):
        db["jailed"][str(member.id)] = [r.id for r in member.roles if r.id != ctx.guild.default_role.id]
        save_db(db)
        for r in member.roles[1:]:
            try: await member.remove_roles(r)
            except: pass
                
        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jail_role: 
            await member.add_roles(jail_role)
            await ctx.send(embed=discord.Embed(description=f"⛓️ **{member.mention} has been locked up in federal prison.**", color=discord.Color.dark_grey()))
        else:
            await ctx.send(embed=discord.Embed(description="⚠️ 'Jailed' role does not exist. Please run `/deployserver` or create it.", color=discord.Color.red()))

    @commands.hybrid_command(name="unjail", description="Releases user from jail and restores roles.")
    @commands.has_permissions(administrator=True)
    async def unjail(self, ctx, member: discord.Member):
        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jail_role and jail_role in member.roles: 
            await member.remove_roles(jail_role)
            
        old_roles = db["jailed"].pop(str(member.id), [])
        for r_id in old_roles:
            role = ctx.guild.get_role(r_id)
            if role: 
                try: await member.add_roles(role)
                except: pass
                
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🔓 **{member.mention} made bail and is released.**", color=discord.Color.green()))

    # ==========================================
    # RPG, ECONOMY & ANIMATED GIF EVENTS
    # ==========================================
    @commands.hybrid_command(name="shop", description="View the interactive rotating Legendary Shop.")
    async def shop(self, ctx): 
        items = db.get("current_shop", [])
        if not items:
            return await ctx.send(embed=discord.Embed(description="🛒 The merchant is currently traveling. The shop will restock soon.", color=discord.Color.dark_grey()))
            
        embed = discord.Embed(title="🛒 The Mystic Merchant", description="The shop restocks randomly every 60 minutes.\nClick the buttons below to purchase an artifact.", color=discord.Color.gold())
        for item in items:
            embed.add_field(name=f"✨ {item['name']}", value=f"**Price:** {item['price']:,} Coins\n*{item['desc']}*", inline=False)
            
        view = DynamicShopView(items)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="inventory", description="Check your legendary items.")
    async def inventory(self, ctx): 
        uid = str(ctx.author.id)
        items = db.get("inventory", {}).get(uid, [])
        if not items:
            return await ctx.send(embed=discord.Embed(title=f"🎒 {ctx.author.name}'s Relics", description="Inventory is empty.", color=discord.Color.blue()))

        chunks = [items[i:i + 10] for i in range(0, len(items), 10)]
        embeds = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(title=f"🎒 {ctx.author.name}'s Relics (Page {i+1}/{len(chunks)})", description="\n".join([f"- {item}" for item in chunk]), color=discord.Color.blue())
            embeds.append(embed)
            
        view = PaginationView(ctx, embeds)
        await ctx.send(embed=embeds[0], view=view)

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

    @commands.hybrid_command(name="weekly", description="Claim weekly coins.")
    @commands.cooldown(1, 604800, commands.BucketType.user)
    async def weekly(self, ctx): 
        uid = str(ctx.author.id)
        db["economy"][uid] = db["economy"].get(uid, 0) + 5000000
        save_db(db)
        await ctx.send(embed=discord.Embed(description="💎 **You claimed your massive 5,000,000 weekly coins!**", color=discord.Color.purple()))

    @commands.hybrid_command(name="work", description="Work for coins.")
    @commands.cooldown(1, 3600, commands.BucketType.user) 
    async def work(self, ctx): 
        earned = random.randint(50000, 150000)
        uid = str(ctx.author.id)
        db["economy"][uid] = db["economy"].get(uid, 0) + earned
        save_db(db)
        embed = discord.Embed(description=f"💼 **You worked a grueling shift and earned {earned:,} coins!**", color=discord.Color.green())
        embed.set_image(url="[https://media1.tenor.com/m/3_4X3Y0_45wAAAAd/anime-work.gif](https://media1.tenor.com/m/3_4X3Y0_45wAAAAd/anime-work.gif)")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="crime", description="Commit a crime for coins (risky).")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def crime(self, ctx):
        uid = str(ctx.author.id)
        if random.choice([True, False]): 
            earned = random.randint(100000, 400000)
            db["economy"][uid] = db["economy"].get(uid, 0) + earned
            embed = discord.Embed(description=f"🥷 **You hacked the mainframe and stole {earned:,} coins!**", color=discord.Color.purple())
            embed.set_image(url="[https://media1.tenor.com/m/2XyX9C4kG0QAAAAd/anime-thief.gif](https://media1.tenor.com/m/2XyX9C4kG0QAAAAd/anime-thief.gif)")
        else: 
            lost = random.randint(50000, 150000)
            db["economy"][uid] = max(0, db["economy"].get(uid, 0) - lost)
            embed = discord.Embed(description=f"🚓 **The feds caught you! Batman arrived. You paid a fine of {lost:,} coins.**", color=discord.Color.red())
            embed.set_image(url="[https://media1.tenor.com/m/X6o2gV1kO18AAAAd/batman-the-batman.gif](https://media1.tenor.com/m/X6o2gV1kO18AAAAd/batman-the-batman.gif)")
        save_db(db)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rob", description="Steal from another user.")
    @commands.cooldown(1, 7200, commands.BucketType.user)
    async def rob(self, ctx, member: discord.Member):
        uid = str(ctx.author.id)
        tid = str(member.id)
        if db["economy"].get(tid, 0) < 100000: 
            return await ctx.send(embed=discord.Embed(description=f"❌ **{member.name} is too poor to rob. Leave them alone!**", color=discord.Color.red()))
            
        if random.choice([True, False]): 
            stolen = random.randint(50000, int(db["economy"][tid] * 0.25))
            db["economy"][tid] -= stolen
            db["economy"][uid] = db["economy"].get(uid, 0) + stolen
            embed = discord.Embed(description=f"🔫 **You mugged {member.name} and stole {stolen:,} coins!**", color=discord.Color.green())
            embed.set_image(url="[https://media1.tenor.com/m/ZzR7vT1wS4gAAAAd/anime-steal.gif](https://media1.tenor.com/m/ZzR7vT1wS4gAAAAd/anime-steal.gif)")
        else: 
            fine = 100000
            db["economy"][uid] = max(0, db["economy"].get(uid, 0) - fine)
            embed = discord.Embed(description=f"🛡️ **{member.name} fought back! You paid a {fine:,} coin hospital bill.**", color=discord.Color.dark_red())
            embed.set_image(url="[https://media1.tenor.com/m/2Y4Z8v3_45wAAAAd/anime-slap.gif](https://media1.tenor.com/m/2Y4Z8v3_45wAAAAd/anime-slap.gif)")
        save_db(db)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="heist", description="Start a bank heist event.")
    @commands.cooldown(1, 14400, commands.BucketType.guild)
    async def heist(self, ctx): 
        payout = random.randint(1000000, 5000000)
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + payout
        save_db(db)
        embed = discord.Embed(title="🏦 BANK HEIST SUCCESSFUL!", description=f"You blew the vault and escaped with **{payout:,} coins!**", color=discord.Color.gold())
        embed.set_image(url="[https://media1.tenor.com/m/1_bY-sZ_4nQAAAAd/money-heist.gif](https://media1.tenor.com/m/1_bY-sZ_4nQAAAAd/money-heist.gif)")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="slots", description="Animated virtual slot machine for millionaires.")
    async def slots(self, ctx, bet: int):
        uid = str(ctx.author.id)
        
        if bet < 100:
            return await ctx.send(embed=discord.Embed(description="❌ **Minimum bet is 100 coins.**", color=discord.Color.red()))
        if db["economy"].get(uid, 0) < bet: 
            return await ctx.send(embed=discord.Embed(description=f"❌ **You don't have enough coins. You need {bet:,}.**", color=discord.Color.red()))
            
        db["economy"][uid] -= bet
        save_db(db)
        
        embed = discord.Embed(title="🎰 SLOTS 🎰", description="**Spinning the reels...**\nGood luck!", color=discord.Color.dark_theme())
        embed.set_image(url="[https://media1.tenor.com/m/x8v1oNUOmg4AAAAd/slot-machine.gif](https://media1.tenor.com/m/x8v1oNUOmg4AAAAd/slot-machine.gif)")
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
        msg = await ctx.send(embed=embed)
        
        reels = ["🍒", "🍋", "💎", "⭐", "🔔", "🍇"]
        r1, r2, r3 = random.choice(reels), random.choice(reels), random.choice(reels)
        final_slots = f"**[ {r1} | {r2} | {r3} ]**"
        
        await asyncio.sleep(2.5) 
        
        if r1 == r2 == r3: 
            winnings = bet * 10
            db["economy"][uid] += winnings
            embed.color = discord.Color.gold()
            embed.description = f"{final_slots}\n\n🎉 **JACKPOT!** You won **{winnings:,} coins!**"
            embed.set_image(url="[https://media1.tenor.com/m/1GvK0ZWe3gAAAAAd/hakari-dance.gif](https://media1.tenor.com/m/1GvK0ZWe3gAAAAAd/hakari-dance.gif)")
        elif r1 == r2 or r2 == r3 or r1 == r3: 
            winnings = int(bet * 1.5)
            db["economy"][uid] += winnings
            embed.color = discord.Color.green()
            embed.description = f"{final_slots}\n\n✨ **Small Win!** You got **{winnings:,} coins!**"
            embed.set_image(url="[https://media1.tenor.com/m/YwWz2U_1_4YAAAAd/anime-money.gif](https://media1.tenor.com/m/YwWz2U_1_4YAAAAd/anime-money.gif)")
        else: 
            embed.color = discord.Color.red()
            embed.description = f"{final_slots}\n\n💥 **You lost.** Better luck next time."
            embed.set_image(url="[https://media1.tenor.com/m/q_D7-XQd5vMAAAAd/anime-cry.gif](https://media1.tenor.com/m/q_D7-XQd5vMAAAAd/anime-cry.gif)")
            
        save_db(db)
        embed.set_footer(text=f"New Balance: {db['economy'][uid]:,} coins")
        await msg.edit(embed=embed)

    @commands.hybrid_command(name="blackjack", description="Play 21 against the bot.")
    async def blackjack(self, ctx, bet: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: 
            return await ctx.send(embed=discord.Embed(description="❌ **Not enough coins.**", color=discord.Color.red()))
            
        db["economy"][uid] -= bet
        player_score = random.randint(15, 25)
        bot_score = random.randint(17, 23)
        
        embed = discord.Embed(color=discord.Color.gold())
        if player_score > 21: 
            embed.description = f"🃏 **Bust!** You drew {player_score}. Bot had {bot_score}. You lose."
            embed.color = discord.Color.red()
        elif player_score > bot_score or bot_score > 21: 
            db["economy"][uid] += bet * 2
            embed.description = f"🃏 **You Win!** You drew {player_score}! Bot drew {bot_score}. Payout: **{bet*2:,} coins!**"
            embed.color = discord.Color.green()
            embed.set_image(url="[https://media1.tenor.com/m/9O3X3Y0O74cAAAAd/kakegurui-anime.gif](https://media1.tenor.com/m/9O3X3Y0O74cAAAAd/kakegurui-anime.gif)")
        else: 
            embed.description = f"🃏 **Bot Wins.** Bot drew {bot_score}. You had {player_score}. You lose."
            embed.color = discord.Color.red()
            
        save_db(db)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="coinflip", description="Gamble 50/50.")
    async def coinflip(self, ctx, bet: int, choice: str):
        if choice.lower() not in ["heads", "tails"]: 
            return await ctx.send(embed=discord.Embed(description="❌ **Please choose 'heads' or 'tails'.**", color=discord.Color.red()))
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: 
            return await ctx.send(embed=discord.Embed(description="❌ **Not enough coins.**", color=discord.Color.red()))
            
        db["economy"][uid] -= bet
        result = random.choice(["heads", "tails"])
        
        embed = discord.Embed()
        if choice.lower() == result: 
            db["economy"][uid] += bet * 2
            embed.description = f"🪙 **It landed on {result.capitalize()}!** You won **{bet*2:,} coins!**"
            embed.color = discord.Color.green()
            embed.set_image(url="[https://media1.tenor.com/m/9O3X3Y0O74cAAAAd/kakegurui-anime.gif](https://media1.tenor.com/m/9O3X3Y0O74cAAAAd/kakegurui-anime.gif)")
        else: 
            embed.description = f"🪙 **It landed on {result.capitalize()}.** You lost."
            embed.color = discord.Color.red()
            
        save_db(db)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="give", description="Give coins to another user.")
    async def give(self, ctx, member: discord.Member, amount: int):
        uid = str(ctx.author.id)
        tid = str(member.id)
        if db["economy"].get(uid, 0) < amount or amount <= 0: 
            return await ctx.send(embed=discord.Embed(description="❌ **Insufficient funds.**", color=discord.Color.red()))
            
        db["economy"][uid] -= amount
        db["economy"][tid] = db["economy"].get(tid, 0) + amount
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"💸 **You gave {member.name} {amount:,} coins.**", color=discord.Color.green()))

    @commands.hybrid_command(name="rich", description="View the richest players.")
    async def rich(self, ctx): 
        sorted_eco = sorted(db["economy"].items(), key=lambda x: x[1], reverse=True)
        if not sorted_eco: 
            return await ctx.send("No economy data.")
        
        chunks = [sorted_eco[i:i + 10] for i in range(0, len(sorted_eco), 10)]
        embeds = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(title=f"🏆 Richest Citizens (Page {i+1}/{len(chunks)})", color=discord.Color.gold())
            for j, (uid, amt) in enumerate(chunk):
                embed.add_field(name=f"#{i*10 + j + 1}", value=f"<@{uid}>: **{amt:,}** coins", inline=False)
            embeds.append(embed)
            
        view = PaginationView(ctx, embeds)
        await ctx.send(embed=embeds[0], view=view)

    @commands.hybrid_command(name="fish", description="Cast a line and catch fish.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def fish(self, ctx): 
        fish_types = ["Old Boot", "Common Carp", "Rare Salmon", "Legendary Shark"]
        fish = random.choice(fish_types)
        reward = {"Old Boot": 0, "Common Carp": 5000, "Rare Salmon": 20000, "Legendary Shark": 100000}[fish]
        
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🎣 **You cast your line and caught a {fish}!** Sold for {reward:,} coins.", color=discord.Color.blue()))

    @commands.hybrid_command(name="hunt", description="Hunt animals or monsters.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def hunt(self, ctx): 
        mobs = ["Mutant Rat", "Forest Goblin", "Shadow Dragon"]
        mob = random.choice(mobs)
        reward = {"Mutant Rat": 2000, "Forest Goblin": 15000, "Shadow Dragon": 150000}[mob]
        
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🏹 **You ventured into the woods and slayed a {mob}!** Claimed {reward:,} coins.", color=discord.Color.dark_green()))

    @commands.hybrid_command(name="mine", description="Mine for ores.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def mine(self, ctx): 
        ores = ["Stone", "Iron Ore", "Raw Diamond"]
        ore = random.choice(ores)
        reward = {"Stone": 500, "Iron Ore": 8000, "Raw Diamond": 120000}[ore]
        
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⛏️ **You swung your pickaxe and mined {ore}!** Sold for {reward:,} coins.", color=discord.Color.light_grey()))

    @commands.hybrid_command(name="quest", description="Go on an RPG quest.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def quest(self, ctx):
        uid = str(ctx.author.id)
        if uid not in db["levels"]: 
            db["levels"][uid] = {"xp": 0, "level": 1}
            
        current_lvl = db["levels"][uid]["level"]
        if current_lvl >= 13000: 
            return await ctx.send(embed=discord.Embed(description="🛑 **Max Level 13,000 Reached!** You are already a god. The quests offer you nothing.", color=discord.Color.red()))
            
        xp_gain = random.randint(300, 800)
        db["levels"][uid]["xp"] += xp_gain
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🗡️ **You completed a dangerous dungeon run!** Earned **{xp_gain} XP**! (Level: {current_lvl})", color=discord.Color.orange()))

    @commands.hybrid_command(name="trade", description="Trade items securely.")
    async def trade(self, ctx, member: discord.Member, item: str):
        uid = str(ctx.author.id)
        tid = str(member.id)
        item = item.lower()
        
        if item not in db.get("inventory", {}).get(uid, []): 
            return await ctx.send(embed=discord.Embed(description="❌ **You do not own this item.**", color=discord.Color.red()))
            
        if tid not in db["inventory"]: 
            db["inventory"][tid] = []
            
        db["inventory"][uid].remove(item)
        db["inventory"][tid].append(item)
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🤝 **You successfully traded your {item.title()} to {member.name}.**", color=discord.Color.green()))

    @commands.hybrid_command(name="bounty", description="Put a coin bounty on a user's head.")
    async def bounty(self, ctx, member: discord.Member, amount: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < amount or amount <= 0: 
            return await ctx.send(embed=discord.Embed(description="❌ **Not enough coins to set this bounty.**", color=discord.Color.red()))
            
        db["economy"][uid] -= amount
        db["bounties"][str(member.id)] = db.get("bounties", {}).get(str(member.id), 0) + amount
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"💀 **Bounty Placed!** You put a **{amount:,} coin** bounty on {member.name}'s head!", color=discord.Color.dark_red()))

    @commands.hybrid_command(name="claimbounty", description="Claim a bounty.")
    async def claimbounty(self, ctx, member: discord.Member):
        uid = str(ctx.author.id)
        tid = str(member.id)
        bounty_amount = db.get("bounties", {}).get(tid, 0)
        
        if bounty_amount <= 0: 
            return await ctx.send(embed=discord.Embed(description="❌ **That user does not have a bounty on their head.**", color=discord.Color.red()))
            
        db["bounties"][tid] = 0
        db["economy"][uid] = db["economy"].get(uid, 0) + bounty_amount
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🔪 **Bounty Claimed!** You hunted down {member.name} and collected the **{bounty_amount:,} coin** reward!", color=discord.Color.dark_red()))

    # ==========================================
    # LEVELING, REPUTATION & UTILITY
    # ==========================================
    @commands.hybrid_command(name="rank", description="Check XP Level.")
    async def rank(self, ctx, member: discord.Member = None): 
        target = member or ctx.author
        uid = str(target.id)
        lvl_data = db["levels"].get(uid, {"xp": 0, "level": 1})
        embed = discord.Embed(title=f"Rank: {target.name}", description=f"⭐ Level: **{lvl_data['level']}**\n✨ XP: **{lvl_data['xp']}**", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard_levels", description="Top highest levels.")
    async def leaderboard_levels(self, ctx): 
        sorted_lvls = sorted(db.get("levels", {}).items(), key=lambda x: x[1]["level"], reverse=True)
        if not sorted_lvls: return await ctx.send("No level data.")
        
        chunks = [sorted_lvls[i:i + 10] for i in range(0, len(sorted_lvls), 10)]
        embeds = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(title=f"🏆 Level Leaderboard (Page {i+1}/{len(chunks)})", color=discord.Color.gold())
            for j, (uid, data) in enumerate(chunk):
                embed.add_field(name=f"#{i*10 + j + 1}", value=f"<@{uid}> - Lvl {data['level']}", inline=False)
            embeds.append(embed)
            
        view = PaginationView(ctx, embeds)
        await ctx.send(embed=embeds[0], view=view)

    @commands.hybrid_command(name="leaderboard_rep", description="Top reputation.")
    async def leaderboard_rep(self, ctx): 
        sorted_rep = sorted(db.get("rep", {}).items(), key=lambda x: x[1], reverse=True)
        if not sorted_rep: return await ctx.send("No reputation data.")
        
        chunks = [sorted_rep[i:i + 10] for i in range(0, len(sorted_rep), 10)]
        embeds = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(title=f"👍 Most Reputable Citizens (Page {i+1}/{len(chunks)})", color=discord.Color.green())
            for j, (uid, amt) in enumerate(chunk):
                embed.add_field(name=f"#{i*10 + j + 1}", value=f"<@{uid}> - {amt} Rep", inline=False)
            embeds.append(embed)
            
        view = PaginationView(ctx, embeds)
        await ctx.send(embed=embeds[0], view=view)

    @commands.hybrid_command(name="givexp", description="Admin command to grant XP.")
    @commands.has_permissions(administrator=True)
    async def givexp(self, ctx, member: discord.Member, amount: int): 
        uid = str(member.id)
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["xp"] += amount
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"📈 **Granted {amount} XP to {member.name}.**", color=discord.Color.green()))

    @commands.hybrid_command(name="removexp", description="Admin command to remove XP.")
    @commands.has_permissions(administrator=True)
    async def removexp(self, ctx, member: discord.Member, amount: int): 
        uid = str(member.id)
        if uid in db["levels"]: 
            db["levels"][uid]["xp"] = max(0, db["levels"][uid]["xp"] - amount)
            save_db(db)
        await ctx.send(embed=discord.Embed(description=f"📉 **Removed {amount} XP from {member.name}.**", color=discord.Color.red()))

    @commands.hybrid_command(name="setlevel", description="Admin force set level.")
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, member: discord.Member, level: int): 
        uid = str(member.id)
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["level"] = level
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⭐ **Force set {member.name} to Level {level}.**", color=discord.Color.gold()))

    @commands.hybrid_command(name="rewards", description="View level role rewards.")
    async def rewards(self, ctx): 
        embed = discord.Embed(title="🎁 Level Rewards", color=discord.Color.green())
        embed.add_field(name="Level 10", value="Trusted Role", inline=False)
        embed.add_field(name="Level 50", value="Ronin Role", inline=False)
        embed.add_field(name="Level 100", value="God Tier Role", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rep", description="Give reputation to someone.")
    async def rep(self, ctx, member: discord.Member):
        if member.id == ctx.author.id: 
            return await ctx.send(embed=discord.Embed(description="❌ You cannot give reputation to yourself.", color=discord.Color.red()))
        uid = str(member.id)
        if "rep" not in db: db["rep"] = {}
        db["rep"][uid] = db["rep"].get(uid, 0) + 1
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"👍 **You gave +1 Reputation to {member.name}.** They now have {db['rep'][uid]} Rep.", color=discord.Color.green()))

    @commands.hybrid_command(name="poll", description="Create a reaction poll.")
    async def poll(self, ctx, question: str): 
        embed = discord.Embed(title="📊 Server Poll", description=question, color=discord.Color.green())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    @commands.hybrid_command(name="giveaway_start", description="Start a giveaway.")
    @commands.has_permissions(manage_messages=True)
    async def giveaway_start(self, ctx, prize: str): 
        embed = discord.Embed(title=f"🎉 GIVEAWAY: {prize} 🎉", description="React with 🎉 to enter!", color=discord.Color.gold())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("🎉")

    @commands.hybrid_command(name="giveaway_reroll", description="Reroll a giveaway winner.")
    @commands.has_permissions(manage_messages=True)
    async def giveaway_reroll(self, ctx): 
        await ctx.send(embed=discord.Embed(description="🎉 **Giveaway rerolled!** (Event listener placeholder)", color=discord.Color.gold()))

    @commands.hybrid_command(name="ticket_setup", description="Setup support tickets.")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx): 
        await ctx.send(embed=discord.Embed(description="🎫 **Support Tickets initialized.** (Button UI placeholder)", color=discord.Color.blue()))

    @commands.hybrid_command(name="ticket_close", description="Closes a ticket channel.")
    @commands.has_permissions(manage_channels=True)
    async def ticket_close(self, ctx): 
        await ctx.send(embed=discord.Embed(description="Closing ticket...", color=discord.Color.red()))
        await asyncio.sleep(2)
        await ctx.channel.delete()

    @commands.hybrid_command(name="remindme", description="Set a reminder.")
    async def remindme(self, ctx, seconds: int, *, message: str): 
        await ctx.send(embed=discord.Embed(description=f"⏰ **Reminder set for {seconds} seconds.**", color=discord.Color.blue()))
        await asyncio.sleep(seconds)
        await ctx.author.send(embed=discord.Embed(title="⏰ Reminder", description=message, color=discord.Color.gold()))

    @commands.hybrid_command(name="afk", description="Set AFK status.")
    async def afk(self, ctx, *, reason: str="AFK"): 
        db["afk"][str(ctx.author.id)] = reason
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"💤 **{ctx.author.mention} is now AFK.** Reason: {reason}", color=discord.Color.dark_grey()))

    @commands.hybrid_command(name="weather", description="Check weather data.")
    async def weather(self, ctx, city: str): 
        await ctx.send(embed=discord.Embed(description=f"🌤️ **Weather in {city.title()}:** Sunny, 75°F (Simulated API).", color=discord.Color.blue()))

    @commands.hybrid_command(name="calc", description="Built-in calculator.")
    async def calc(self, ctx, expression: str):
        try: 
            result = eval(expression, {'__builtins__': None}, {})
            await ctx.send(embed=discord.Embed(description=f"🧮 **Result:** `{result}`", color=discord.Color.green()))
        except: 
            await ctx.send(embed=discord.Embed(description="❌ **Invalid math expression.**", color=discord.Color.red()))

    @commands.hybrid_command(name="translate", description="Translate text.")
    async def translate(self, ctx, language: str, *, text: str): 
        await ctx.send(embed=discord.Embed(description=f"🌐 **Translated to {language.title()}:** *{text}* (Simulated API).", color=discord.Color.teal()))

    @commands.hybrid_command(name="userhistory", description="Check user history stats.")
    async def userhistory(self, ctx, member: discord.Member): 
        embed = discord.Embed(title=f"History for {member.name}", color=discord.Color.blue())
        embed.add_field(name="Joined Server", value=member.joined_at.strftime('%Y-%m-%d %H:%M'), inline=False)
        embed.add_field(name="Account Created", value=member.created_at.strftime('%Y-%m-%d %H:%M'), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="roleinfo", description="Check role info.")
    async def roleinfo(self, ctx, role: discord.Role): 
        embed = discord.Embed(title=f"Role Info: {role.name}", color=role.color)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="ID", value=str(role.id), inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="servericon", description="Get high-res server icon.")
    async def servericon(self, ctx): 
        if ctx.guild.icon:
            await ctx.send(ctx.guild.icon.url)
        else:
            await ctx.send(embed=discord.Embed(description="This server has no icon.", color=discord.Color.grey()))

    @commands.hybrid_command(name="ping", description="Check bot latency.")
    async def ping(self, ctx): 
        await ctx.send(embed=discord.Embed(description=f"🏓 **Pong!** {round(self.bot.latency * 1000)}ms", color=discord.Color.blurple()))

    @commands.hybrid_command(name="avatar", description="Get user PFP.")
    async def avatar(self, ctx, member: discord.Member = None): 
        target = member or ctx.author
        embed = discord.Embed(title=f"{target.name}'s Avatar", color=discord.Color.blue())
        embed.set_image(url=target.avatar.url if target.avatar else target.default_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="View server stats.")
    async def serverinfo(self, ctx):
        embed = discord.Embed(title=f"Server Info - {ctx.guild.name}", color=discord.Color.gold())
        embed.add_field(name="👑 Owner", value=ctx.guild.owner.mention, inline=True)
        embed.add_field(name="👥 Members", value=ctx.guild.member_count, inline=True)
        embed.add_field(name="📁 Channels", value=len(ctx.guild.channels), inline=True)
        await ctx.send(embed=embed)

    # ==========================================
    # 🤡 FUN, TROLLING & ANIME (PREFIX COMMANDS)
    # ==========================================
    @commands.command(name="fakeban")
    async def fakeban(self, ctx, member: discord.Member): 
        embed = discord.Embed(title="User Banned", description=f"🔨 **{member.name}** has been permanently banned from the server.\n\n*Reason: Caught lacking.*", color=discord.Color.red())
        embed.set_image(url="[https://media1.tenor.com/m/2Y4Z8v3_45wAAAAd/anime-ban.gif](https://media1.tenor.com/m/2Y4Z8v3_45wAAAAd/anime-ban.gif)")
        await ctx.send(embed=embed)

    @commands.command(name="rickroll")
    async def rickroll(self, ctx, member: discord.Member):
        try: 
            await member.send("🎁 **You have been gifted Discord Nitro!** Claim it here: [https://www.youtube.com/watch?v=dQw4w9WgXcQ](https://www.youtube.com/watch?v=dQw4w9WgXcQ)")
            await ctx.send(embed=discord.Embed(description=f"🤫 **Successfully sent a disguised package to {member.name}.**", color=discord.Color.green()))
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

    @commands.command(name="susmeter")
    async def susmeter(self, ctx, member: discord.Member=None): 
        target = member or ctx.author
        await ctx.send(embed=discord.Embed(description=f"📮 **{target.name}** is **{random.randint(0,100)}%** sus.", color=discord.Color.dark_grey()))

    @commands.command(name="roast")
    async def roast(self, ctx, member: discord.Member):
        roasts = [
            "You're like a cloud. When you disappear, it's a beautiful day.", 
            "I'd agree with you but then we’d both be wrong.",
            "If laughter is the best medicine, your face must be curing the world."
        ]
        await ctx.send(embed=discord.Embed(description=f"{member.mention} 🔥 {random.choice(roasts)}", color=discord.Color.dark_orange()))

    @commands.command(name="compliment")
    async def compliment(self, ctx, member: discord.Member):
        comps = [
            "You have a great sense of humor!", 
            "You light up the room!",
            "You are glowing today."
        ]
        await ctx.send(embed=discord.Embed(description=f"💖 {member.mention} {random.choice(comps)}", color=discord.Color.pink()))

    @commands.command(name="confess")
    async def confess(self, ctx, *, message: str): 
        try:
            await ctx.message.delete()
        except:
            pass
        embed = discord.Embed(title="🤫 Anonymous Confession", description=message, color=discord.Color.dark_theme())
        await ctx.send(embed=embed)

    @commands.command(name="kill")
    async def kill(self, ctx, member: discord.Member):
        deaths = [
            "fell out of the world.", 
            "was obliterated by a rogue AI.", 
            "was crushed by a falling anvil."
        ]
        await ctx.send(embed=discord.Embed(description=f"☠️ **{member.name}** {random.choice(deaths)}", color=discord.Color.dark_red()))

    @commands.command(name="revive")
    async def revive(self, ctx, member: discord.Member): 
        await ctx.send(embed=discord.Embed(description=f"👼 **{member.name} has been resurrected from the dead!**", color=discord.Color.gold()))

    @commands.command(name="meme")
    async def meme(self, ctx): 
        await ctx.send("😂 *Imagine a really funny, high-quality meme right here.* (API integration placeholder)")

    @commands.command(name="dadjoke")
    async def dadjoke(self, ctx):
        jokes = [
            "I'm afraid for the calendar. Its days are numbered.", 
            "Why do fathers take an extra pair of socks when they go golfing? In case they get a hole in one!",
            "I thought the dryer was shrinking my clothes. Turns out it was the refrigerator."
        ]
        await ctx.send(embed=discord.Embed(description=f"🧔 **Dad Joke:** {random.choice(jokes)}", color=discord.Color.blue()))

    @commands.command(name="choose")
    async def choose(self, ctx, option1: str, option2: str): 
        await ctx.send(embed=discord.Embed(description=f"🤔 **I choose...** `{random.choice([option1, option2])}`", color=discord.Color.teal()))

    @commands.command(name="spank")
    async def spank(self, ctx, member: discord.Member): 
        await ctx.send(embed=discord.Embed(description=f"🤚 **{ctx.author.name} viciously spanked {member.name}!**", color=discord.Color.dark_orange()))

    @commands.command(name="jailbreak")
    async def jailbreak(self, ctx, member: discord.Member):
        if random.randint(1, 10) <= 2: 
            jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
            if jail_role and jail_role in member.roles: 
                await member.remove_roles(jail_role)
                await ctx.send(embed=discord.Embed(description=f"🔓 **SUCCESS!** {ctx.author.name} broke {member.name} out of federal prison!", color=discord.Color.green()))
            else:
                await ctx.send(embed=discord.Embed(description=f"⚠️ {member.name} isn't in jail!", color=discord.Color.orange()))
        else: 
            await ctx.send(embed=discord.Embed(description="❌ **Jailbreak failed.** The guards caught you trying to sneak in.", color=discord.Color.red()))

    @commands.command(name="eightball")
    async def eightball(self, ctx, *, question: str): 
        res = random.choice(["Yes, definitely.", "No.", "Maybe.", "Definitely not.", "Without a doubt.", "Ask again later."])
        embed = discord.Embed(title="🎱 Magic 8-Ball", color=discord.Color.dark_grey())
        embed.add_field(name="Question:", value=question, inline=False)
        embed.add_field(name="Answer:", value=res, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="hack")
    async def hack(self, ctx, member: discord.Member): 
        msg = await ctx.send(embed=discord.Embed(description=f"💻 **Hacking {member.name}...**", color=discord.Color.dark_grey()))
        await asyncio.sleep(2)
        await msg.edit(embed=discord.Embed(description="🕵️‍♂️ Finding IP Address...", color=discord.Color.dark_grey()))
        await asyncio.sleep(2)
        await msg.edit(embed=discord.Embed(description=f"✅ **Successfully hacked {member.mention}.** Selling their search history for 5 robux.", color=discord.Color.green()))

    @commands.command(name="ship")
    async def ship(self, ctx, m1: discord.Member, m2: discord.Member=None): 
        target2 = m2 or ctx.author
        rating = random.randint(0, 100)
        embed = discord.Embed(title="❤️ Matchmaker", description=f"**{m1.name}** x **{target2.name}**\n\n**Compatibility:** {rating}%", color=discord.Color.pink())
        await ctx.send(embed=embed)

    @commands.command(name="pat")
    async def pat(self, ctx, member: discord.Member): 
        embed = discord.Embed(description=f"🤚 **{ctx.author.name} gently patted {member.name} on the head!**", color=discord.Color.pink())
        embed.set_image(url="[https://media1.tenor.com/m/8Y_2v_3_45wAAAAd/anime-pat.gif](https://media1.tenor.com/m/8Y_2v_3_45wAAAAd/anime-pat.gif)")
        await ctx.send(embed=embed)
    
    @commands.command(name="punch")
    async def punch(self, ctx, member: discord.Member): 
        embed = discord.Embed(description=f"👊 **{ctx.author.name} totally decked {member.name}!**", color=discord.Color.red())
        embed.set_image(url="[https://media1.tenor.com/m/2Y4Z8v3_45wAAAAd/anime-punch.gif](https://media1.tenor.com/m/2Y4Z8v3_45wAAAAd/anime-punch.gif)")
        await ctx.send(embed=embed)

    @commands.command(name="bite")
    async def bite(self, ctx, member: discord.Member): 
        embed = discord.Embed(description=f"🧛 **{ctx.author.name} bit {member.name}!**", color=discord.Color.dark_red())
        embed.set_image(url="[https://media1.tenor.com/m/ZzR7vT1wS4gAAAAd/anime-bite.gif](https://media1.tenor.com/m/ZzR7vT1wS4gAAAAd/anime-bite.gif)")
        await ctx.send(embed=embed)

    @commands.command(name="kiss")
    async def kiss(self, ctx, member: discord.Member): 
        embed = discord.Embed(description=f"💋 **{ctx.author.name} gave {member.name} a kiss!**", color=discord.Color.magenta())
        embed.set_image(url="[https://media1.tenor.com/m/2XyX9C4kG0QAAAAd/anime-kiss.gif](https://media1.tenor.com/m/2XyX9C4kG0QAAAAd/anime-kiss.gif)")
        await ctx.send(embed=embed)

    @commands.command(name="smug")
    async def smug(self, ctx): 
        embed = discord.Embed(description=f"😏 **{ctx.author.name} is looking extremely smug.**", color=discord.Color.purple())
        embed.set_image(url="[https://media1.tenor.com/m/3_4X3Y0_45wAAAAd/anime-smug.gif](https://media1.tenor.com/m/3_4X3Y0_45wAAAAd/anime-smug.gif)")
        await ctx.send(embed=embed)

    @commands.command(name="cry")
    async def cry(self, ctx): 
        embed = discord.Embed(description=f"😭 **{ctx.author.name} is crying in the corner.**", color=discord.Color.blue())
        embed.set_image(url="[https://media1.tenor.com/m/b-I3Jq7uU9wAAAAd/crying-anime.gif](https://media1.tenor.com/m/b-I3Jq7uU9wAAAAd/crying-anime.gif)")
        await ctx.send(embed=embed)

    @commands.command(name="quote")
    async def quote(self, ctx):
        quotes = [
            "If you don't fight, you can't win.", 
            "Since when were you under the impression that I wasn't using Kyoka Suigetsu?",
            "The bird of Hermes is my name, eating my wings to make me tame."
        ]
        await ctx.send(embed=discord.Embed(description=f"📜 *\"{random.choice(quotes)}\"*", color=discord.Color.dark_theme()))

    @commands.command(name="powerlevel")
    async def powerlevel(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        pwr = random.randint(10, 10000000)
        if pwr > 5000000: 
            await ctx.send(embed=discord.Embed(description=f"💥 **{target.mention}'s power level is {pwr:,}!** They have the aura of Wang Lin! Run!", color=discord.Color.gold()))
        else: 
            await ctx.send(embed=discord.Embed(description=f"🔍 **{target.mention}'s power level is {pwr:,}.** Just absolute fodder.", color=discord.Color.light_grey()))

    @commands.command(name="domain_expansion")
    async def domain_expansion(self, ctx): 
        embed = discord.Embed(description=f"🤞 **Domain Expansion!** {ctx.author.mention} trapped everyone in their domain!", color=discord.Color.dark_blue())
        embed.set_image(url="[https://media1.tenor.com/m/7_3X2v2X14YAAAAd/domain-expansion.gif](https://media1.tenor.com/m/7_3X2v2X14YAAAAd/domain-expansion.gif)")
        await ctx.send(embed=embed)

    @commands.command(name="bankai")
    async def bankai(self, ctx): 
        embed = discord.Embed(description=f"⚔️ **BANKAI!** {ctx.author.mention}'s spiritual pressure is crushing the server!", color=discord.Color.red())
        embed.set_image(url="[https://media1.tenor.com/m/9O3X3Y0O74cAAAAd/bankai.gif](https://media1.tenor.com/m/9O3X3Y0O74cAAAAd/bankai.gif)")
        await ctx.send(embed=embed)

# ==========================================
# FINAL SETUP HOOK
# ==========================================
async def setup(bot):
    await bot.add_cog(MasterCommands(bot))


