import discord
from discord.ext import commands
import random
import json
import asyncio
import re
from core import db, save_db, get_gif, ask_groq, ai_client
from ui import PaginationView 

# ========================================================================
# MONSTER GACHA SYSTEM (Upgraded with Mythic & Secret)
# ========================================================================
MONSTERS = {
    "Common": {"chance": 50, "value": 1500, "mobs": ["🟢 Slime", "🦇 Cave Bat", "🐀 Plague Rat"]},
    "Uncommon": {"chance": 25, "value": 5000, "mobs": ["👺 Goblin", "🐺 Dire Wolf", "💀 Skeleton Warrior"]},
    "Rare": {"chance": 12, "value": 25000, "mobs": ["👹 Orc Brute", "🗿 Stone Gargoyle", "👻 Cursed Wraith"]},
    "Epic": {"chance": 8, "value": 100000, "mobs": ["🐉 Lesser Dragon", "🦅 Griffin", "🐍 Basilisk"]},
    "Legendary": {"chance": 3.5, "value": 1000000, "mobs": ["🔥 Immortal Phoenix", "🐙 Abyssal Kraken", "⚡ Storm Behemoth"]},
    "Mythic": {"chance": 1.2, "value": 10000000, "mobs": ["🌌 Astral Devourer", "☠️ Lich King", "👁️ Eldritch Watcher"]},
    "Secret": {"chance": 0.3, "value": 50000000, "mobs": ["💠 The Creator", "♾️ Omega Entity", "👑 Soul Sovereign"]}
}

