import discord
from discord.ext import commands
import random
import json
import asyncio
# 🔥 FIXED: Imported from 'ui' instead of 'core' based on our new structure
from core import db, save_db, get_gif, ask_groq
from ui import PaginationView 

# ========================================================================
# MONSTER GACHA SYSTEM (Base Variables)
# ========================================================================
MONSTERS = {
    "Common": {"chance": 55, "value": 1500, "mobs": ["🟢 Slime", "🦇 Cave Bat", "🐀 Plague Rat"]},
    "Uncommon": {"chance": 25, "value": 5000, "mobs": ["👺 Goblin", "🐺 Dire Wolf", "💀 Skeleton Warrior"]},
    "Rare": {"chance": 12, "value": 25000, "mobs": ["👹 Orc Brute", "🗿 Stone Gargoyle", "👻 Cursed Wraith"]},
    "Epic": {"chance": 6, "value": 100000, "mobs": ["🐉 Lesser Dragon", "🦅 Griffin", "🐍 Basilisk"]},
    "Legendary": {"chance": 2, "value": 1000000, "mobs": ["🔥 Immortal Phoenix", "🐙 Abyssal Kraken", "⚡ Storm Behemoth"]}
}

# ========================================================================
# UI CLASS: AI Black Market View
# ========================================================================
class BlackMarketView(discord.ui.View):
    def __init__(self, ctx, uid, mob_name, amount, buyers):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.uid = uid
        self.mob_name = mob_name
        self.amount = amount
        self.buyers = buyers

    async def process_sale(self, interaction: discord.Interaction, index: int):
        if interaction.user.id != int(self.uid):
            return await interaction.response.send_message("❌ This is not your deal!", ephemeral=True)

        buyer = self.buyers[index]
        payout = buyer["offer"]

        # Deduct mob
        db["zoo"][self.uid][self.mob_name] -= self.amount
        if db["zoo"][self.uid][self.mob_name] <= 0:
            del db["zoo"][self.uid][self.mob_name]
            
        # Add coins
        db.setdefault("economy", {})[self.uid] = db["economy"].get(self.uid, 0) + payout
        save_db(db)

        # Disable buttons
        for child in self.children: child.disabled = True
        
        embed = discord.Embed(title="🤝 Deal Closed!", description=f"You sold **{self.amount}x {self.mob_name}** to **{buyer['buyer']}** for **{payout:,} 🪙**!\n\n🗣️ *\"{buyer['quote']}\"*", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Sell to Buyer 1", style=discord.ButtonStyle.success)
    async def b1(self, interaction, button): await self.process_sale(interaction, 0)

    @discord.ui.button(label="Sell to Buyer 2", style=discord.ButtonStyle.primary)
    async def b2(self, interaction, button): await self.process_sale(interaction, 1)

    @discord.ui.button(label="Sell to Buyer 3", style=discord.ButtonStyle.danger)
    async def b3(self, interaction, button): await self.process_sale(interaction, 2)

# ========================================================================
# UI CLASSES: Interactive Trading System
# ========================================================================
class TradeOfferModal(discord.ui.Modal, title="Offer Assets"):
    asset_type = discord.ui.TextInput(label="Type: 'coins', 'item', or 'monster'", placeholder="e.g. monster", required=True)
    asset_name = discord.ui.TextInput(label="Exact Name (Leave blank if coins)", placeholder="e.g. Slime [The Cowardly]", required=False)
    amount = discord.ui.TextInput(label="Amount", placeholder="e.g. 1000", required=True)

    def __init__(self, view, player_num):
        super().__init__()
        self.view = view
        self.player_num = player_num # 1 or 2

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        a_type = self.asset_type.value.strip().lower()
        a_name = self.asset_name.value.strip()
        try: amt = int(self.amount.value.strip())
        except: return await interaction.followup.send("❌ Amount must be a number.", ephemeral=True)

        if amt <= 0: return await interaction.followup.send("❌ Amount must be greater than 0.", ephemeral=True)

        if a_type == "coins":
            if db.setdefault("economy", {}).get(uid, 0) < amt:
                return await interaction.followup.send("❌ You don't have that many coins.", ephemeral=True)
            self.view.offers[self.player_num]["coins"] += amt
            
        elif a_type == "item":
            inv = [i.lower() for i in db.setdefault("inventory", {}).get(uid, [])]
            if inv.count(a_name.lower()) < amt:
                return await interaction.followup.send("❌ You don't have enough of that item.", ephemeral=True)
            exact = next(i for i in db["inventory"][uid] if i.lower() == a_name.lower())
            self.view.offers[self.player_num]["items"][exact] = self.view.offers[self.player_num]["items"].get(exact, 0) + amt
            
        elif a_type in ["monster", "mob"]:
            zoo = db.setdefault("zoo", {}).get(uid, {})
            exact = next((m for m in zoo if a_name.lower() in m.lower()), None)
            if not exact or zoo[exact] < amt:
                return await interaction.followup.send("❌ You don't have enough of that monster.", ephemeral=True)
            self.view.offers[self.player_num]["monsters"][exact] = self.view.offers[self.player_num]["monsters"].get(exact, 0) + amt
        else:
            return await interaction.followup.send("❌ Invalid type. Use coins, item, or monster.", ephemeral=True)

        self.view.locked = {1: False, 2: False}
        await self.view.update_ui(interaction)

class ActiveTradeView(discord.ui.View):
    def __init__(self, p1, p2):
        super().__init__(timeout=300)
        self.p1 = p1
        self.p2 = p2
        self.offers = {
            1: {"coins": 0, "items": {}, "monsters": {}},
            2: {"coins": 0, "items": {}, "monsters": {}}
        }
        self.locked = {1: False, 2: False}

    def format_offer(self, p_num):
        o = self.offers[p_num]
        lines = [f"🪙 **Coins:** {o['coins']:,}"]
        if o["items"]: lines.append("🎒 **Items:** " + ", ".join([f"{k} x{v}" for k, v in o["items"].items()]))
        if o["monsters"]: lines.append("🐾 **Monsters:** " + ", ".join([f"{k} x{v}" for k, v in o["monsters"].items()]))
        status = "✅ Locked" if self.locked[p_num] else "⏳ Trading..."
        return "\n".join(lines) + f"\n**Status:** {status}"

    async def update_ui(self, interaction):
        embed = discord.Embed(title="🤝 Active Trade Session", color=discord.Color.blurple())
        embed.add_field(name=f"Player 1: {self.p1.name}", value=self.format_offer(1), inline=False)
        embed.add_field(name=f"Player 2: {self.p2.name}", value=self.format_offer(2), inline=False)
        
        if self.locked[1] and self.locked[2]:
            await self.execute_trade(interaction)
        else:
            await interaction.message.edit(embed=embed, view=self)

    async def execute_trade(self, interaction):
        u1, u2 = str(self.p1.id), str(self.p2.id)
        for p_num, uid, target_uid in [(1, u1, u2), (2, u2, u1)]:
            o = self.offers[p_num]
            if o["coins"] > 0:
                db["economy"][uid] -= o["coins"]
                db["economy"][target_uid] = db["economy"].get(target_uid, 0) + o["coins"]
            for item, amt in o["items"].items():
                for _ in range(amt):
                    db["inventory"][uid].remove(item)
                    db.setdefault("inventory", {}).setdefault(target_uid, []).append(item)
            for mob, amt in o["monsters"].items():
                db["zoo"][uid][mob] -= amt
                if db["zoo"][uid][mob] <= 0: del db["zoo"][uid][mob]
                db.setdefault("zoo", {}).setdefault(target_uid, {})[mob] = db["zoo"][target_uid].get(mob, 0) + amt

        save_db(db)
        for child in self.children: child.disabled = True
        await interaction.message.edit(embed=discord.Embed(title="🎉 Trade Successful!", color=discord.Color.green()), view=self)
        self.stop()

    @discord.ui.button(label="➕ Add Offer", style=discord.ButtonStyle.primary)
    async def offer_btn(self, interaction, button):
        if interaction.user == self.p1: await interaction.response.send_modal(TradeOfferModal(self, 1))
        elif interaction.user == self.p2: await interaction.response.send_modal(TradeOfferModal(self, 2))
        else: await interaction.response.send_message("❌ Not your trade!", ephemeral=True)

    @discord.ui.button(label="🔒 Lock / Unlock", style=discord.ButtonStyle.success)
    async def lock_btn(self, interaction, button):
        if interaction.user == self.p1: self.locked[1] = not self.locked[1]
        elif interaction.user == self.p2: self.locked[2] = not self.locked[2]
        else: return await interaction.response.send_message("❌ Not your trade!", ephemeral=True)
        await interaction.response.defer()
        await self.update_ui(interaction)

    @discord.ui.button(label="❌ Cancel Trade", style=discord.ButtonStyle.danger)
    async def cancel_btn(self, interaction, button):
        if interaction.user not in [self.p1, self.p2]: return await interaction.response.send_message("❌ Not your trade!", ephemeral=True)
        for child in self.children: child.disabled = True
        await interaction.message.edit(embed=discord.Embed(description="🛑 Trade cancelled.", color=discord.Color.red()), view=self)
        self.stop()

class TradeAcceptView(discord.ui.View):
    def __init__(self, p1, p2):
        super().__init__(timeout=60)
        self.p1 = p1
        self.p2 = p2

    @discord.ui.button(label="✅ Accept Trade", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        if interaction.user != self.p2: return await interaction.response.send_message("❌ Only they can accept!", ephemeral=True)
        view = ActiveTradeView(self.p1, self.p2)
        embed = discord.Embed(title="🤝 Active Trade Session", description="Click 'Add Offer' to build your trade.", color=discord.Color.blurple())
        await interaction.response.edit_message(embed=embed, view=view)
        self.stop()

# ========================================================================
# COG CLASS: RPG
# ========================================================================
class RPG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="hunt", description="Hunt for monsters.")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def hunt(self, ctx): 
        await ctx.defer()
        uid = str(ctx.author.id)
        
        if random.randint(1, 100) <= 2:
            prompt = "I just triggered a 1-of-1 ultra rare mythic boss spawn. Generate a unique Boss monster. Output ONLY JSON: {'name': 'string', 'title': 'string', 'value': integer}."
            try:
                res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
                clean = res.replace('```json', '').replace('```', '').strip()
                s, e = clean.find('{'), clean.rfind('}')
                boss_data = json.loads(clean[s:e+1])
                full_name = f"🌌 {boss_data['name']} [{boss_data['title']}] (Mythic 1-of-1)"
                db.setdefault("zoo", {}).setdefault(uid, {})
                db["zoo"][uid][full_name] = db["zoo"][uid].get(full_name, 0) + 1
                save_db(db)
                embed = discord.Embed(title="🚨 MYTHIC ANOMALY 🚨", description=f"Captured: **{full_name}**\nValue: {boss_data['value']:,} 🪙", color=discord.Color.magenta())
                embed.set_image(url="https://media.giphy.com/media/l41YkxvU8c7J7Bba0/giphy.gif")
                return await ctx.send(embed=embed)
            except: pass

        rarities = list(MONSTERS.keys()); weights = [MONSTERS[r]["chance"] for r in rarities]
        caught_rarity = random.choices(rarities, weights=weights, k=1)[0]
        caught_mob = random.choice(MONSTERS[caught_rarity]["mobs"])
        
        prompt2 = f"Generate nature for {caught_mob} e.g. [The Brave]. Return ONLY the bracketed string."
        try:
            nature = await ask_groq([{"role": "user", "content": prompt2}], inject_personality=False)
            if not nature.startswith('['): nature = f"[{nature}]"
        except: nature = "[The Average]"

        full_name = f"{caught_mob} {nature}"
        db.setdefault("zoo", {}).setdefault(uid, {})[full_name] = db["zoo"][uid].get(full_name, 0) + 1
        save_db(db)

        colors = {"Common": 0x95a5a6, "Uncommon": 0x2ecc71, "Rare": 0x3498db, "Epic": 0x9b59b6, "Legendary": 0xf1c40f}
        embed = discord.Embed(title="🏹 The Hunt!", description=f"You caught a **{full_name}**!\n**Rarity:** {caught_rarity}", color=colors[caught_rarity])
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="zoo", description="View your monsters.")
    async def zoo(self, ctx, member: discord.Member = None):
        await ctx.defer()
        target = member or ctx.author
        uid = str(target.id)
        zoo_inv = db.get("zoo", {}).get(uid, {})
        if not zoo_inv: return await ctx.send("🐾 Zoo is empty.")
        lines = [f"**{mob}** x{count}" for mob, count in zoo_inv.items()]
        chunks = [lines[i:i + 10] for i in range(0, len(lines), 10)]
        embeds = [discord.Embed(title=f"🐾 {target.name}'s Bestiary", description="\n".join(chunk), color=0x27ae60) for chunk in chunks]
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))

    @commands.hybrid_command(name="fuse_monster", description="Fuse two monsters.")
    async def fuse_monster(self, ctx, mob1: str, mob2: str):
        await ctx.defer()
        uid = str(ctx.author.id)
        zoo_inv = db.setdefault("zoo", {}).get(uid, {})
        exact_m1 = next((m for m in zoo_inv if mob1.lower() in m.lower()), None)
        exact_m2 = next((m for m in zoo_inv if mob2.lower() in m.lower()), None)
        if not exact_m1 or not exact_m2 or (exact_m1 == exact_m2 and zoo_inv[exact_m1] < 2):
            return await ctx.send("❌ You don't own these.")
        prompt = f"Fuse {exact_m1} and {exact_m2}. Return JSON: {'name': 'string', 'desc': 'string'}."
        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            clean = res.replace('```json', '').replace('```', '').strip()
            chimera = json.loads(clean[clean.find('{'):clean.rfind('}')+1])
            zoo_inv[exact_m1] -= 1; zoo_inv[exact_m2] -= 1
            if zoo_inv[exact_m1] <= 0: del zoo_inv[exact_m1]
            if zoo_inv[exact_m2] <= 0: del zoo_inv[exact_m2]
            full_n = f"🧬 {chimera['name']} (Chimera)"
            zoo_inv[full_n] = zoo_inv.get(full_n, 0) + 1
            save_db(db)
            await ctx.send(embed=discord.Embed(title="🧬 MUTATION SUCCESS", description=f"Created **{full_n}**\n*{chimera['desc']}*", color=0x6c5ce7))
        except: await ctx.send("❌ Mutation failed.")

    @commands.hybrid_command(name="sell_monster", description="Sell to Black Market.")
    async def sell_monster(self, ctx, exact_name: str, amount: int = 1):
        await ctx.defer(); uid = str(ctx.author.id); zoo_inv = db.setdefault("zoo", {}).get(uid, {})
        found_mob = next((m for m in zoo_inv if exact_name.lower() in m.lower()), None)
        if not found_mob or zoo_inv[found_mob] < amount: return await ctx.send("❌ You don't own that.")
        base = 10000000 if "Mythic" in found_mob else 1500
        prompt = f"Sell {amount}x {found_mob}. Return JSON array of 3 buyers: {'buyer': 'str', 'quote': 'str', 'offer': int}."
        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            buyers = json.loads(res[res.find('['):res.rfind(']')+1])
            embed = discord.Embed(title="🕴️ Black Market", description=f"Selling **{amount}x {found_mob}**", color=0x2c3e50)
            for i, b in enumerate(buyers): embed.add_field(name=f"Buyer {i+1}: {b['buyer']}", value=f"💰 {b['offer']:,} 🪙\n*\"{b['quote']}\"*", inline=False)
            await ctx.send(embed=embed, view=BlackMarketView(ctx, uid, found_mob, amount, buyers))
        except: await ctx.send("❌ Market closed.")

    @commands.hybrid_group(name="lootbox")
    async def lootbox(self, ctx):
        if ctx.invoked_subcommand is None: await ctx.send("Use `/lootbox buy` or `/lootbox open`.")

    @lootbox.command(name="buy")
    async def lootbox_buy(self, ctx, amount: int = 1):
        await ctx.defer(); uid = str(ctx.author.id); cost = 100000 * amount
        if db.setdefault("economy", {}).get(uid, 0) < cost: return await ctx.send("❌ Not enough coins.")
        db["economy"][uid] -= cost; db.setdefault("lootboxes", {})[uid] = db.get("lootboxes", {}).get(uid, 0) + amount; save_db(db)
        await ctx.send(f"🎁 Bought {amount}x Lootboxes!")

    @lootbox.command(name="open")
    async def lootbox_open(self, ctx):
        await ctx.defer(); uid = str(ctx.author.id)
        if db.setdefault("lootboxes", {}).get(uid, 0) <= 0: return await ctx.send("❌ No boxes!")
        db["lootboxes"][uid] -= 1
        await ctx.send("🎁 Opening...", delete_after=1); await asyncio.sleep(1.5)
        coins = random.randint(10000, 250000); mob = f"🐲 Dragon [Box]"
        db.setdefault("economy", {})[uid] += coins; db.setdefault("zoo", {}).setdefault(uid, {})[mob] = db["zoo"][uid].get(mob, 0) + 1; save_db(db)
        await ctx.send(f"✨ Found {coins:,} coins and a {mob}!")

    @commands.hybrid_command(name="rank")
    async def rank(self, ctx, m: discord.Member = None): 
        await ctx.defer(); t = m or ctx.author; l = db.setdefault("levels", {}).setdefault(str(t.id), {"xp": 0, "level": 1})
        req = int(150 * (l['level'] ** 1.5))
        await ctx.send(embed=discord.Embed(title=f"Rank: {t.name}", description=f"⭐ Lvl: {l['level']}\n✨ XP: {l['xp']}/{req}", color=0x3498db))

async def setup(bot):
    await bot.add_cog(RPG(bot))
