import discord
from discord.ext import commands, tasks
import os
import json
import random
import asyncio
from datetime import timedelta
from groq import AsyncGroq

# ==========================================
# DATABASE & DYNAMIC GIF SETUP
# ==========================================
DB_FILE = "database.json"

DEFAULT_GIFS = {
    "boss_spawn": ["https://media.giphy.com/media/Kx1nQEQigkUUM/giphy.gif"],
    "boss_win": ["https://media.giphy.com/media/11s7Ke7jcNxCHS/giphy.gif"],
    "boss_lose": ["https://media.giphy.com/media/8YmZ14DOpivXMuckSI/giphy.gif"],
    "work": ["https://media.giphy.com/media/13HgwGsXF0aiGY/giphy.gif"],
    "crime_win": ["https://media1.tenor.com/m/Nbb3z3G_yE8AAAAd/smug-anime.gif"],
    "crime_lose": ["https://media1.tenor.com/m/2A2-m3i3Z_8AAAAd/police-anime.gif"],
    "rob_win": ["https://media1.tenor.com/m/wO6LwO-W9VAAAAAd/run-anime.gif"],
    "rob_lose": ["https://media.giphy.com/media/vxvNnIYFcYqEE/giphy.gif"],
    "heist": ["https://media1.tenor.com/m/P0Tj_Z9zZBAAAAAd/megumin-explosion.gif"],
    "slots_spin": ["https://media1.tenor.com/m/71o_zXf12z0AAAAd/kakegurui-yumeko-jabami.gif"],
    "slots_jackpot": ["https://media1.tenor.com/m/1GvK0ZWe3gAAAAAd/hakari-dance.gif"],
    "slots_win": ["https://media.giphy.com/media/lptjRBxFKCJmFoibP3/giphy.gif"],
    "slots_lose": ["https://media1.tenor.com/m/1GvGzU-gB-QAAAAd/aqua-crying.gif"],
    "blackjack_win": ["https://media1.tenor.com/m/I2KzZ6f0b48AAAAd/kakegurui-cards.gif"],
    "blackjack_lose": ["https://media1.tenor.com/m/1GvGzU-gB-QAAAAd/aqua-crying.gif"],
    "coinflip_win": ["https://media1.tenor.com/m/aC7_YkYIwtYAAAAd/misaka-mikoto-coin.gif"],
    "coinflip_lose": ["https://media1.tenor.com/m/1GvGzU-gB-QAAAAd/aqua-crying.gif"],
    "level_up": ["https://media1.tenor.com/m/2T1cK-p3ZAMAAAAd/goku-super-saiyan.gif"],
    "nuke": ["https://media1.tenor.com/m/cWvO56B8gS0AAAAd/evangelion-explosion.gif"],
    "fakeban": ["https://media.giphy.com/media/fe4dDMD2cAU5RfEaCU/giphy.gif"],
    "pat": ["https://media.giphy.com/media/L2z7jvEQeR5v2/giphy.gif"],
    "punch": ["https://media.giphy.com/media/arbCGSt8TcbXq/giphy.gif"],
    "bite": ["https://media.giphy.com/media/Z7x24IHBcmV7W/giphy.gif"],
    "kiss": ["https://media.giphy.com/media/G3va31oGfiIGs/giphy.gif"],
    "smug": ["https://media.giphy.com/media/116wwYf3azFccE/giphy.gif"],
    "cry": ["https://media.giphy.com/media/ROF8OQvDsvvXy/giphy.gif"],
    "domain": ["https://media.giphy.com/media/VeqoDqdvj2J7bNVBq1/giphy.gif"],
    "bankai": ["https://media.giphy.com/media/8qDzzyxbcfimY/giphy.gif"]
}

def get_default_db():
    return {
        "warns": {}, "jailed": {}, 
        "config": {"filterwords": [], "ai_channel": None, "cmd_channel": None, "event_channel": None, "antiraid": False}, 
        "economy": {}, "levels": {}, "custom_commands": {}, "afk": {}, 
        "inventory": {}, "rep": {}, "bounties": {}, "current_shop": [],
        "gifs": DEFAULT_GIFS.copy()
    }

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f: json.dump(get_default_db(), f)
    with open(DB_FILE, "r") as f: 
        data = json.load(f)
        if "gifs" not in data: data["gifs"] = DEFAULT_GIFS.copy()
        for k, v in DEFAULT_GIFS.items():
            if k not in data["gifs"] or not data["gifs"][k]: data["gifs"][k] = v.copy()
        return data

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

db = load_db()
snipes = {}
edit_snipes = {}

def get_gif(category):
    lst = db["gifs"].get(category, [])
    return random.choice(lst) if lst else "https://media.giphy.com/media/Kx1nQEQigkUUM/giphy.gif"

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
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not yours!", ephemeral=True)
        self.value = True; [setattr(c, 'disabled', True) for c in self.children]; await interaction.response.edit_message(view=self); self.stop()
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not yours!", ephemeral=True)
        self.value = False; [setattr(c, 'disabled', True) for c in self.children]; await interaction.response.edit_message(view=self); self.stop()

class PaginationView(discord.ui.View):
    def __init__(self, ctx, embeds):
        super().__init__(timeout=120)
        self.ctx = ctx; self.embeds = embeds; self.current_page = 0; self.update_buttons()
    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0; self.children[1].disabled = self.current_page == (len(self.embeds) - 1)
    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.primary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not yours!", ephemeral=True)
        self.current_page -= 1; self.update_buttons(); await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not yours!", ephemeral=True)
        self.current_page += 1; self.update_buttons(); await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

class BuyButton(discord.ui.Button):
    def __init__(self, item):
        super().__init__(label=f"Buy {item['name']} ({item['price']:,})", style=discord.ButtonStyle.success)
        self.item = item
    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if db["economy"].get(uid, 0) < self.item["price"]: return await interaction.response.send_message(embed=discord.Embed(description=f"❌ You need **{self.item['price']:,} coins**.", color=discord.Color.red()), ephemeral=True)
        db["economy"][uid] -= self.item["price"]; db.setdefault("inventory", {}).setdefault(uid, []).append(self.item["name"]); save_db(db)
        await interaction.response.send_message(embed=discord.Embed(description=f"✅ **Purchased!** Added **{self.item['name']}** to inventory.", color=discord.Color.green()), ephemeral=True)

class DynamicShopView(discord.ui.View):
    def __init__(self, shop_items):
        super().__init__(timeout=300)
        for item in shop_items: self.add_item(BuyButton(item))

class AIBossFightView(discord.ui.View):
    def __init__(self, ctx, ai_client, chat_history):
        super().__init__(timeout=120)
        self.ctx = ctx; self.ai_client = ai_client; self.chat_history = chat_history
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author: await interaction.response.send_message("❌ Spawn your own boss!", ephemeral=True); return False
        return True
    async def process_turn(self, interaction: discord.Interaction, action: str):
        await interaction.response.defer()
        self.chat_history.append({"role": "user", "content": f"I choose to: {action}. Describe outcome under 100 words. End output EXACTLY with '[CONTINUE]', '[WIN]', or '[LOSE]'."})
        try:
            response = await self.ai_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=self.chat_history)
            reply = response.choices[0].message.content.strip()
        except Exception as e: return await interaction.edit_original_response(content=f"❌ DM disconnected: {e}")
        self.chat_history.append({"role": "assistant", "content": reply})

        if "[WIN]" in reply.upper():
            clean = reply.replace("[WIN]", "").replace("[win]", "").strip()
            reward = random.randint(1000000, 5000000)
            db["economy"][str(self.ctx.author.id)] = db["economy"].get(str(self.ctx.author.id), 0) + reward; save_db(db)
            embed = discord.Embed(title="🏆 RAID BOSS SLAIN!", description=f"{clean}\n\n💰 **Rewards:** {reward:,} Coins!", color=discord.Color.gold())
            embed.set_image(url=get_gif("boss_win")); [setattr(c, 'disabled', True) for c in self.children]
            await interaction.edit_original_response(embed=embed, view=self)
        elif "[LOSE]" in reply.upper():
            clean = reply.replace("[LOSE]", "").replace("[lose]", "").strip()
            embed = discord.Embed(title="💀 RAID WIPE - YOU DIED", description=clean, color=discord.Color.dark_red())
            embed.set_image(url=get_gif("boss_lose")); [setattr(c, 'disabled', True) for c in self.children]
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            clean = reply.replace("[CONTINUE]", "").replace("[continue]", "").strip()
            embed = discord.Embed(title="⚔️ RAID BOSS ENRAGED", description=clean, color=discord.Color.dark_theme())
            embed.set_image(url=get_gif("boss_spawn"))
            await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Attack 🗡️", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction, button): await self.process_turn(interaction, "Aggressively attack.")
    @discord.ui.button(label="Magic ✨", style=discord.ButtonStyle.primary)
    async def magic_button(self, interaction, button): await self.process_turn(interaction, "Cast devastating magic.")
    @discord.ui.button(label="Defend 🛡️", style=discord.ButtonStyle.success)
    async def defend_button(self, interaction, button): await self.process_turn(interaction, "Brace for impact.")
    @discord.ui.button(label="Flee 🏃", style=discord.ButtonStyle.secondary)
    async def run_button(self, interaction, button):
        [setattr(c, 'disabled', True) for c in self.children]
        await interaction.response.edit_message(embed=discord.Embed(title="🏃 COWARD", description="You abandoned the raid.", color=discord.Color.light_grey()), view=self)