# ========================================================================
# LOOTBOX CONFIGURATION
# ========================================================================
LOOTBOXES = {
    "wooden": {
        "price": 25000, 
        "name": "🪵 Wooden Box", 
        "coin_range": (5000, 15000), 
        "xp_range": (50, 150), 
        "rarities": ["Common", "Uncommon", "Rare"], 
        "weights": [70, 25, 5]
    },
    "mystic": {
        "price": 150000, 
        "name": "🔮 Mystic Box", 
        "coin_range": (30000, 100000), 
        "xp_range": (200, 500), 
        "rarities": ["Uncommon", "Rare", "Epic", "Legendary"], 
        "weights": [40, 40, 15, 5]
    },
    "abyssal": {
        "price": 1000000, 
        "name": "🌌 Abyssal Box", 
        "coin_range": (200000, 800000), 
        "xp_range": (1000, 2500), 
        "rarities": ["Rare", "Epic", "Legendary", "Mythic", "Secret"], 
        "weights": [20, 40, 30, 8, 2]
    }
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

        db["zoo"][self.uid][self.mob_name] -= self.amount
        if db["zoo"][self.uid][self.mob_name] <= 0:
            del db["zoo"][self.uid][self.mob_name]
            
        db.setdefault("economy", {})[self.uid] = db["economy"].get(self.uid, 0) + payout
        save_db(db)

        for child in self.children: 
            child.disabled = True
        
        embed = discord.Embed(
            title="🤝 Deal Closed!", 
            description=f"You sold **{self.amount}x {self.mob_name}** to **{buyer['buyer']}** for **{payout:,} 🪙**!\n\n🗣️ *\"{buyer['quote']}\"*", 
            color=discord.Color.green()
        )
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
        self.player_num = player_num 

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        a_type = self.asset_type.value.strip().lower()
        a_name = self.asset_name.value.strip()
        
        try: amt = int(self.amount.value.strip())
        except ValueError: return await interaction.followup.send("❌ Amount must be a valid number.", ephemeral=True)

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
            return await interaction.followup.send("❌ Invalid type. Use 'coins', 'item', or 'monster'.", ephemeral=True)

        self.view.locked = {1: False, 2: False}
        await self.view.update_ui(interaction)

class ActiveTradeView(discord.ui.View):
    def __init__(self, p1, p2):
        super().__init__(timeout=300)
        self.p1 = p1
        self.p2 = p2
        self.offers = {1: {"coins": 0, "items": {}, "monsters": {}}, 2: {"coins": 0, "items": {}, "monsters": {}}}
        self.locked = {1: False, 2: False}

    def format_offer(self, p_num):
        o = self.offers[p_num]
        lines = [f"🪙 **Coins:** {o['coins']:,}"]
        if o["items"]: lines.append("🎒 **Items:** " + ", ".join([f"{k} x{v}" for k, v in o["items"].items()]))
        if o["monsters"]: lines.append("🐾 **Monsters:** " + ", ".join([f"{k} x{v}" for k, v in o["monsters"].items()]))
        status = "✅ Locked" if self.locked[p_num] else "⏳ Trading..."
        return "\n".join(lines) + f"\n\n**Status:** {status}"

    async def update_ui(self, interaction):
        embed = discord.Embed(title="🤝 Active Trade Session", color=discord.Color.blurple())
        embed.add_field(name=f"Player 1: {self.p1.name}", value=self.format_offer(1), inline=False)
        embed.add_field(name=f"Player 2: {self.p2.name}", value=self.format_offer(2), inline=False)
        
        if self.locked[1] and self.locked[2]: await self.execute_trade(interaction)
        else: await interaction.message.edit(embed=embed, view=self)

    async def execute_trade(self, interaction):
        u1, u2 = str(self.p1.id), str(self.p2.id)
        
        for p_num, uid, target_uid in [(1, u1, u2), (2, u2, u1)]:
            o = self.offers[p_num]
            if o["coins"] > 0:
                db["economy"][uid] -= o["coins"]
                db.setdefault("economy", {})[target_uid] = db["economy"].get(target_uid, 0) + o["coins"]
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
        await interaction.message.edit(embed=discord.Embed(title="🎉 Trade Successful!", description="All assets were securely transferred.", color=discord.Color.green()), view=self)
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
        await interaction.message.edit(embed=discord.Embed(description="🛑 Trade cancelled by a participant.", color=discord.Color.red()), view=self)
        self.stop()

class TradeAcceptView(discord.ui.View):
    def __init__(self, p1, p2):
        super().__init__(timeout=60)
        self.p1 = p1
        self.p2 = p2

    @discord.ui.button(label="✅ Accept Trade", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        if interaction.user != self.p2: return await interaction.response.send_message("❌ Only the requested user can accept!", ephemeral=True)
        view = ActiveTradeView(self.p1, self.p2)
        embed = discord.Embed(title="🤝 Active Trade Session", description="Click 'Add Offer' to build your trade.", color=discord.Color.blurple())
        await interaction.response.edit_message(embed=embed, view=view)
        self.stop()


# ========================================================================
# UI CLASS: Server Raid Boss View
# ========================================================================
class BossRaidView(discord.ui.View):
    def __init__(self, boss_name, max_hp):
        super().__init__(timeout=600) # 10 minute raid timer
        self.boss_name = boss_name
        self.max_hp = max_hp
        self.hp = max_hp
        self.participants = {} 
        self.fainted = set()   

    async def update_raid(self, interaction: discord.Interaction):
        if self.hp <= 0:
            for child in self.children: child.disabled = True
            
            leaderboard = sorted(self.participants.items(), key=lambda x: x[1], reverse=True)
            desc = f"💀 **{self.boss_name} HAS BEEN SLAIN!**\n\n🏆 **Top Damage Dealers:**\n"
            
            for i, (uid, dmg) in enumerate(leaderboard[:5]):
                payout = dmg * 10 
                db.setdefault("economy", {})[uid] = db.get("economy", {}).get(uid, 0) + payout
                desc += f"**{i+1}.** <@{uid}> - {dmg:,} DMG (*Won {payout:,} 🪙*)\n"
            
            save_db(db)
            embed = discord.Embed(title="🎉 RAID COMPLETE", description=desc, color=discord.Color.green())
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            ratio = max(self.hp / self.max_hp, 0.0)
            filled = int(ratio * 15)
            hp_bar = f"[{'█' * filled}{'░' * (15 - filled)}]"
            
            embed = discord.Embed(title=f"⚔️ RAID BOSS: {self.boss_name}", color=discord.Color.red())
            embed.add_field(name="HP", value=f"`{hp_bar}`\n**{self.hp:,} / {self.max_hp:,}**", inline=False)
            
            if self.participants:
                top_player = max(self.participants, key=self.participants.get)
                top_member = interaction.guild.get_member(int(top_player))
                embed.set_footer(text=f"👑 Aggro: {top_member.name if top_member else 'Unknown'}")
                
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Strike ⚔️", style=discord.ButtonStyle.danger)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        if uid in self.fainted:
            return await interaction.response.send_message("💀 You are fainted! Wait for the medics.", ephemeral=True)

        user_level = db.setdefault("levels", {}).setdefault(uid, {"xp": 0, "level": 1})["level"]
        damage = random.randint(50, 150) + (user_level * 5)
        
        if random.randint(1, 100) <= 10:
            self.fainted.add(uid)
            await interaction.response.send_message(f"💥 **CRITICAL HIT!** {self.boss_name} slammed you! You are fainted!", ephemeral=True)
        else:
            self.hp -= damage
            self.participants[uid] = self.participants.get(uid, 0) + damage
            await self.update_raid(interaction)


# ========================================================================
# COG CLASS: RPG
# ========================================================================
class RPG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="hunt", description="Hunt for monsters out in the wild.")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def hunt(self, ctx): 
        await ctx.defer()
        uid = str(ctx.author.id)
        
        if random.randint(1, 100) <= 2 and ai_client:
            prompt = """I just triggered a 1-of-1 ultra rare mythic boss spawn. Generate a unique Boss monster. 
            Output ONLY a raw, perfectly formatted JSON object exactly like this: 
            {"name": "String", "title": "String", "value": 15000000}"""
            
            try:
                res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
                start, end = res.find('{'), res.rfind('}')
                if start == -1 or end == -1: raise Exception("JSON format hallucination.")
                
                boss_data = json.loads(res[start:end+1])
                full_name = f"🌌 {boss_data['name']} [{boss_data['title']}] (Mythic 1-of-1)"
                
                db.setdefault("zoo", {}).setdefault(uid, {})
                db["zoo"][uid][full_name] = db["zoo"][uid].get(full_name, 0) + 1
                save_db(db)
                
                embed = discord.Embed(title="🚨 MYTHIC ANOMALY 🚨", description=f"The fabric of reality tore open and you captured a 1-of-1 Mythic Boss!\n\n**Captured:** {full_name}\n**Value:** {boss_data['value']:,} 🪙", color=discord.Color.magenta())
                embed.set_image(url="https://media.giphy.com/media/l41YkxvU8c7J7Bba0/giphy.gif")
                return await ctx.send(embed=embed)
            except Exception as e: 
                print(f"⚠️ AI Mythic Generation Failed: {e}")

        rarities = list(MONSTERS.keys())
        weights = [MONSTERS[r]["chance"] for r in rarities]
        caught_rarity = random.choices(rarities, weights=weights, k=1)[0]
        caught_mob = random.choice(MONSTERS[caught_rarity]["mobs"])
        
        nature = "[The Average]"
        if ai_client:
            prompt2 = f"Generate a short title or nature for a {caught_mob} e.g. [The Brave]. Return ONLY the bracketed string. Nothing else."
            try:
                res_nature = await ask_groq([{"role": "user", "content": prompt2}], inject_personality=False)
                match = re.search(r'\[.*?\]', res_nature)
                if match: nature = match.group(0)
                else: nature = f"[{res_nature.strip()}]"
            except: pass

        full_name = f"{caught_mob} {nature}"
        
        db.setdefault("zoo", {}).setdefault(uid, {})[full_name] = db["zoo"][uid].get(full_name, 0) + 1
        save_db(db)

        colors = {"Common": 0x95a5a6, "Uncommon": 0x2ecc71, "Rare": 0x3498db, "Epic": 0x9b59b6, "Legendary": 0xf1c40f, "Mythic": 0xe91e63, "Secret": 0x00d2d3}
        embed = discord.Embed(title="🏹 The Hunt!", description=f"You ventured into the wild and caught a **{full_name}**!\n\n**Rarity:** {caught_rarity}\n**Base Value:** {MONSTERS[caught_rarity]['value']:,} 🪙", color=colors.get(caught_rarity, 0x95a5a6))
        await ctx.send(embed=embed)


    @commands.hybrid_command(name="zoo", description="View your captured monsters.")
    async def zoo(self, ctx, member: discord.Member = None):
        await ctx.defer()
        target = member or ctx.author
        uid = str(target.id)
        
        zoo_inv = db.get("zoo", {}).get(uid, {})
        if not zoo_inv: return await ctx.send(embed=discord.Embed(description="🐾 This user's zoo is completely empty.", color=discord.Color.red()))
            
        lines = [f"**{mob}** x{count}" for mob, count in zoo_inv.items()]
        chunks = [lines[i:i + 10] for i in range(0, len(lines), 10)]
        embeds = [discord.Embed(title=f"🐾 {target.name}'s Bestiary ({i+1}/{len(chunks)})", description="\n".join(chunk), color=0x27ae60) for i, chunk in enumerate(chunks)]
        
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))


    @commands.hybrid_command(name="fuse_monster", description="Fuse two monsters to create a powerful Chimera.")
    async def fuse_monster(self, ctx, mob1: str, mob2: str):
        await ctx.defer()
        uid = str(ctx.author.id)
        zoo_inv = db.setdefault("zoo", {}).get(uid, {})
        
        exact_m1 = next((m for m in zoo_inv if mob1.lower() in m.lower()), None)
        exact_m2 = next((m for m in zoo_inv if mob2.lower() in m.lower()), None)
        
        if not exact_m1 or not exact_m2 or (exact_m1 == exact_m2 and zoo_inv[exact_m1] < 2):
            return await ctx.send(embed=discord.Embed(description="❌ You don't own the required monsters for this fusion.", color=discord.Color.red()))
            
        prompt = f"""I am fusing '{exact_m1}' and '{exact_m2}'. Generate a horrific, overpowered hybrid Chimera monster. 
        Output ONLY a valid JSON object exactly like this: {{"name": "String", "desc": "String"}}"""
        
        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            start, end = res.find('{'), res.rfind('}')
            if start == -1 or end == -1: raise Exception("AI JSON format error.")
            
            chimera = json.loads(res[start:end+1])
            
            zoo_inv[exact_m1] -= 1
            zoo_inv[exact_m2] -= 1
            if zoo_inv[exact_m1] <= 0: del zoo_inv[exact_m1]
            if zoo_inv[exact_m2] <= 0: del zoo_inv[exact_m2]
            
            full_n = f"🧬 {chimera['name']} (Chimera)"
            zoo_inv[full_n] = zoo_inv.get(full_n, 0) + 1
            save_db(db)
            
            embed = discord.Embed(title="🧬 MUTATION SUCCESSFUL", description=f"You successfully fused the monsters and created **{full_n}**!\n\n*{chimera['desc']}*", color=0x6c5ce7)
            await ctx.send(embed=embed)
        except Exception as e: 
            await ctx.send(embed=discord.Embed(description="❌ The mutation chamber exploded due to an AI error. Your monsters are safe.", color=discord.Color.red()))


    @commands.hybrid_command(name="sell_monster", description="Sell a monster to shady buyers on the AI Black Market.")
    async def sell_monster(self, ctx, exact_name: str, amount: int = 1):
        await ctx.defer()
        uid = str(ctx.author.id)
        zoo_inv = db.setdefault("zoo", {}).get(uid, {})
        
        found_mob = next((m for m in zoo_inv if exact_name.lower() in m.lower()), None)
        if not found_mob or zoo_inv[found_mob] < amount: 
            return await ctx.send(embed=discord.Embed(description=f"❌ You don't own {amount}x of that monster.", color=discord.Color.red()))
            
        base = 10000000 if "Mythic" in found_mob else 1500
        total_val = base * amount
        
        prompt = f"""I am selling '{amount}x {found_mob}' (Estimated Base: {total_val}). Generate 3 shady black market buyers. One lowballs, one is fair, one overpays. 
        Output ONLY a JSON array of 3 objects exactly like this:
        [
            {{"buyer": "Name", "quote": "String", "offer": 1000}},
            ...
        ]"""
        
        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            start, end = res.find('['), res.rfind(']')
            if start == -1 or end == -1: raise Exception("AI JSON format error.")
            buyers = json.loads(res[start:end+1])
            
            embed = discord.Embed(title="🕴️ The Black Market", description=f"You brought **{amount}x {found_mob}** to the alleyway.\nThree figures step forward...", color=0x2c3e50)
            for i, b in enumerate(buyers): 
                embed.add_field(name=f"Buyer {i+1}: {b['buyer']}", value=f"💰 **Offer:** {b['offer']:,} 🪙\n🗣️ *\"{b['quote']}\"*", inline=False)
                
            await ctx.send(embed=embed, view=BlackMarketView(ctx, uid, found_mob, amount, buyers))
        except Exception as e: 
            await ctx.send(embed=discord.Embed(description="❌ The black market was raided by the FBI. Try selling later.", color=discord.Color.red()))

    @commands.hybrid_command(name="trade", description="Trade coins, items, and monsters with another player.")
    async def trade(self, ctx, member: discord.Member):
        if member.bot or member == ctx.author: return await ctx.send("❌ You can't trade with a bot or yourself.", ephemeral=True)
        embed = discord.Embed(title="🤝 Trade Request", description=f"{member.mention}, **{ctx.author.name}** wants to trade with you!", color=discord.Color.gold())
        await ctx.send(content=member.mention, embed=embed, view=TradeAcceptView(ctx.author, member))

    @commands.hybrid_command(name="bossfight", description="Summon a massive server-wide Raid Boss.")
    @commands.cooldown(1, 3600, commands.BucketType.guild)
    async def bossfight(self, ctx):
        await ctx.defer()
        boss_names = ["The Abyssal Devourer", "Mecha-Godzilla V2", "Fallen Seraphim", "Cursed Lich King"]
        boss_name = random.choice(boss_names)
        max_hp = 10000 + (len(ctx.guild.members) * 100) 
        
        view = BossRaidView(boss_name, max_hp)
        ratio = max(view.hp / view.max_hp, 0.0)
        filled = int(ratio * 15)
        hp_bar = f"[{'█' * filled}{'░' * (15 - filled)}]"
        
        embed = discord.Embed(title=f"⚔️ RAID BOSS SPAWNED", description=f"**{boss_name}** has invaded the server!\nClick **Strike** to attack. Damage scales with your `/rank`!", color=discord.Color.red())
        embed.add_field(name="HP", value=f"`{hp_bar}`\n**{view.hp:,} / {view.max_hp:,}**", inline=False)
        embed.set_image(url="https://media.giphy.com/media/xT9IgzoKnwFNmISR8I/giphy.gif")
        
        await ctx.send(embed=embed, view=view)


    # ========================================================================
    # UPGRADED LOOTBOX SYSTEM
    # ========================================================================
    @commands.hybrid_group(name="lootbox", description="Manage, buy, and open Lootboxes.")
    async def lootbox(self, ctx):
        if ctx.invoked_subcommand is None: 
            embed = discord.Embed(title="🎁 Lootbox Shop", description="Use `/lootbox buy <type> [amount]` or `/lootbox open <type> [amount]`.\n\n**Available Boxes:**", color=discord.Color.gold())
            for key, val in LOOTBOXES.items():
                embed.add_field(name=val['name'], value=f"💰 Cost: **{val['price']:,} 🪙**\n✨ Drops: {', '.join(val['rarities'])}", inline=False)
            await ctx.send(embed=embed)

    @lootbox.command(name="buy", description="Purchase a lootbox (wooden, mystic, abyssal).")
    async def lootbox_buy(self, ctx, box_type: str, amount: int = 1):
        await ctx.defer()
        uid = str(ctx.author.id)
        box_type = box_type.lower()
        
        if box_type not in LOOTBOXES:
            return await ctx.send(embed=discord.Embed(description="❌ Invalid box type! Choose: `wooden`, `mystic`, or `abyssal`.", color=discord.Color.red()))
            
        if amount < 1 or amount > 50:
            return await ctx.send(embed=discord.Embed(description="❌ You can only buy between 1 and 50 boxes at a time.", color=discord.Color.red()))

        cost = LOOTBOXES[box_type]["price"] * amount
        
        if db.setdefault("economy", {}).get(uid, 0) < cost: 
            return await ctx.send(embed=discord.Embed(description=f"❌ You need **{cost:,} 🪙** to buy {amount}x {LOOTBOXES[box_type]['name']}.", color=discord.Color.red()))
            
        db["economy"][uid] -= cost
        
        # Safe migration for old DB format
        user_boxes = db.setdefault("lootboxes", {}).setdefault(uid, {})
        if isinstance(user_boxes, int): 
            db["lootboxes"][uid] = {"mystic": user_boxes}
            
        db["lootboxes"][uid][box_type] = db["lootboxes"][uid].get(box_type, 0) + amount
        save_db(db)
        
        await ctx.send(embed=discord.Embed(description=f"🎁 Successfully purchased **{amount}x {LOOTBOXES[box_type]['name']}**!", color=discord.Color.green()))

    @lootbox.command(name="open", description="Open your lootboxes (up to 10 at once).")
    async def lootbox_open(self, ctx, box_type: str, amount: int = 1):
        await ctx.defer()
        uid = str(ctx.author.id)
        box_type = box_type.lower()
        
        if box_type not in LOOTBOXES:
            return await ctx.send(embed=discord.Embed(description="❌ Invalid box type! Choose: `wooden`, `mystic`, or `abyssal`.", color=discord.Color.red()))
            
        if amount < 1 or amount > 10:
            return await ctx.send(embed=discord.Embed(description="❌ You can only open between 1 and 10 boxes at a time to prevent spam.", color=discord.Color.red()))

        # Safe migration check
        user_boxes = db.setdefault("lootboxes", {}).setdefault(uid, {})
        if isinstance(user_boxes, int):
            db["lootboxes"][uid] = {"mystic": user_boxes}

        if db["lootboxes"][uid].get(box_type, 0) < amount: 
            return await ctx.send(embed=discord.Embed(description=f"❌ You don't have enough {LOOTBOXES[box_type]['name']}s. Check `/lootbox inventory`.", color=discord.Color.red()))
            
        db["lootboxes"][uid][box_type] -= amount
        
        msg = await ctx.send(embed=discord.Embed(description=f"🎁 **Opening {amount}x {LOOTBOXES[box_type]['name']}...** Unlocking the seals...", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        
        total_coins = 0
        total_xp = 0
        mobs_caught = {}
        
        config = LOOTBOXES[box_type]
        
        for _ in range(amount):
            # Roll Coins & XP
            total_coins += random.randint(*config["coin_range"])
            total_xp += random.randint(*config["xp_range"])
            
            # Roll Mob
            rarity = random.choices(config["rarities"], weights=config["weights"], k=1)[0]
            mob = f"{random.choice(MONSTERS[rarity]['mobs'])} [Boxed]"
            mobs_caught[mob] = mobs_caught.get(mob, 0) + 1
            
            # Save mob
            db.setdefault("zoo", {}).setdefault(uid, {})[mob] = db["zoo"][uid].get(mob, 0) + 1

        db.setdefault("economy", {})[uid] += total_coins
        db.setdefault("levels", {}).setdefault(uid, {"xp": 0, "level": 1})["xp"] += total_xp
        save_db(db)
        
        mob_summary = "\n".join([f"🐾 **{m}** x{c}" for m, c in mobs_caught.items()])
        
        embed = discord.Embed(title="✨ LOOTBOXES OPENED! ✨", color=discord.Color.purple())
        embed.add_field(name="💰 Total Coins", value=f"+{total_coins:,}", inline=True)
        embed.add_field(name="📈 Total XP", value=f"+{total_xp:,}", inline=True)
        embed.add_field(name="🐉 Monsters Found", value=mob_summary, inline=False)
        
        await msg.edit(embed=embed)

    @lootbox.command(name="inventory", aliases=["inv"], description="Check how many lootboxes you own.")
    async def lootbox_inventory(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        
        user_boxes = db.setdefault("lootboxes", {}).setdefault(uid, {})
        if isinstance(user_boxes, int): 
            db["lootboxes"][uid] = {"mystic": user_boxes}
            user_boxes = db["lootboxes"][uid]
            
        if not any(user_boxes.values()):
            return await ctx.send(embed=discord.Embed(description="📦 You have absolutely zero lootboxes. Go buy some!", color=discord.Color.red()))
            
        desc = ""
        for b_type, count in user_boxes.items():
            if count > 0:
                name = LOOTBOXES.get(b_type, {"name": b_type})["name"]
                desc += f"{name}: **{count}**\n"
                
        await ctx.send(embed=discord.Embed(title="📦 Your Lootbox Stash", description=desc, color=discord.Color.blue()))


    # ========================================================================
    # LEVELING & QUESTS
    # ========================================================================
    @commands.hybrid_command(name="quest", description="Go on an epic quest to earn XP and level up.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def quest(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        level_data = db.setdefault("levels", {}).setdefault(uid, {"xp": 0, "level": 1})
        
        if level_data["level"] >= 13000:
            return await ctx.send(embed=discord.Embed(description="🛑 **Max Level 13,000 Reached!** You are already at the pinnacle.", color=discord.Color.red()))
        
        xp_gained = random.randint(300, 800)
        level_data["xp"] += xp_gained
        
        req_xp = int(150 * (level_data['level'] ** 1.5))
        leveled_up = False
        
        while level_data["xp"] >= req_xp:
            level_data["xp"] -= req_xp
            level_data["level"] += 1
            leveled_up = True
            req_xp = int(150 * (level_data['level'] ** 1.5))
            
        save_db(db)
        
        desc = f"🗡️ **Dungeon run complete!** You braved the depths and earned **{xp_gained} XP**!"
        if leveled_up:
            desc += f"\n\n🎉 **LEVEL UP!** You grew stronger and are now Level **{level_data['level']}**!"
            
        await ctx.send(embed=discord.Embed(description=desc, color=discord.Color.orange()))

    @commands.hybrid_command(name="rank", description="Check your current RPG Level and XP.")
    async def rank(self, ctx, m: discord.Member = None): 
        await ctx.defer()
        target = m or ctx.author
        
        level_data = db.setdefault("levels", {}).setdefault(str(target.id), {"xp": 0, "level": 1})
        req = int(150 * (level_data['level'] ** 1.5))
        
        embed = discord.Embed(title=f"Rank: {target.name}", description=f"⭐ Level: **{level_data['level']}**\n✨ XP: **{level_data['xp']} / {req}**", color=0x3498db)
        embed.set_thumbnail(url=str(target.display_avatar.url))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard_levels", aliases=["lbl"], description="View the top-ranked players by RPG Level.")
    async def leaderboard_levels(self, ctx): 
        await ctx.defer()
        sorted_levels = sorted(db.get("levels", {}).items(), key=lambda x: (x[1].get("level", 1), x[1].get("xp", 0)), reverse=True)
        
        if not sorted_levels: 
            return await ctx.send(embed=discord.Embed(description="No ranking data available yet.", color=discord.Color.red()))
            
        chunks = [sorted_levels[i:i + 10] for i in range(0, len(sorted_levels), 10)]
        embeds = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(title=f"🏆 RPG Level Leaderboard ({i+1}/{len(chunks)})", color=discord.Color.gold())
            for j, (uid, data) in enumerate(chunk): 
                embed.add_field(name=f"#{i*10 + j + 1}", value=f"<@{uid}> - Level **{data.get('level', 1)}** (XP: {data.get('xp', 0)})", inline=False)
            embeds.append(embed)
            
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))

    @commands.hybrid_command(name="givexp", description="Give XP to a user (Admin Only).")
    @commands.has_permissions(administrator=True)
    async def givexp(self, ctx, member: discord.Member, amount: int): 
        await ctx.defer()
        uid = str(member.id)
        level_data = db.setdefault("levels", {}).setdefault(uid, {"xp": 0, "level": 1})
        level_data["xp"] += amount
        
        req_xp = int(150 * (level_data['level'] ** 1.5))
        while level_data["xp"] >= req_xp:
            level_data["xp"] -= req_xp
            level_data["level"] += 1
            req_xp = int(150 * (level_data['level'] ** 1.5))
            
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"📈 Granted **{amount:,} XP** to {member.mention}. They are now Level **{level_data['level']}**.", color=discord.Color.green()))


async def setup(bot):
    await bot.add_cog(RPG(bot))