# ==========================================
# CORE COG, ERROR HANDLER & LISTENERS
# ==========================================
class MasterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
        self.client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.ai_event_loop.start()
        self.shop_refresh_loop.start()

    def cog_unload(self):
        self.ai_event_loop.cancel(); self.shop_refresh_loop.cancel()

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandInvokeError): error = error.original
        if isinstance(error, commands.CommandOnCooldown):
            m, s = divmod(int(error.retry_after), 60); h, m = divmod(m, 60)
            t = f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"
            embed = discord.Embed(description=f"⏳ **Hold up!** Cooldown active. Try again in **{t}**.", color=discord.Color.red())
            if ctx.interaction:
                if not ctx.interaction.response.is_done(): await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
                else: await ctx.interaction.followup.send(embed=embed, ephemeral=True)
            else: await ctx.send(embed=embed, delete_after=10)
        elif isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(description="❌ **You lack permissions.**", color=discord.Color.red())
            if ctx.interaction:
                if not ctx.interaction.response.is_done(): await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
                else: await ctx.interaction.followup.send(embed=embed, ephemeral=True)
            else: await ctx.send(embed=embed, delete_after=5)
        else:
            print(f"Command Error: {error}"); err_msg = f"❌ **Internal error:** `{str(error)}`"
            try:
                if ctx.interaction:
                    if not ctx.interaction.response.is_done(): await ctx.interaction.response.send_message(err_msg, ephemeral=True)
                    else: await ctx.interaction.followup.send(err_msg, ephemeral=True)
                else: await ctx.send(err_msg)
            except: pass

    async def ask_groq(self, messages):
        if not self.client: raise Exception("Groq API Key missing.")
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]:
            try: 
                res = await self.client.chat.completions.create(model=model, messages=messages)
                return res.choices[0].message.content.strip()
            except: continue 
        raise Exception("All AI models failed.")

    @tasks.loop(minutes=60)
    async def shop_refresh_loop(self):
        master_items = [
            {"name": "True Bankai Awakening", "price": 5000000, "desc": "Unlocks ultimate potential."},
            {"name": "Gomu Gomu no Mi", "price": 10000000, "desc": "Tastes terrible."},
            {"name": "Heaven Defying Bead", "price": 50000000, "desc": "Bends reality."},
            {"name": "Sukuna's Finger", "price": 2500000, "desc": "Immense power, severe side effects."},
            {"name": "Infinity Stone", "price": 25000000, "desc": "Universal energy."},
            {"name": "Death Note", "price": 8000000, "desc": "Handle with care."}
        ]
        db["current_shop"] = random.sample(master_items, 4); save_db(db)
        channel_id = db["config"].get("event_channel")
        if channel_id and self.client: 
            channel = self.bot.get_channel(channel_id)
            if channel: await channel.send(embed=discord.Embed(title="🏪 MYSTIC SHOP RESTOCKED", description="New legendary artifacts!\nUse `/shop`.", color=discord.Color.magenta()))

    @shop_refresh_loop.before_loop
    async def before_shop_loop(self): await self.bot.wait_until_ready()

    @tasks.loop(minutes=60)
    async def ai_event_loop(self):
        channel_id = db["config"].get("event_channel")
        if channel_id and self.client:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try: 
                    reply = await self.ask_groq([{"role": "user", "content": "Generate an engaging Discord event. No JSON."}])
                    await channel.send(embed=discord.Embed(title="🌟 Server Event", description=reply, color=discord.Color.blurple()))
                except: pass

    @ai_event_loop.before_loop
    async def before_event_loop(self): await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if db["config"].get("antiraid", False):
            try: await member.kick(reason="Anti-Raid active.")
            except: pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.author.bot: snipes[message.channel.id] = {"content": message.content, "author": message.author.name, "avatar": str(message.author.display_avatar.url)}

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.author.bot: edit_snipes[before.channel.id] = {"before": before.content, "after": after.content, "author": before.author.name}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        uid = str(message.author.id)

        # 1. DM AI CHAT (WITH MEMORY)
        if not message.guild:
            if not self.client: return
            async with message.channel.typing():
                try: 
                    hist = [{"role": "system", "content": "You are habbibi mod (:, a chaotic, funny Discord bot. You are in DMs."}]
                    recent = [m async for m in message.channel.history(limit=6)]; recent.reverse()
                    for m in recent:
                        if m.content.strip(): hist.append({"role": "assistant" if m.author == self.bot.user else "user", "content": m.content})
                    reply = await self.ask_groq(hist)
                    await message.channel.send(reply[:2000])
                except Exception as e: await message.channel.send(f"❌ AI Error: {e}")
            return 

        # 2. AFK System
        if uid in db["afk"]:
            del db["afk"][uid]; save_db(db)
            await message.channel.send(embed=discord.Embed(description=f"👋 Welcome back {message.author.mention}, AFK removed.", color=discord.Color.green()), delete_after=10)
        for m in message.mentions:
            if str(m.id) in db["afk"]: await message.channel.send(embed=discord.Embed(description=f"💤 **{m.name}** is AFK: {db['afk'][str(m.id)]}", color=discord.Color.dark_grey()))

        # 3. Automod
        for w in db["config"]["filterwords"]:
            if w in message.content.lower():
                try: await message.delete(); await message.channel.send(embed=discord.Embed(description=f"⚠️ {message.author.mention}, blacklisted word!", color=discord.Color.red()), delete_after=5)
                except: pass
                return

        # 4. RPG Leveling
        if uid not in db["levels"]: db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["xp"] += random.randint(10, 25)
        if db["levels"][uid]["xp"] >= (db["levels"][uid]["level"] * 100) * 1.5 and db["levels"][uid]["level"] < 13000:
            db["levels"][uid]["level"] += 1; save_db(db)
            lvl_up = discord.Embed(title="Level Up!", description=f"🎉 **{message.author.mention}** leveled up to **Level {db['levels'][uid]['level']}**!", color=discord.Color.gold())
            lvl_up.set_image(url=get_gif("level_up"))
            await message.channel.send(embed=lvl_up)
        else: save_db(db)

        # 5. Custom Prefix
        if message.content.startswith('!') and len(message.content) > 1:
            cmd = message.content[1:].split()[0].lower()
            if cmd in db["custom_commands"]: return await message.channel.send(embed=discord.Embed(description=db["custom_commands"][cmd], color=discord.Color.blue()))

        # 6. SERVER AI CHAT (WITH MEMORY)
        ai_chan = db["config"].get("ai_channel")
        if message.channel.id == ai_chan and not message.content.startswith(('!', '/')) and self.client:
            async with message.channel.typing():
                try: 
                    hist = [{"role": "system", "content": "You are habbibi mod (:, a chaotic and sarcastic Discord bot."}]
                    recent = [m async for m in message.channel.history(limit=6)]; recent.reverse()
                    for m in recent:
                        if m.content.strip(): hist.append({"role": "assistant" if m.author == self.bot.user else "user", "content": m.content})
                    reply = await self.ask_groq(hist)
                    await message.channel.send(reply[:2000])
                except: pass
    # ==========================================
    # HIDDEN ADMIN GIF MANAGER
    # ==========================================
    @commands.hybrid_command(name="gif_add", description="[Admin] Add a Discord CDN or direct GIF link to a category.")
    @commands.has_permissions(administrator=True)
    async def gif_add(self, ctx, category: str, url: str):
        await ctx.defer(ephemeral=True)
        c = category.lower()
        if c not in db["gifs"]: db["gifs"][c] = []
        db["gifs"][c].append(url); save_db(db)
        await ctx.send(embed=discord.Embed(description=f"✅ **GIF Added!** The `{c}` category now has {len(db['gifs'][c])} randomized GIFs.", color=discord.Color.green()))

    @commands.hybrid_command(name="gif_remove", description="[Admin] Remove a GIF URL from a category.")
    @commands.has_permissions(administrator=True)
    async def gif_remove(self, ctx, category: str, url: str):
        await ctx.defer(ephemeral=True)
        c = category.lower()
        if c in db["gifs"] and url in db["gifs"][c]:
            db["gifs"][c].remove(url); save_db(db)
            await ctx.send(embed=discord.Embed(description=f"🗑️ **GIF Removed!** The `{c}` category now has {len(db['gifs'][c])} left.", color=discord.Color.red()))
        else: await ctx.send(embed=discord.Embed(description=f"❌ URL not found in `{c}`.", color=discord.Color.red()))

    @commands.hybrid_command(name="gif_list", description="[Admin] View all dynamic GIF categories.")
    @commands.has_permissions(administrator=True)
    async def gif_list(self, ctx):
        await ctx.defer(ephemeral=True)
        cats = "\n".join([f"**{k}**: {len(v)} GIFs" for k, v in db["gifs"].items()])
        await ctx.send(embed=discord.Embed(title="📂 Database GIF Categories", description=cats, color=discord.Color.blue()))

    # ==========================================
    # CONFIG & MASTERLIST
    # ==========================================
    @commands.hybrid_command(name="setaichannel", description="Sets AI auto-reply channel.")
    @commands.has_permissions(administrator=True)
    async def setaichannel(self, ctx): db["config"]["ai_channel"] = ctx.channel.id; save_db(db); await ctx.send(embed=discord.Embed(description=f"🤖 **AI Auto-Chat bound.**", color=discord.Color.green()))

    @commands.hybrid_command(name="setcmdchannel", description="Locks commands.")
    @commands.has_permissions(administrator=True)
    async def setcmdchannel(self, ctx): db["config"]["cmd_channel"] = ctx.channel.id; save_db(db); await ctx.send(embed=discord.Embed(description=f"🔒 **Commands locked.**", color=discord.Color.green()))

    @commands.hybrid_command(name="seteventchannel", description="Sets AI event channel.")
    @commands.has_permissions(administrator=True)
    async def seteventchannel(self, ctx): db["config"]["event_channel"] = ctx.channel.id; save_db(db); await ctx.send(embed=discord.Embed(description=f"🌟 **AI Events bound.**", color=discord.Color.green()))

    @commands.hybrid_command(name="unsetchannel", description="Unbinds a bot channel.")
    @commands.has_permissions(administrator=True)
    async def unsetchannel(self, ctx, channel_type: str):
        valid = {"ai": "ai_channel", "cmd": "cmd_channel", "event": "event_channel"}
        c = channel_type.lower()
        if c not in valid: return await ctx.send(embed=discord.Embed(description="❌ Use `ai`, `cmd`, or `event`.", color=discord.Color.red()))
        db["config"][valid[c]] = None; save_db(db); await ctx.send(embed=discord.Embed(description=f"✅ **Unbound {c.upper()}.**", color=discord.Color.green()))

    @commands.hybrid_command(name="deployserver", description="Wipes and builds layout.")
    @commands.has_permissions(administrator=True)
    async def deployserver(self, ctx):
        view = ConfirmView(ctx); msg = await ctx.send(embed=discord.Embed(title="⚠️ CLEAN SLATE", description="WIPE the server?", color=discord.Color.red()), view=view)
        await view.wait(); 
        if not view.value: return await msg.edit(embed=discord.Embed(description="🛑 Cancelled.", color=discord.Color.grey()), view=None)
        await msg.edit(embed=discord.Embed(description="⚙️ Wiping...", color=discord.Color.orange()), view=None)
        g = ctx.guild
        for c in g.channels:
            try: await c.delete(); await asyncio.sleep(0.5)
            except: pass
        for r in g.roles:
            if r.name != "@everyone" and not r.managed and r < g.me.top_role:
                try: await r.delete(); await asyncio.sleep(0.5)
                except: pass
        roles_to_make = [{"name": "Admin", "color": discord.Color.red()}, {"name": "Moderator", "color": discord.Color.orange()}, {"name": "Jailed", "color": discord.Color.dark_grey()}]
        cr = {}
        for r in roles_to_make:
            try: cr[r["name"]] = await g.create_role(name=r["name"], color=r["color"], permissions=discord.Permissions(administrator=(r["name"] == "Admin")), hoist=True); await asyncio.sleep(1)
            except: pass
        try: await ctx.author.add_roles(cr.get("Admin"))
        except: pass
        ci = await g.create_category("📌 INFORMATION"); await g.create_text_channel("rules", category=ci)
        cc = await g.create_category("💬 CHAT"); gc = await g.create_text_channel("general", category=cc); bc = await g.create_text_channel("bot-commands", category=cc); ac = await g.create_text_channel("talk-to-ai", category=cc)
        cv = await g.create_category("🔊 VOICE"); await g.create_voice_channel("General VC", category=cv)
        if "Jailed" in cr:
            for cat in g.categories:
                try: await cat.set_permissions(cr["Jailed"], read_messages=False, connect=False)
                except: pass
        db["config"]["cmd_channel"] = bc.id; db["config"]["ai_channel"] = ac.id; db["config"]["event_channel"] = gc.id; save_db(db)
        await gc.send(embed=discord.Embed(title="✅ Deployment Complete", description=f"{ctx.author.mention}, operational.", color=discord.Color.green()))

    @commands.hybrid_command(name="masterlist", description="View all bot commands.")
    async def masterlist(self, ctx):
        e1 = discord.Embed(title="🤖 Masterlist: Admin & Config (Page 1/4)", color=discord.Color.blue()).add_field(name="/gif_add, /gif_remove, /gif_list", value="Manage dynamic DB GIFs.", inline=False).add_field(name="/deployserver & /unsetchannel", value="Server setup.", inline=False).add_field(name="/aicommand", value="God-Mode AI execution.", inline=False).add_field(name="/define, /bossfight, /lore", value="Interactive AI.", inline=False)
        e2 = discord.Embed(title="🛡️ Masterlist: Moderation (Page 2/4)", color=discord.Color.red()).add_field(name="/tempban, /tempmute, /jail", value="Punishments.", inline=False).add_field(name="/lockdown, /snipe, /purge", value="Security.", inline=False)
        e3 = discord.Embed(title="💰 Masterlist: RPG & Utils (Page 3/4)", color=discord.Color.gold()).add_field(name="/shop, /bal, /daily, /weekly, /heist", value="Economy.", inline=False).add_field(name="/level, /rank, /poll", value="Utilities.", inline=False)
        e4 = discord.Embed(title="🤡 Masterlist: Prefix (Page 4/4)", description="**Use `!` for these (e.g., `!hack`)**", color=discord.Color.purple()).add_field(name="Trolls", value="`!fakeban`, `!rickroll`, `!roast`", inline=False).add_field(name="Anime", value="`!pat`, `!punch`, `!kiss`, `!domain_expansion`", inline=False)
        await ctx.send(embed=e1, view=PaginationView(ctx, [e1, e2, e3, e4]))

    # ==========================================
    # GOD-MODE & AI TOOLS
    # ==========================================
    @commands.hybrid_command(name='aicommand', description="Master AI brain. Execute python dynamically.")
    @commands.has_permissions(administrator=True)
    async def aicommand(self, ctx, *, instruction: str):
        await ctx.defer() 
        if not self.client: return await ctx.send(embed=discord.Embed(description="🤖 **AI is offline.**", color=discord.Color.red()))
        prompt = f"""Omnipotent Discord bot. Boss commanded: "{instruction}"
        Output a JSON array: 1. Reply: {{"action": "reply", "message": "text"}} 2. Execute Python: {{"action": "execute", "code": "await ctx.send('Done!')"}}
        STRICT RULES: Output ONLY a valid JSON array. Write valid discord.py async code."""
        try:
            raw_res = await self.ask_groq([{"role": "user", "content": prompt}])
            s, e = raw_res.find('['), raw_res.rfind(']')
            clean = raw_res[s:e+1] if s != -1 else raw_res.replace('```json', '').replace('```python', '').replace('```', '').strip()
            if clean.startswith('{'): clean = f"[{clean}]"
            for act in json.loads(clean):
                if act.get("action") == "reply": await ctx.send(embed=discord.Embed(description=f"🤖 {act.get('message')}", color=discord.Color.blurple()))
                elif act.get("action") == "execute":
                    msg = await ctx.send(embed=discord.Embed(description="⚡ **Executing Python...**", color=discord.Color.orange()))
                    try:
                        w = "async def __ai_exec():\n" + "\n".join([f"    {l}" for l in act.get("code", "").split("\n")])
                        env = {'discord': discord, 'bot': self.bot, 'ctx': ctx, 'asyncio': asyncio, 'db': db}
                        exec(w, env); await env['__ai_exec'](); await msg.edit(embed=discord.Embed(description="✅ **Execution Successful!**", color=discord.Color.green()))
                    except Exception as err: await msg.edit(embed=discord.Embed(description=f"⚠️ **Failed:**\n```py\n{err}\n```", color=discord.Color.red()))
        except Exception as e: await ctx.send(embed=discord.Embed(description=f"❌ **Error:** {e}", color=discord.Color.red()))

    @commands.hybrid_command(name="bossfight", description="Start an interactive Anime/Game Raid Boss Fight.")
    async def bossfight(self, ctx):
        await ctx.defer()
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        chat_history = [
            {"role": "system", "content": "You are an epic Dungeon Master. Keep responses under 100 words. Append '[CONTINUE]', '[WIN]', or '[LOSE]' at the exact end of every response."}, 
            {"role": "user", "content": "Generate the absolute beginning of an epic Anime or RPG Game themed Raid Boss fight. Describe a terrifying boss appearing. Do NOT resolve the fight yet. End with the boss attacking."}
        ]
        try: scen = await self.ask_groq(chat_history)
        except: return await ctx.send(embed=discord.Embed(description="❌ Connection failed.", color=discord.Color.red()))
        chat_history.append({"role": "assistant", "content": scen})
        embed = discord.Embed(title="⚔️ RAID BOSS SPAWNED", description=scen, color=discord.Color.dark_red())
        embed.set_image(url=get_gif("boss_spawn"))
        await ctx.send(embed=embed, view=AIBossFightView(ctx, self.client, chat_history))

    @commands.hybrid_command(name="define", description="AI powered dictionary.")
    async def define(self, ctx, word: str): 
        await ctx.defer()
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await self.ask_groq([{"role": "user", "content": f"Precise definition for: '{word}'"}])
        await ctx.send(embed=discord.Embed(title=f"📖 Definition: {word.title()}", description=reply, color=discord.Color.dark_blue()))

    @commands.hybrid_command(name="urban", description="AI Urban Dictionary.")
    async def urban(self, ctx, word: str): 
        await ctx.defer()
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await self.ask_groq([{"role": "user", "content": f"Slang definition for: '{word}'. Safe for work."}])
        await ctx.send(embed=discord.Embed(title=f"🏙️ Urban: {word.title()}", description=reply, color=discord.Color.dark_green()))
    @commands.hybrid_command(name="forceevent", description="Force AI event.")
    @commands.has_permissions(administrator=True)
    async def forceevent(self, ctx): 
        await ctx.defer()
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await self.ask_groq([{"role": "user", "content": "Generate a modern Discord event."}])
        await ctx.send(embed=discord.Embed(title="🌟 Event", description=reply, color=discord.Color.blurple()))

    @commands.hybrid_command(name="tldr", description="AI summarizes 50 messages.")
    async def tldr(self, ctx): 
        await ctx.defer()
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        log = "\n".join([m.content async for m in ctx.channel.history(limit=50) if m.content])
        reply = await self.ask_groq([{"role": "user", "content": f"Summarize:\n{log}"}])
        await ctx.send(embed=discord.Embed(title="📜 TL;DR", description=reply, color=discord.Color.light_grey()))

    @commands.hybrid_command(name="roast_history", description="AI roasts user messages.")
    async def roast_history(self, ctx, member: discord.Member): 
        await ctx.defer()
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        log = "\n".join([m.content async for m in ctx.channel.history(limit=25) if m.author == member and m.content])
        if not log: return await ctx.send(embed=discord.Embed(description="Not enough messages.", color=discord.Color.red()))
        reply = await self.ask_groq([{"role": "user", "content": f"Roast this user:\n{log}"}])
        await ctx.send(embed=discord.Embed(title=f"🔥 Roast: {member.name}", description=reply, color=discord.Color.dark_orange()))

    @commands.hybrid_command(name="gothic_translate")
    async def gothic_translate(self, ctx, *, text: str): 
        await ctx.defer()
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await self.ask_groq([{"role": "user", "content": f"Rewrite into dark gothic:\n{text}"}])
        await ctx.send(embed=discord.Embed(title="🦇 Gothic", description=reply, color=discord.Color.purple()))

    @commands.hybrid_command(name="lore")
    async def lore(self, ctx): 
        await ctx.defer()
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await self.ask_groq([{"role": "user", "content": f"Epic backstory for {ctx.guild.name}."}])
        await ctx.send(embed=discord.Embed(title="📖 Lore", description=reply, color=discord.Color.dark_theme()))

    @commands.hybrid_command(name="debate")
    async def debate(self, ctx, *, topic: str): 
        await ctx.defer()
        if not self.client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await self.ask_groq([{"role": "system", "content": "Argue against user."}, {"role": "user", "content": topic}])
        await ctx.send(embed=discord.Embed(title=f"⚖️ Debating: {topic}", description=reply, color=discord.Color.dark_grey()))

    # ==========================================
    # ADVANCED MODERATION
    # ==========================================
    @commands.hybrid_command(name="tempban")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, m: discord.Member, days: int, *, r: str="Ban"): 
        await ctx.defer(); await m.ban(reason=r); await ctx.send(embed=discord.Embed(title="🔨 Banned", description=f"**{m.name}** for {days}d.\nReason: {r}", color=discord.Color.red()))
        await asyncio.sleep(days * 86400); await ctx.guild.unban(m, reason="Expired")

    @commands.hybrid_command(name="tempmute")
    @commands.has_permissions(moderate_members=True)
    async def tempmute(self, ctx, m: discord.Member, mins: int, *, r: str="Mute"): 
        await ctx.defer(); await m.timeout(timedelta(minutes=mins), reason=r); await ctx.send(embed=discord.Embed(title="🔇 Muted", description=f"**{m.name}** for {mins}m.", color=discord.Color.orange()))

    @commands.hybrid_command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, s: int): 
        await ctx.defer(); await ctx.channel.edit(slowmode_delay=s); await ctx.send(embed=discord.Embed(description=f"⏱️ **Slowmode {s}s.**", color=discord.Color.blue()))

    @commands.hybrid_command(name="lockdown")
    @commands.has_permissions(administrator=True)
    async def lockdown(self, ctx):
        await ctx.defer(); await ctx.send(embed=discord.Embed(description="🚨 **LOCKDOWN INITIATED...**", color=discord.Color.red()))
        for c in ctx.guild.text_channels:
            try: await c.set_permissions(ctx.guild.default_role, send_messages=False)
            except: pass

    @commands.hybrid_command(name="unlockdown")
    @commands.has_permissions(administrator=True)
    async def unlockdown(self, ctx):
        await ctx.defer(); await ctx.send(embed=discord.Embed(description="🔓 **LOCKDOWN LIFTED...**", color=discord.Color.green()))
        for c in ctx.guild.text_channels:
            try: await c.set_permissions(ctx.guild.default_role, send_messages=True)
            except: pass

    @commands.hybrid_command(name="snipe")
    async def snipe(self, ctx):
        await ctx.defer(); d = snipes.get(ctx.channel.id)
        if not d: return await ctx.send(embed=discord.Embed(description="Nothing to snipe!", color=discord.Color.red()))
        await ctx.send(embed=discord.Embed(description=d["content"], color=discord.Color.red()).set_author(name=d["author"], icon_url=d["avatar"]))

    @commands.hybrid_command(name="editsnipe")
    async def editsnipe(self, ctx):
        await ctx.defer(); d = edit_snipes.get(ctx.channel.id)
        if not d: return await ctx.send(embed=discord.Embed(description="No edited messages!", color=discord.Color.red()))
        await ctx.send(embed=discord.Embed(title="Edited", color=discord.Color.orange()).set_author(name=d["author"]).add_field(name="Before", value=d["before"], inline=False).add_field(name="After", value=d["after"], inline=False))

    @commands.hybrid_command(name="purge")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int): 
        await ctx.defer(); view = ConfirmView(ctx); msg = await ctx.send(embed=discord.Embed(description=f"⚠️ Delete {amount} messages?", color=discord.Color.orange()), view=view)
        await view.wait()
        if not view.value: return await msg.edit(embed=discord.Embed(description="🛑 Cancelled.", color=discord.Color.grey()), view=None)
        await ctx.channel.purge(limit=amount + 1); await ctx.send(embed=discord.Embed(description=f"🧹 **Swept {amount}.**", color=discord.Color.green()), delete_after=4)

    @commands.hybrid_command(name="nuke")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx): 
        await ctx.defer(); view = ConfirmView(ctx); msg = await ctx.send(embed=discord.Embed(title="☢️ NUKE", description="Are you sure?", color=discord.Color.red()), view=view)
        await view.wait()
        if not view.value: return await msg.edit(embed=discord.Embed(description="🛑 Cancelled.", color=discord.Color.grey()), view=None)
        p = ctx.channel.position; nc = await ctx.channel.clone(); await ctx.channel.delete(); await nc.edit(position=p)
        embed = discord.Embed(description="☢️ **TACTICAL NUKE DEPLOYED!**", color=discord.Color.dark_red())
        embed.set_image(url=get_gif("nuke")); await nc.send(embed=embed)

    @commands.hybrid_command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, m: discord.Member, *, r: str="Lacking"): await ctx.defer(); await m.kick(reason=r); await ctx.send(embed=discord.Embed(description=f"👢 **{m.name} kicked.**", color=discord.Color.red()))

    @commands.hybrid_command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, m: discord.Member, *, r: str="Banned"): await ctx.defer(); await m.ban(reason=r); await ctx.send(embed=discord.Embed(description=f"🔨 **{m.name} banned.**", color=discord.Color.dark_red()))

    @commands.hybrid_command(name="warn")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, m: discord.Member, *, r: str="Violation"): 
        await ctx.defer(); db.setdefault("warns", {}).setdefault(str(m.id), []).append(r); save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⚠️ **{m.mention} warned.**", color=discord.Color.yellow()))

    @commands.hybrid_command(name="warnings")
    async def warnings(self, ctx, m: discord.Member): 
        await ctx.defer(); w = db["warns"].get(str(m.id), [])
        if not w: return await ctx.send(embed=discord.Embed(description=f"✅ **{m.name} is clean.**", color=discord.Color.green()))
        embed = discord.Embed(title=f"⚠️ Warnings: {m.name}", color=discord.Color.orange())
        for i, text in enumerate(w): embed.add_field(name=f"Warning {i+1}", value=text, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarns")
    @commands.has_permissions(administrator=True)
    async def clearwarns(self, ctx, m: discord.Member): 
        await ctx.defer(); db["warns"].pop(str(m.id), None); save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🗑️ **Cleared all warnings for {m.name}.**", color=discord.Color.green()))

    @commands.hybrid_command(name="jail")
    @commands.has_permissions(administrator=True)
    async def jail(self, ctx, m: discord.Member):
        await ctx.defer(); db.setdefault("jailed", {})[str(m.id)] = [r.id for r in m.roles if r.id != ctx.guild.default_role.id]; save_db(db)
        for r in m.roles[1:]:
            try: await m.remove_roles(r)
            except: pass
        jr = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jr: await m.add_roles(jr); await ctx.send(embed=discord.Embed(description=f"⛓️ **{m.mention} locked up.**", color=discord.Color.dark_grey()))
        else: await ctx.send(embed=discord.Embed(description="⚠️ 'Jailed' role missing.", color=discord.Color.red()))

    @commands.hybrid_command(name="unjail")
    @commands.has_permissions(administrator=True)
    async def unjail(self, ctx, m: discord.Member):
        await ctx.defer(); jr = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jr and jr in m.roles: await m.remove_roles(jr)
        for r_id in db.get("jailed", {}).pop(str(m.id), []):
            role = ctx.guild.get_role(r_id)
            if role: 
                try: await m.add_roles(role)
                except: pass
        save_db(db); await ctx.send(embed=discord.Embed(description=f"🔓 **{m.mention} made bail.**", color=discord.Color.green()))

    # ==========================================
    # RPG, ECONOMY & ANIMATED GIF EVENTS
    # ==========================================
    @commands.hybrid_command(name="shop", description="View the interactive rotating Legendary Shop.")
    async def shop(self, ctx): 
        await ctx.defer()
        items = db.get("current_shop", [])
        if not items: return await ctx.send(embed=discord.Embed(description="🛒 Merchant is traveling.", color=discord.Color.dark_grey()))
        embed = discord.Embed(title="🛒 The Mystic Merchant", description="Restocks every 60 mins.", color=discord.Color.gold())
        for item in items: embed.add_field(name=f"✨ {item['name']}", value=f"**{item['price']:,} Coins**\n*{item['desc']}*", inline=False)
        await ctx.send(embed=embed, view=DynamicShopView(items))

    @commands.hybrid_command(name="inventory")
    async def inventory(self, ctx): 
        await ctx.defer(); items = db.get("inventory", {}).get(str(ctx.author.id), [])
        if not items: return await ctx.send(embed=discord.Embed(description="🎒 Inventory empty.", color=discord.Color.blue()))
        chunks = [items[i:i + 10] for i in range(0, len(items), 10)]
        embeds = [discord.Embed(title=f"🎒 Relics ({i+1}/{len(chunks)})", description="\n".join([f"- {x}" for x in chunk]), color=discord.Color.blue()) for i, chunk in enumerate(chunks)]
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))

    @commands.hybrid_command(name="bal")
    async def bal(self, ctx, m: discord.Member = None): 
        await ctx.defer(); t = m or ctx.author; b = db["economy"].get(str(t.id), 0)
        await ctx.send(embed=discord.Embed(title="🏦 Bank", description=f"💰 **{t.name}**: **{b:,}** coins.", color=discord.Color.green()))

    @commands.hybrid_command(name="daily")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx): 
        await ctx.defer(); db.setdefault("economy", {})[str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + 500000; save_db(db)
        await ctx.send(embed=discord.Embed(description="🎁 **Claimed 500,000 coins!**", color=discord.Color.gold()))

    @commands.hybrid_command(name="weekly", description="Claim weekly coins.")
    @commands.cooldown(1, 604800, commands.BucketType.user)
    async def weekly(self, ctx): 
        await ctx.defer(); db.setdefault("economy", {})[str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + 5000000; save_db(db)
        await ctx.send(embed=discord.Embed(description="💎 **Claimed 5,000,000 coins!**", color=discord.Color.purple()))

    @commands.hybrid_command(name="work")
    @commands.cooldown(1, 3600, commands.BucketType.user) 
    async def work(self, ctx): 
        await ctx.defer()
        e = random.randint(50000, 150000); db.setdefault("economy", {})[str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + e; save_db(db)
        embed = discord.Embed(description=f"💼 **Earned {e:,} coins!**", color=discord.Color.green())
        embed.set_image(url=get_gif("work"))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="crime", description="Commit a crime for coins (risky).")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def crime(self, ctx):
        await ctx.defer()
        u = str(ctx.author.id)
        if random.choice([True, False]): 
            e = random.randint(100000, 400000); db.setdefault("economy", {})[u] = db["economy"].get(u, 0) + e
            embed = discord.Embed(description=f"🥷 **Hacked {e:,} coins!**", color=discord.Color.purple())
            embed.set_image(url=get_gif("crime_win"))
        else: 
            l = random.randint(50000, 150000); db.setdefault("economy", {})[u] = max(0, db["economy"].get(u, 0) - l)
            embed = discord.Embed(description=f"🚓 **Feds caught you! Fined {l:,} coins.**", color=discord.Color.red())
            embed.set_image(url=get_gif("crime_lose"))
        save_db(db); await ctx.send(embed=embed)

    @commands.hybrid_command(name="rob")
    @commands.cooldown(1, 7200, commands.BucketType.user)
    async def rob(self, ctx, m: discord.Member):
        await ctx.defer()
        u, t = str(ctx.author.id), str(m.id)
        if db.setdefault("economy", {}).get(t, 0) < 100000: return await ctx.send(embed=discord.Embed(description=f"❌ **{m.name} is too poor.**", color=discord.Color.red()))
        if random.choice([True, False]): 
            s = random.randint(50000, int(db["economy"][t] * 0.25)); db["economy"][t] -= s; db["economy"][u] = db["economy"].get(u, 0) + s
            embed = discord.Embed(description=f"🔫 **Mugged {s:,} coins!**", color=discord.Color.green())
            embed.set_image(url=get_gif("rob_win"))
        else: 
            f = 100000; db["economy"][u] = max(0, db["economy"].get(u, 0) - f)
            embed = discord.Embed(description=f"🛡️ **{m.name} fought back! Fined {f:,} coins.**", color=discord.Color.dark_red())
            embed.set_image(url=get_gif("rob_lose"))
        save_db(db); await ctx.send(embed=embed)

    @commands.hybrid_command(name="heist")
    @commands.cooldown(1, 14400, commands.BucketType.guild)
    async def heist(self, ctx): 
        await ctx.defer()
        p = random.randint(1000000, 5000000); db.setdefault("economy", {})[str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + p; save_db(db)
        embed = discord.Embed(title="🏦 BANK HEIST", description=f"You blew the vault and escaped with **{p:,} coins!**", color=discord.Color.gold())
        embed.set_image(url=get_gif("heist"))
        await ctx.send(embed=embed)
    @commands.hybrid_command(name="slots", description="Animated slot machine.")
    async def slots(self, ctx, bet: int):
        await ctx.defer()
        uid = str(ctx.author.id)
        if bet < 100: return await ctx.send(embed=discord.Embed(description="❌ Min bet is 100.", color=discord.Color.red()))
        if db.setdefault("economy", {}).get(uid, 0) < bet: return await ctx.send(embed=discord.Embed(description="❌ Not enough coins.", color=discord.Color.red()))
            
        db["economy"][uid] -= bet; save_db(db)
        embed = discord.Embed(title="🎰 SLOTS 🎰", description="**[ 🎰 | 🎰 | 🎰 ]**\n*Spinning...*", color=discord.Color.dark_theme())
        embed.set_image(url=get_gif("slots_spin"))
        embed.set_author(name=ctx.author.name, icon_url=str(ctx.author.display_avatar.url))
        msg = await ctx.send(embed=embed)
        
        r = ["🍒", "🍋", "💎", "⭐", "🔔", "🍇"]
        r1, r2, r3 = random.choice(r), random.choice(r), random.choice(r)

        await asyncio.sleep(0.6); embed.description = f"**[ {r1} | {r2} | {r3} ]**"
        
        if r1 == r2 == r3: 
            w = bet * 10; db["economy"][uid] += w; embed.color = discord.Color.gold()
            embed.description += f"\n\n🎉 **JACKPOT!** Won **{w:,} coins!**"
            embed.set_image(url=get_gif("slots_jackpot"))
        elif r1 == r2 or r2 == r3 or r1 == r3: 
            w = int(bet * 1.5); db["economy"][uid] += w; embed.color = discord.Color.green()
            embed.description += f"\n\n✨ **Small Win!** Won **{w:,} coins!**"
            embed.set_image(url=get_gif("slots_win"))
        else: 
            embed.color = discord.Color.red(); embed.description += f"\n\n💥 **You lost.**"
            embed.set_image(url=get_gif("slots_lose"))
            
        save_db(db); embed.set_footer(text=f"New Balance: {db['economy'][uid]:,} coins"); await msg.edit(embed=embed)

    @commands.hybrid_command(name="blackjack", description="Play 21 against the bot.")
    async def blackjack(self, ctx, bet: int):
        await ctx.defer(); u = str(ctx.author.id)
        if db.setdefault("economy", {}).get(u, 0) < bet or bet <= 0: return await ctx.send(embed=discord.Embed(description="❌ Poor.", color=discord.Color.red()))
        db["economy"][u] -= bet; p, b = random.randint(15, 25), random.randint(17, 23)
        embed = discord.Embed(color=discord.Color.gold())
        if p > 21: embed.description = f"🃏 **Bust!** You: {p}, Bot: {b}. Lost."; embed.color = discord.Color.red(); embed.set_image(url=get_gif("blackjack_lose"))
        elif p > b or b > 21: db["economy"][u] += bet*2; embed.description = f"🃏 **Win!** You: {p}, Bot: {b}. Won **{bet*2:,}**!"; embed.set_image(url=get_gif("blackjack_win"))
        else: embed.description = f"🃏 **Lost.** Bot: {b}, You: {p}."; embed.color = discord.Color.red(); embed.set_image(url=get_gif("blackjack_lose"))
        save_db(db); await ctx.send(embed=embed)

    @commands.hybrid_command(name="coinflip", description="Gamble 50/50.")
    async def coinflip(self, ctx, bet: int, c: str):
        await ctx.defer()
        if c.lower() not in ["heads", "tails"]: return await ctx.send(embed=discord.Embed(description="❌ 'heads' or 'tails'.", color=discord.Color.red()))
        u = str(ctx.author.id)
        if db.setdefault("economy", {}).get(u, 0) < bet or bet <= 0: return await ctx.send(embed=discord.Embed(description="❌ Poor.", color=discord.Color.red()))
        db["economy"][u] -= bet; res = random.choice(["heads", "tails"])
        embed = discord.Embed()
        if c.lower() == res: db["economy"][u] += bet*2; embed.description = f"🪙 **{res.title()}!** Won **{bet*2:,}**!"; embed.color = discord.Color.green(); embed.set_image(url=get_gif("coinflip_win"))
        else: embed.description = f"🪙 **{res.title()}.** Lost."; embed.color = discord.Color.red(); embed.set_image(url=get_gif("coinflip_lose"))
        save_db(db); await ctx.send(embed=embed)

    @commands.hybrid_command(name="give", description="Give coins.")
    async def give(self, ctx, m: discord.Member, a: int):
        await ctx.defer(); u, t = str(ctx.author.id), str(m.id)
        if db.setdefault("economy", {}).get(u, 0) < a or a <= 0: return await ctx.send(embed=discord.Embed(description="❌ Poor.", color=discord.Color.red()))
        db["economy"][u] -= a; db["economy"][t] = db["economy"].get(t, 0) + a; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"💸 Gave **{a:,}** coins to {m.name}.", color=discord.Color.green()))

    @commands.hybrid_command(name="trade", description="Trade items.")
    async def trade(self, ctx, m: discord.Member, item: str):
        await ctx.defer(); u, t = str(ctx.author.id), str(m.id); i = item.lower()
        if i not in db.setdefault("inventory", {}).get(u, []): return await ctx.send(embed=discord.Embed(description="❌ Don't own.", color=discord.Color.red()))
        db["inventory"][u].remove(i); db.setdefault("inventory", {}).setdefault(t, []).append(i); save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🤝 Traded **{i.title()}** to {m.name}.", color=discord.Color.green()))
        
    @commands.hybrid_command(name="bounty", description="Place bounty.")
    async def bounty(self, ctx, m: discord.Member, a: int):
        await ctx.defer(); u = str(ctx.author.id)
        if db.setdefault("economy", {}).get(u, 0) < a or a <= 0: return await ctx.send(embed=discord.Embed(description="❌ Poor.", color=discord.Color.red()))
        db["economy"][u] -= a; db.setdefault("bounties", {})[str(m.id)] = db["bounties"].get(str(m.id), 0) + a; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"💀 Bounty of **{a:,}** placed on {m.name}!", color=discord.Color.dark_red()))

    @commands.hybrid_command(name="claimbounty", description="Claim bounty.")
    async def claimbounty(self, ctx, m: discord.Member):
        await ctx.defer(); u, t = str(ctx.author.id), str(m.id); b = db.setdefault("bounties", {}).get(t, 0)
        if b <= 0: return await ctx.send(embed=discord.Embed(description="❌ No bounty.", color=discord.Color.red()))
        db["bounties"][t] = 0; db.setdefault("economy", {})[u] = db["economy"].get(u, 0) + b; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🔪 Claimed **{b:,}** coins!", color=discord.Color.green()))

    @commands.hybrid_command(name="fish", description="Cast a line and catch fish.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def fish(self, ctx): 
        await ctx.defer()
        fish = random.choice(["Old Boot", "Common Carp", "Rare Salmon", "Legendary Shark"])
        reward = {"Old Boot": 0, "Common Carp": 5000, "Rare Salmon": 20000, "Legendary Shark": 100000}[fish]
        db.setdefault("economy", {})[str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🎣 Caught a {fish}! Sold for {reward:,} coins.", color=discord.Color.blue()))

    @commands.hybrid_command(name="hunt", description="Hunt animals or monsters.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def hunt(self, ctx): 
        await ctx.defer()
        mob = random.choice(["Mutant Rat", "Forest Goblin", "Shadow Dragon"])
        reward = {"Mutant Rat": 2000, "Forest Goblin": 15000, "Shadow Dragon": 150000}[mob]
        db.setdefault("economy", {})[str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🏹 Slayed a {mob}! Claimed {reward:,} coins.", color=discord.Color.dark_green()))

    @commands.hybrid_command(name="mine", description="Mine for ores.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def mine(self, ctx): 
        await ctx.defer()
        ore = random.choice(["Stone", "Iron Ore", "Raw Diamond"])
        reward = {"Stone": 500, "Iron Ore": 8000, "Raw Diamond": 120000}[ore]
        db.setdefault("economy", {})[str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⛏️ Mined {ore}! Sold for {reward:,} coins.", color=discord.Color.light_grey()))

    @commands.hybrid_command(name="rich")
    async def rich(self, ctx): 
        await ctx.defer(); se = sorted(db.get("economy", {}).items(), key=lambda x: x[1], reverse=True)
        if not se: return await ctx.send("No data.")
        chunks = [se[i:i + 10] for i in range(0, len(se), 10)]; embeds = []
        for i, c in enumerate(chunks):
            e = discord.Embed(title=f"🏆 Richest (Page {i+1}/{len(chunks)})", color=discord.Color.gold())
            for j, (uid, amt) in enumerate(c): e.add_field(name=f"#{i*10 + j + 1}", value=f"<@{uid}>: **{amt:,}**", inline=False)
            embeds.append(e)
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))

    @commands.hybrid_command(name="quest")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def quest(self, ctx):
        await ctx.defer(); u = str(ctx.author.id)
        if db.setdefault("levels", {}).setdefault(u, {"xp": 0, "level": 1})["level"] >= 13000: return await ctx.send(embed=discord.Embed(description="🛑 **Max Level 13,000!**", color=discord.Color.red()))
        x = random.randint(300, 800); db["levels"][u]["xp"] += x; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🗡️ **Dungeon run complete!** Earned **{x} XP**!", color=discord.Color.orange()))

    # ==========================================
    # LEVELING & UTILITY
    # ==========================================
    @commands.hybrid_command(name="rank", description="Check XP Rank.")
    async def rank(self, ctx, m: discord.Member = None): 
        await ctx.defer(); t = m or ctx.author; l = db.setdefault("levels", {}).setdefault(str(t.id), {"xp": 0, "level": 1})
        embed = discord.Embed(title=f"Rank: {t.name}", description=f"⭐ Lvl: **{l['level']}**\n✨ XP: **{l['xp']}**", color=discord.Color.blue())
        embed.set_thumbnail(url=str(t.display_avatar.url))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard_levels", description="Top highest levels.")
    async def leaderboard_levels(self, ctx): 
        await ctx.defer(); sl = sorted(db.get("levels", {}).items(), key=lambda x: x[1]["level"], reverse=True)
        if not sl: return await ctx.send("No data.")
        chunks = [sl[i:i + 10] for i in range(0, len(sl), 10)]; embeds = []
        for i, c in enumerate(chunks):
            e = discord.Embed(title=f"🏆 Level Leaderboard ({i+1}/{len(chunks)})", color=discord.Color.gold())
            for j, (uid, d) in enumerate(c): e.add_field(name=f"#{i*10 + j + 1}", value=f"<@{uid}> - Lvl {d['level']}", inline=False)
            embeds.append(e)
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))

    @commands.hybrid_command(name="givexp")
    @commands.has_permissions(administrator=True)
    async def givexp(self, ctx, m: discord.Member, a: int): 
        await ctx.defer(); db.setdefault("levels", {}).setdefault(str(m.id), {"xp": 0, "level": 1})["xp"] += a; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"📈 Granted {a} XP to {m.name}.", color=discord.Color.green()))

    @commands.hybrid_command(name="removexp")
    @commands.has_permissions(administrator=True)
    async def removexp(self, ctx, m: discord.Member, a: int): 
        await ctx.defer(); u = str(m.id); db["levels"][u]["xp"] = max(0, db.setdefault("levels", {}).get(u, {"xp":0})["xp"] - a); save_db(db)
        await ctx.send(embed=discord.Embed(description=f"📉 Removed {a} XP from {m.name}.", color=discord.Color.red()))

    @commands.hybrid_command(name="setlevel")
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, m: discord.Member, l: int): 
        await ctx.defer(); db.setdefault("levels", {}).setdefault(str(m.id), {"xp": 0, "level": 1})["level"] = l; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⭐ Set {m.name} to Lvl {l}.", color=discord.Color.gold()))

    @commands.hybrid_command(name="rewards")
    async def rewards(self, ctx): 
        await ctx.defer(); await ctx.send(embed=discord.Embed(title="🎁 Rewards", description="Lvl 10: Trusted\nLvl 50: Ronin\nLvl 100: God", color=discord.Color.green()))

    @commands.hybrid_command(name="rep", description="Give rep.")
    async def rep(self, ctx, m: discord.Member):
        await ctx.defer()
        if m.id == ctx.author.id: return await ctx.send(embed=discord.Embed(description="❌ No self rep.", color=discord.Color.red()))
        db.setdefault("rep", {})[str(m.id)] = db["rep"].get(str(m.id), 0) + 1; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"👍 +1 Rep to {m.name}.", color=discord.Color.green()))

    @commands.hybrid_command(name="leaderboard_rep", description="Top rep.")
    async def leaderboard_rep(self, ctx): 
        await ctx.defer()
        sr = sorted(db.get("rep", {}).items(), key=lambda x: x[1], reverse=True)
        if not sr: return await ctx.send("No data.")
        chunks = [sr[i:i + 10] for i in range(0, len(sr), 10)]; embeds = []
        for i, c in enumerate(chunks):
            e = discord.Embed(title=f"👍 Most Reputable ({i+1}/{len(chunks)})", color=discord.Color.green())
            for j, (uid, amt) in enumerate(c): e.add_field(name=f"#{i*10 + j + 1}", value=f"<@{uid}> - {amt} Rep", inline=False)
            embeds.append(e)
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))

    @commands.hybrid_command(name="poll", description="Create poll.")
    async def poll(self, ctx, q: str): 
        await ctx.defer(); m = await ctx.send(embed=discord.Embed(title="📊 Poll", description=q, color=discord.Color.green()))
        await m.add_reaction("👍"); await m.add_reaction("👎")

    @commands.hybrid_command(name="giveaway_start")
    @commands.has_permissions(manage_messages=True)
    async def giveaway_start(self, ctx, p: str): 
        await ctx.defer(); m = await ctx.send(embed=discord.Embed(title=f"🎉 GIVEAWAY: {p}", description="React 🎉", color=discord.Color.gold()))
        await m.add_reaction("🎉")

    @commands.hybrid_command(name="giveaway_reroll")
    @commands.has_permissions(manage_messages=True)
    async def giveaway_reroll(self, ctx): await ctx.defer(); await ctx.send("🎉 Rerolled!")

    @commands.hybrid_command(name="ticket_setup")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx): await ctx.defer(); await ctx.send(embed=discord.Embed(description="🎫 Tickets initialized.", color=discord.Color.blue()))

    @commands.hybrid_command(name="ticket_close")
    @commands.has_permissions(manage_channels=True)
    async def ticket_close(self, ctx): await ctx.channel.delete()

    @commands.hybrid_command(name="remindme")
    async def remindme(self, ctx, s: int, *, m: str): 
        await ctx.defer(); await ctx.send(embed=discord.Embed(description=f"⏰ Set for {s}s.", color=discord.Color.blue()))
        await asyncio.sleep(s); await ctx.author.send(embed=discord.Embed(title="⏰ Reminder", description=m, color=discord.Color.gold()))

    @commands.hybrid_command(name="afk")
    async def afk(self, ctx, *, r="AFK"): 
        await ctx.defer(); db.setdefault("afk", {})[str(ctx.author.id)] = r; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"💤 AFK: {r}", color=discord.Color.dark_grey()))

    @commands.hybrid_command(name="weather")
    async def weather(self, ctx, c: str): await ctx.defer(); await ctx.send(embed=discord.Embed(description=f"🌤️ {c.title()}: Sunny, 75°F (Sim).", color=discord.Color.blue()))

    @commands.hybrid_command(name="calc")
    async def calc(self, ctx, e: str): 
        await ctx.defer()
        try: await ctx.send(embed=discord.Embed(description=f"🧮 `{eval(e, {'__builtins__': None}, {})}`", color=discord.Color.green()))
        except: await ctx.send(embed=discord.Embed(description="❌ Error.", color=discord.Color.red()))

    @commands.hybrid_command(name="translate")
    async def translate(self, ctx, l: str, *, t: str): await ctx.defer(); await ctx.send(embed=discord.Embed(description="🌐 Translated.", color=discord.Color.teal()))

    @commands.hybrid_command(name="userhistory")
    async def userhistory(self, ctx, m: discord.Member): await ctx.defer(); await ctx.send(embed=discord.Embed(description=f"📜 Joined: {m.joined_at.strftime('%Y-%m-%d')}", color=discord.Color.blue()))

    @commands.hybrid_command(name="roleinfo")
    async def roleinfo(self, ctx, r: discord.Role): await ctx.defer(); await ctx.send(embed=discord.Embed(description=f"🛡️ {len(r.members)} members.", color=r.color))

    @commands.hybrid_command(name="servericon")
    async def servericon(self, ctx): await ctx.defer(); await ctx.send(ctx.guild.icon.url if ctx.guild.icon else "No icon.")

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx): await ctx.defer(); await ctx.send(embed=discord.Embed(description=f"🏓 **Pong!** {round(self.bot.latency * 1000)}ms", color=discord.Color.blurple()))

    @commands.hybrid_command(name="avatar")
    async def avatar(self, ctx, m: discord.Member = None): await ctx.defer(); await ctx.send(embed=discord.Embed(color=discord.Color.blue()).set_image(url=str((m or ctx.author).display_avatar.url)))

    @commands.hybrid_command(name="serverinfo")
    async def serverinfo(self, ctx): await ctx.defer(); await ctx.send(embed=discord.Embed(title=ctx.guild.name, color=discord.Color.gold()).add_field(name="Members", value=ctx.guild.member_count))

    # ==========================================
    # 🤡 FUN & ANIME (PREFIX COMMANDS)
    # ==========================================
    @commands.command(name="fakeban")
    async def fakeban(self, ctx, m: discord.Member): 
        e = discord.Embed(description=f"🔨 **{m.name}** permanently banned.", color=discord.Color.red())
        e.set_image(url=get_gif("fakeban")); await ctx.send(embed=e)
    @commands.command(name="rickroll")
    async def rickroll(self, ctx, m: discord.Member):
        try: await m.send("🎁 Nitro: [https://youtube.com/watch?v=dQw4w9WgXcQ](https://youtube.com/watch?v=dQw4w9WgXcQ)"); await ctx.send(embed=discord.Embed(description=f"🤫 Sent.", color=discord.Color.green()))
        except: await ctx.send(embed=discord.Embed(description="❌ DMs closed.", color=discord.Color.red()))
    @commands.command(name="howgay")
    async def howgay(self, ctx, m: discord.Member=None): await ctx.send(embed=discord.Embed(description=f"🏳️‍🌈 {(m or ctx.author).name} is {random.randint(0,100)}% gay.", color=discord.Color.magenta()))
    @commands.command(name="simpmeter")
    async def simpmeter(self, ctx, m: discord.Member=None): await ctx.send(embed=discord.Embed(description=f"😳 {(m or ctx.author).name} is {random.randint(0,100)}% simp.", color=discord.Color.purple()))
    @commands.command(name="susmeter")
    async def susmeter(self, ctx, m: discord.Member=None): await ctx.send(embed=discord.Embed(description=f"📮 {(m or ctx.author).name} is {random.randint(0,100)}% sus.", color=discord.Color.dark_grey()))
    @commands.command(name="roast")
    async def roast(self, ctx, m: discord.Member): await ctx.send(embed=discord.Embed(description=f"{m.mention} 🔥 You're like a cloud. When you leave, it's a beautiful day.", color=discord.Color.orange()))
    @commands.command(name="compliment")
    async def compliment(self, ctx, m: discord.Member): await ctx.send(embed=discord.Embed(description=f"💖 {m.mention} You light up the room!", color=discord.Color.pink()))
    @commands.command(name="confess")
    async def confess(self, ctx, *, msg: str): 
        try: await ctx.message.delete()
        except: pass
        await ctx.send(embed=discord.Embed(title="🤫 Confession", description=msg, color=discord.Color.dark_theme()))
    @commands.command(name="kill")
    async def kill(self, ctx, m: discord.Member): await ctx.send(embed=discord.Embed(description=f"☠️ **{m.name}** fell out of the world.", color=discord.Color.dark_red()))
    @commands.command(name="revive")
    async def revive(self, ctx, m: discord.Member): await ctx.send(embed=discord.Embed(description=f"👼 **{m.name}** resurrected!", color=discord.Color.gold()))
    @commands.command(name="meme")
    async def meme(self, ctx): await ctx.send("😂 *[Meme Placeholder]*")
    @commands.command(name="dadjoke")
    async def dadjoke(self, ctx): await ctx.send(embed=discord.Embed(description="🧔 **Joke:** Calendar's days are numbered.", color=discord.Color.blue()))
    @commands.command(name="choose")
    async def choose(self, ctx, o1: str, o2: str): await ctx.send(embed=discord.Embed(description=f"🤔 `{random.choice([o1, o2])}`", color=discord.Color.teal()))
    @commands.command(name="spank")
    async def spank(self, ctx, m: discord.Member): await ctx.send(embed=discord.Embed(description=f"🤚 **{ctx.author.name} spanked {m.name}!**", color=discord.Color.dark_orange()))
    @commands.command(name="jailbreak")
    async def jailbreak(self, ctx, m: discord.Member):
        if random.randint(1, 10) <= 2: 
            jr = discord.utils.get(ctx.guild.roles, name="Jailed")
            if jr and jr in m.roles: await m.remove_roles(jr)
            await ctx.send(embed=discord.Embed(description="🔓 **SUCCESS!**", color=discord.Color.green()))
        else: await ctx.send(embed=discord.Embed(description="❌ **Failed.**", color=discord.Color.red()))
    @commands.command(name="eightball")
    async def eightball(self, ctx, *, q: str): await ctx.send(embed=discord.Embed(description=f"🎱 **A:** {random.choice(['Yes.', 'No.', 'Maybe.'])}", color=discord.Color.dark_grey()))
    @commands.command(name="hack")
    async def hack(self, ctx, m: discord.Member): msg = await ctx.send(embed=discord.Embed(description="💻 **Hacking...**", color=discord.Color.dark_grey())); await asyncio.sleep(2); await msg.edit(embed=discord.Embed(description=f"✅ **Hacked {m.mention}.**", color=discord.Color.green()))
    @commands.command(name="ship")
    async def ship(self, ctx, m1: discord.Member, m2: discord.Member=None): await ctx.send(embed=discord.Embed(description=f"❤️ **{m1.name} x {(m2 or ctx.author).name}:** {random.randint(0,100)}%", color=discord.Color.pink()))
    
    @commands.command(name="pat")
    async def pat(self, ctx, m: discord.Member): 
        e = discord.Embed(description=f"🤚 **{ctx.author.name} patted {m.name}!**", color=discord.Color.pink())
        e.set_image(url=get_gif("pat")); await ctx.send(embed=e)
    @commands.command(name="punch")
    async def punch(self, ctx, m: discord.Member): 
        e = discord.Embed(description=f"👊 **{ctx.author.name} punched {m.name}!**", color=discord.Color.red())
        e.set_image(url=get_gif("punch")); await ctx.send(embed=e)
    @commands.command(name="bite")
    async def bite(self, ctx, m: discord.Member): 
        e = discord.Embed(description=f"🧛 **{ctx.author.name} bit {m.name}!**", color=discord.Color.dark_red())
        e.set_image(url=get_gif("bite")); await ctx.send(embed=e)
    @commands.command(name="kiss")
    async def kiss(self, ctx, m: discord.Member): 
        e = discord.Embed(description=f"💋 **{ctx.author.name} kissed {m.name}!**", color=discord.Color.magenta())
        e.set_image(url=get_gif("kiss")); await ctx.send(embed=e)
    @commands.command(name="smug")
    async def smug(self, ctx): 
        e = discord.Embed(description=f"😏 **{ctx.author.name} is smug.**", color=discord.Color.purple())
        e.set_image(url=get_gif("smug")); await ctx.send(embed=e)
    @commands.command(name="cry")
    async def cry(self, ctx): 
        e = discord.Embed(description=f"😭 **{ctx.author.name} cries.**", color=discord.Color.blue())
        e.set_image(url=get_gif("cry")); await ctx.send(embed=e)
    @commands.command(name="quote")
    async def quote(self, ctx): await ctx.send(embed=discord.Embed(description=f"📜 *If you don't fight, you can't win.*", color=discord.Color.dark_theme()))
    @commands.command(name="powerlevel")
    async def powerlevel(self, ctx, m: discord.Member = None): 
        p = random.randint(10, 10000000)
        await ctx.send(embed=discord.Embed(description=f"💥 **Power level {p:,}!**" if p > 5000000 else f"🔍 **Power level {p:,}.**", color=discord.Color.gold()))
    @commands.command(name="domain_expansion")
    async def domain_expansion(self, ctx): 
        e = discord.Embed(description=f"🤞 **Domain Expansion!**", color=discord.Color.dark_blue())
        e.set_image(url=get_gif("domain")); await ctx.send(embed=e)
    @commands.command(name="bankai")
    async def bankai(self, ctx): 
        e = discord.Embed(description=f"⚔️ **BANKAI!**", color=discord.Color.red())
        e.set_image(url=get_gif("bankai")); await ctx.send(embed=e)

async def setup(bot):
    await bot.add_cog(MasterCommands(bot))
