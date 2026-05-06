import discord
from discord.ext import commands
import random
import json
import asyncio
import re
from core import db, save_db, get_gif, ask_groq, ai_client
from ui import PaginationView 

# ========================================================================
# MONSTER GACHA SYSTEM, STATS & MULTIPLIERS
# ========================================================================
MONSTERS = {
    "Common": {"chance": 50, "value": 1500, "hp": 100, "dmg": 25, "xp_mult": 1.05, "mobs": ["🟢 Slime", "🦇 Cave Bat", "🐀 Plague Rat"]},
    "Uncommon": {"chance": 25, "value": 5000, "hp": 250, "dmg": 60, "xp_mult": 1.10, "mobs": ["👺 Goblin", "🐺 Dire Wolf", "💀 Skeleton Warrior"]},
    "Rare": {"chance": 12, "value": 25000, "hp": 600, "dmg": 150, "xp_mult": 1.25, "mobs": ["👹 Orc Brute", "🗿 Stone Gargoyle", "👻 Cursed Wraith"]},
    "Epic": {"chance": 8, "value": 100000, "hp": 1500, "dmg": 400, "xp_mult": 1.50, "mobs": ["🐉 Lesser Dragon", "🦅 Griffin", "🐍 Basilisk"]},
    "Legendary": {"chance": 3.5, "value": 1000000, "hp": 4000, "dmg": 1000, "xp_mult": 2.0, "mobs": ["🔥 Immortal Phoenix", "🐙 Abyssal Kraken", "⚡ Storm Behemoth"]},
    "Mythic": {"chance": 1.2, "value": 10000000, "hp": 10000, "dmg": 2500, "xp_mult": 3.0, "mobs": ["🌌 Astral Devourer", "☠️ Lich King", "👁️ Eldritch Watcher"]},
    "Secret": {"chance": 0.3, "value": 50000000, "hp": 25000, "dmg": 6000, "xp_mult": 6.0, "mobs": ["💠 The Creator", "♾️ Omega Entity", "👑 Soul Sovereign"]}
}

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
# HELPER FUNCTIONS
# ========================================================================
def get_mob_stats(mob_name):
    """Dynamically finds the Rarity, HP, DMG, and XP of a monster by its name."""
    for rarity, data in MONSTERS.items():
        if any(base_mob in mob_name for base_mob in data["mobs"]):
            return rarity, data["hp"], data["dmg"], data["xp_mult"]
            
    # Fallbacks for fusions or dynamic names
    if "Mythic" in mob_name: return "Mythic", 10000, 2500, 3.0
    if "Secret" in mob_name or "Chimera" in mob_name: return "Secret", 25000, 6000, 6.0
    return "Common", 100, 25, 1.05

def generate_health_bar(hp, max_hp):
    if hp <= 0: return "`[💀 DEFEATED  ]`"
    ratio = max(hp / max_hp, 0.0)
    filled = int(ratio * 10)
    return f"`[{'█' * filled}{'░' * (10 - filled)}]`"

# ========================================================================
# UI CLASSES: AI 3V3 BATTLE ENGINE
# ========================================================================
class TeamBattleView(discord.ui.View):
    def __init__(self, ctx, p1_name, p2_name, t1, t2, is_pvp=False):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.p1_name = p1_name
        self.p2_name = p2_name
        self.t1 = t1  # List of dicts: name, hp, max_hp, dmg, move
        self.t2 = t2
        self.is_pvp = is_pvp
        self.round_num = 1

    def build_team_string(self, team):
        desc = ""
        for m in team:
            bar = generate_health_bar(m['hp'], m['max_hp'])
            desc += f"**{m['name']}**\n{bar} **{m['hp']} / {m['max_hp']}**\n"
        return desc if desc else "💀 *Wiped Out*"

    @discord.ui.button(label="⚔️ Execute Next Round", style=discord.ButtonStyle.danger)
    async def next_round(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        t1_alive = [m for m in self.t1 if m['hp'] > 0]
        t2_alive = [m for m in self.t2 if m['hp'] > 0]
        
        if not t1_alive or not t2_alive:
            return # Battle already over
            
        combat_log = []
        
        # TEAM 1 ATTACKS
        for m in t1_alive:
            if not t2_alive: break
            target = random.choice(t2_alive)
            dmg = int(m['dmg'] * random.uniform(0.85, 1.15))
            
            # 10% Critical Hit Chance
            is_crit = random.randint(1, 100) <= 10
            if is_crit: dmg = int(dmg * 1.5)
            
            target['hp'] = max(0, target['hp'] - dmg)
            crit_text = " (CRITICAL HIT!)" if is_crit else ""
            combat_log.append(f"[{self.p1_name}]'s {m['name']} used '{m['move']}' on {target['name']} for {dmg} damage!{crit_text}")
            if target['hp'] == 0: t2_alive.remove(target)

        # TEAM 2 ATTACKS
        for m in t2_alive:
            if not t1_alive: break
            target = random.choice(t1_alive)
            dmg = int(m['dmg'] * random.uniform(0.85, 1.15))
            
            is_crit = random.randint(1, 100) <= 10
            if is_crit: dmg = int(dmg * 1.5)
            
            target['hp'] = max(0, target['hp'] - dmg)
            crit_text = " (CRITICAL HIT!)" if is_crit else ""
            combat_log.append(f"[{self.p2_name}]'s {m['name']} used '{m['move']}' on {target['name']} for {dmg} damage!{crit_text}")
            if target['hp'] == 0: t1_alive.remove(target)

        # Re-check alive status after combat phase
        t1_alive = [m for m in self.t1 if m['hp'] > 0]
        t2_alive = [m for m in self.t2 if m['hp'] > 0]
        
        # Generate AI Narration (With Timeout Shield)
        narrative = "The combat was too fast to describe!"
        if ai_client and combat_log:
            prompt = f"Rewrite this raw RPG combat log into a highly epic, fast-paced 2-sentence battle narration:\n\n{chr(10).join(combat_log)}"
            try:
                narrative = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
            except:
                narrative = "💥 The clash was explosive! (AI Narration Timed Out)\n" + "\n".join([f"• {log}" for log in combat_log])

        # Check for Win/Loss
        if not t1_alive or not t2_alive:
            for child in self.children: child.disabled = True
            
            if not t1_alive and not t2_alive:
                narrative += "\n\n🤝 **IT'S A DRAW! Both teams wiped each other out!**"
                color = discord.Color.orange()
            elif not t1_alive:
                narrative += f"\n\n💀 **{self.p1_name} HAS BEEN DEFEATED! {self.p2_name} WINS!**"
                color = discord.Color.red()
            else:
                narrative += f"\n\n🏆 **{self.p2_name} HAS BEEN DEFEATED! {self.p1_name} WINS!**"
                color = discord.Color.green()
                if not self.is_pvp:
                    # PvE Reward
                    reward = 50000 * self.round_num
                    uid = str(self.ctx.author.id)
                    db.setdefault("economy", {})[uid] = db["economy"].get(uid, 0) + reward
                    save_db(db)
                    narrative += f"\n💰 **Loot Earned:** {reward:,} 🪙"
        else:
            color = discord.Color.dark_theme()

        self.round_num += 1
        
        embed = discord.Embed(title=f"⚔️ Round {self.round_num - 1} Clash!", description=narrative, color=color)
        embed.add_field(name=f"🛡️ {self.p1_name}'s Team", value=self.build_team_string(self.t1), inline=True)
        embed.add_field(name=f"👹 {self.p2_name}'s Team", value=self.build_team_string(self.t2), inline=True)
        
        await interaction.message.edit(embed=embed, view=self)


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

        user_zoo = db.setdefault("zoo", {}).setdefault(self.uid, {})
        user_zoo[self.mob_name] -= self.amount
        if user_zoo[self.mob_name] <= 0:
            del user_zoo[self.mob_name]
            
        db.setdefault("economy", {})[self.uid] = db["economy"].get(self.uid, 0) + payout
        
        # Unequip if sold
        team = db.get("team", {}).get(self.uid, {})
        slots_to_clear = [s for s, m in team.items() if m["name"] == self.mob_name and self.mob_name not in user_zoo]
        for s in slots_to_clear: del team[s]
            
        save_db(db)

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
# UI CLASS: Server Raid Boss View
# ========================================================================
class BossRaidView(discord.ui.View):
    def __init__(self, boss_name, max_hp):
        super().__init__(timeout=600)
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

    def build_fighter(self, uid, mob_name):
        """Helper to construct a battle-ready dictionary from a monster name."""
        rarity, hp, dmg, xp = get_mob_stats(mob_name)
        moves = db.setdefault("monster_moves", {}).setdefault(uid, {})
        custom_move = moves.get(mob_name, "Basic Strike")
        
        return {
            "name": mob_name,
            "rarity": rarity,
            "max_hp": hp,
            "hp": hp,
            "dmg": dmg,
            "move": custom_move
        }

    # ========================================================================
    # 3V3 TEAM BATTLES (PvE & PvP)
    # ========================================================================
    @commands.hybrid_command(name="pve", description="Send your equipped team of up to 3 monsters into a wild battle!")
    @commands.cooldown(1, 45, commands.BucketType.member)
    async def pve(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        
        user_team = db.get("team", {}).get(uid, {})
        if not user_team:
            return await ctx.send(embed=discord.Embed(description="❌ You don't have any monsters equipped! Use `/equip <slot> <name>`.", color=discord.Color.red()))
            
        # Build Player 1 Team
        t1 = [self.build_fighter(uid, mob["name"]) for mob in user_team.values()]
        
        # Build AI Team based on player's strength
        t2 = []
        rarities = list(MONSTERS.keys())
        for _ in range(len(t1)):
            enemy_rarity = random.choice(rarities)
            enemy_name = f"{random.choice(MONSTERS[enemy_rarity]['mobs'])} [Wild]"
            
            # AI doesn't have an owner ID, we generate stats purely on name
            r, hp, dmg, xp = get_mob_stats(enemy_name)
            t2.append({"name": enemy_name, "rarity": r, "max_hp": hp, "hp": hp, "dmg": dmg, "move": "Wild Thrash"})

        view = TeamBattleView(ctx, ctx.author.name, "Wild Encounter", t1, t2, is_pvp=False)
        
        embed = discord.Embed(title="🌲 Wild Encounter!", description="Your team stumbled across wild monsters!\nClick **[⚔️ Execute Next Round]** to clash!", color=discord.Color.dark_green())
        embed.add_field(name=f"🛡️ {ctx.author.name}'s Team", value=view.build_team_string(t1), inline=True)
        embed.add_field(name=f"👹 Wild Team", value=view.build_team_string(t2), inline=True)
        
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="pvp", description="Challenge another player's equipped team to a 3v3 duel!")
    @commands.cooldown(1, 60, commands.BucketType.member)
    async def pvp(self, ctx, opponent: discord.Member):
        await ctx.defer()
        u1, u2 = str(ctx.author.id), str(opponent.id)
        
        if u1 == u2 or opponent.bot:
            return await ctx.send("❌ Invalid opponent.")
            
        t1_data = db.get("team", {}).get(u1, {})
        t2_data = db.get("team", {}).get(u2, {})
        
        if not t1_data: return await ctx.send(embed=discord.Embed(description="❌ You have no team equipped!", color=discord.Color.red()))
        if not t2_data: return await ctx.send(embed=discord.Embed(description=f"❌ {opponent.name} has no team equipped!", color=discord.Color.red()))
            
        t1 = [self.build_fighter(u1, mob["name"]) for mob in t1_data.values()]
        t2 = [self.build_fighter(u2, mob["name"]) for mob in t2_data.values()]

        view = TeamBattleView(ctx, ctx.author.name, opponent.name, t1, t2, is_pvp=True)
        
        embed = discord.Embed(title="⚔️ PvP DUEL INITIATED!", description=f"{ctx.author.mention} challenged {opponent.mention} to a team battle!\nClick **[⚔️ Execute Next Round]** to simulate combat!", color=discord.Color.red())
        embed.add_field(name=f"🛡️ {ctx.author.name}'s Team", value=view.build_team_string(t1), inline=True)
        embed.add_field(name=f"🛡️ {opponent.name}'s Team", value=view.build_team_string(t2), inline=True)
        
        await ctx.send(embed=embed, view=view)


    # ========================================================================
    # TEAM MANAGEMENT & UPGRADES
    # ========================================================================
    @commands.hybrid_command(name="equip", description="Equip a monster to your 3-man active team! (Slot 1, 2, or 3)")
    async def equip(self, ctx, slot: int, *, exact_name: str):
        await ctx.defer()
        if slot not in [1, 2, 3]:
            return await ctx.send(embed=discord.Embed(description="❌ Invalid slot! You can only equip to slot `1`, `2`, or `3`.", color=discord.Color.red()))
            
        uid = str(ctx.author.id)
        zoo_inv = db.get("zoo", {}).get(uid, {})
        
        exact_match = next((m for m in zoo_inv if exact_name.lower() in m.lower()), None)
        if not exact_match:
            return await ctx.send(embed=discord.Embed(description=f"❌ You don't own a monster named `{exact_name}` in your zoo.", color=discord.Color.red()))
            
        rarity, _, _, _ = get_mob_stats(exact_match)

        db.setdefault("team", {}).setdefault(uid, {})[str(slot)] = {"name": exact_match, "rarity": rarity}
        save_db(db)
        
        embed = discord.Embed(title="🐾 Pet Equipped!", description=f"You successfully assigned **{exact_match}** ({rarity}) to **Slot {slot}**!\nYour team will fight for you in `/pve` and boost your `/quest` XP.", color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="team", description="Check your current 3v3 equipped team.")
    async def team(self, ctx, member: discord.Member = None):
        await ctx.defer()
        target = member or ctx.author
        uid = str(target.id)
        
        # Auto-Migrate Old Pet System to Slot 1 safely
        if "equipped_pet" in db and uid in db["equipped_pet"]:
            old_pet = db["equipped_pet"].pop(uid)
            db.setdefault("team", {}).setdefault(uid, {})["1"] = old_pet
            save_db(db)

        team = db.get("team", {}).get(uid, {})
        if not team:
            return await ctx.send(embed=discord.Embed(description=f"❌ {target.name} does not have any team members equipped. Use `/equip`.", color=discord.Color.dark_grey()))
            
        embed = discord.Embed(title=f"🐾 {target.name}'s Active Team", description="These monsters boost your `/quest` XP and fight for you in `/pve` and `/pvp`.", color=discord.Color.gold())
        
        total_xp_boost = 0
        for i in range(1, 4):
            slot_str = str(i)
            if slot_str in team:
                mob = team[slot_str]
                _, hp, dmg, xp_mult = get_mob_stats(mob["name"])
                custom_move = db.get("monster_moves", {}).get(uid, {}).get(mob["name"], "Basic Strike")
                
                total_xp_boost += int((xp_mult - 1.0) * 100)
                embed.add_field(name=f"Slot {i}: {mob['name']}", value=f"💎 **Rarity:** {mob['rarity']}\n❤️ **HP:** {hp:,} | ⚔️ **DMG:** {dmg:,}\n🔮 **Move:** {custom_move}", inline=False)
            else:
                embed.add_field(name=f"Slot {i}: [Empty]", value="Use `/equip` to add a monster.", inline=False)
                
        embed.set_footer(text=f"Total Passive Bonus: +{total_xp_boost}% Quest XP")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="upgrade_pet", description="AI generates a powerful custom move for your monster! (Cost: 50k)")
    @commands.cooldown(1, 45, commands.BucketType.member)
    async def upgrade_pet(self, ctx, *, exact_name: str):
        await ctx.defer()
        uid = str(ctx.author.id)
        cost = 50000
        
        zoo_inv = db.get("zoo", {}).get(uid, {})
        exact_match = next((m for m in zoo_inv if exact_name.lower() in m.lower()), None)
        
        if not exact_match:
            return await ctx.send(embed=discord.Embed(description=f"❌ You don't own `{exact_name}`.", color=discord.Color.red()))
            
        if db.setdefault("economy", {}).get(uid, 0) < cost:
            return await ctx.send(embed=discord.Embed(description=f"❌ You need {cost:,} 🪙 to upgrade a monster.", color=discord.Color.red()))
            
        db["economy"][uid] -= cost
        save_db(db)
        
        # 70% Success Chance
        if random.randint(1, 100) > 70:
            return await ctx.send(embed=discord.Embed(description=f"💥 **UPGRADE FAILED!** You spent 50,000 🪙 but **{exact_match}** couldn't grasp the new technique.", color=discord.Color.dark_red()))
            
        if not ai_client:
            return await ctx.send(embed=discord.Embed(description="❌ **AI Offline.** The upgrade center is closed.", color=discord.Color.red()))
            
        msg = await ctx.send(embed=discord.Embed(description=f"🔮 **Channeling cosmic energy into {exact_match}...**", color=discord.Color.blurple()))
        
        prompt = f"Generate a badass, epic 2-to-3 word RPG attack move name for a monster named '{exact_match}'. Output ONLY the move name, nothing else. No quotes."
        try:
            # 🔥 TIMEOUT SHIELD
            new_move = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
            
            db.setdefault("monster_moves", {}).setdefault(uid, {})[exact_match] = new_move
            save_db(db)
            
            await msg.edit(embed=discord.Embed(title="✨ UPGRADE SUCCESS!", description=f"**{exact_match}** successfully consumed the essence and learned a new signature attack:\n\n🔮 **{new_move}**", color=discord.Color.gold()))
        except Exception as e:
            await msg.edit(embed=discord.Embed(description="❌ AI Timeout. The upgrade was refunded.", color=discord.Color.red()))
            db["economy"][uid] += cost
            save_db(db)

    # ========================================================================
    # STANDARD RPG HUNT & ZOO
    # ========================================================================
    @commands.hybrid_command(name="hunt", description="Venture into the wild to capture rare monsters.")
    @commands.cooldown(1, 45, commands.BucketType.member)
    async def hunt(self, ctx): 
        await ctx.defer()
        uid = str(ctx.author.id)
        
        msg = await ctx.send(embed=discord.Embed(description="🌲 **Venturing into the tall grass...**", color=discord.Color.dark_green()))
        await asyncio.sleep(1.5)
        
        if random.randint(1, 100) <= 2 and ai_client:
            prompt = """I just triggered a 1-of-1 ultra rare mythic boss spawn. Generate a unique Boss monster. 
            Output ONLY a raw, perfectly formatted JSON object exactly like this: 
            {"name": "String", "title": "String", "value": 15000000}"""
            
            try:
                res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=4.0)
                start, end = res.find('{'), res.rfind('}')
                if start == -1 or end == -1: raise Exception("JSON format hallucination.")
                
                boss_data = json.loads(res[start:end+1])
                full_name = f"🌌 {boss_data['name']} [{boss_data['title']}] (Mythic 1-of-1)"
                
                user_zoo = db.setdefault("zoo", {}).setdefault(uid, {})
                user_zoo[full_name] = user_zoo.get(full_name, 0) + 1
                save_db(db)
                
                embed = discord.Embed(title="🚨 MYTHIC ANOMALY 🚨", description=f"The fabric of reality tore open and you captured a 1-of-1 Mythic Boss!\n\n**Captured:** {full_name}\n**Value:** {boss_data['value']:,} 🪙", color=discord.Color.magenta())
                embed.set_image(url="https://media.giphy.com/media/l41YkxvU8c7J7Bba0/giphy.gif")
                return await msg.edit(embed=embed)
            except Exception as e: 
                print(f"⚠️ AI Mythic Timeout: {e}")

        rarities = list(MONSTERS.keys())
        weights = [MONSTERS[r]["chance"] for r in rarities]
        caught_rarity = random.choices(rarities, weights=weights, k=1)[0]
        caught_mob = random.choice(MONSTERS[caught_rarity]["mobs"])
        
        nature = "[The Average]"
        if ai_client:
            prompt2 = f"Generate a short title or nature for a {caught_mob} e.g. [The Brave]. Return ONLY the bracketed string. Nothing else."
            try:
                res_nature = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt2}], inject_personality=False), timeout=4.0)
                match = re.search(r'\[.*?\]', res_nature)
                if match: nature = match.group(0)
                else: nature = f"[{res_nature.strip()}]"
            except: pass

        full_name = f"{caught_mob} {nature}"
        
        user_zoo = db.setdefault("zoo", {}).setdefault(uid, {})
        user_zoo[full_name] = user_zoo.get(full_name, 0) + 1
        save_db(db)

        colors = {"Common": 0x95a5a6, "Uncommon": 0x2ecc71, "Rare": 0x3498db, "Epic": 0x9b59b6, "Legendary": 0xf1c40f, "Mythic": 0xe91e63, "Secret": 0x00d2d3}
        embed = discord.Embed(title="🏹 The Hunt!", description=f"You ventured into the wild and caught a **{full_name}**!\n\n**Rarity:** {caught_rarity}\n**Base Value:** {MONSTERS.get(caught_rarity, {}).get('value', 1500):,} 🪙", color=colors.get(caught_rarity, 0x95a5a6))
        await msg.edit(embed=embed)


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
        user_zoo = db.setdefault("zoo", {}).setdefault(uid, {})
        
        exact_m1 = next((m for m in user_zoo if mob1.lower() in m.lower()), None)
        exact_m2 = next((m for m in user_zoo if mob2.lower() in m.lower()), None)
        
        if not exact_m1 or not exact_m2 or (exact_m1 == exact_m2 and user_zoo[exact_m1] < 2):
            return await ctx.send(embed=discord.Embed(description="❌ You don't own the required monsters for this fusion.", color=discord.Color.red()))
            
        prompt = f"""I am fusing '{exact_m1}' and '{exact_m2}'. Generate a horrific, overpowered hybrid Chimera monster. 
        Output ONLY a valid JSON object exactly like this: {{"name": "String", "desc": "String"}}"""
        
        try:
            res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
            start, end = res.find('{'), res.rfind('}')
            if start == -1 or end == -1: raise Exception("AI JSON format error.")
            
            chimera = json.loads(res[start:end+1])
            
            user_zoo[exact_m1] -= 1
            user_zoo[exact_m2] -= 1
            if user_zoo[exact_m1] <= 0: del user_zoo[exact_m1]
            if user_zoo[exact_m2] <= 0: del user_zoo[exact_m2]
            
            full_n = f"🧬 {chimera['name']} (Chimera)"
            user_zoo[full_n] = user_zoo.get(full_n, 0) + 1
            save_db(db)
            
            embed = discord.Embed(title="🧬 MUTATION SUCCESSFUL", description=f"You successfully fused the monsters and created **{full_n}**!\n\n*{chimera['desc']}*", color=0x6c5ce7)
            await ctx.send(embed=embed)
        except Exception as e: 
            await ctx.send(embed=discord.Embed(description="❌ The mutation chamber exploded due to an AI error (or timed out). Your monsters are safe.", color=discord.Color.red()))


    @commands.hybrid_command(name="sell_monster", description="Sell a monster to shady buyers on the AI Black Market.")
    async def sell_monster(self, ctx, exact_name: str, amount: int = 1):
        await ctx.defer()
        uid = str(ctx.author.id)
        user_zoo = db.setdefault("zoo", {}).setdefault(uid, {})
        
        found_mob = next((m for m in user_zoo if exact_name.lower() in m.lower()), None)
        if not found_mob or user_zoo[found_mob] < amount: 
            return await ctx.send(embed=discord.Embed(description=f"❌ You don't own {amount}x of that monster.", color=discord.Color.red()))
            
        rarity, hp, dmg, xp = get_mob_stats(found_mob)
        base_val = 1500
        for r, data in MONSTERS.items():
            if r == rarity: base_val = data.get("value", 1500)
            
        if "Mythic" in found_mob: base_val = 10000000
        if "Secret" in found_mob or "Chimera" in found_mob: base_val = 50000000
        
        total_val = base_val * amount
        
        prompt = f"""I am selling '{amount}x {found_mob}' (Estimated Base: {total_val}). Generate 3 shady black market buyers. One lowballs, one is fair, one overpays. 
        Output ONLY a JSON array of 3 objects exactly like this:
        [
            {{"buyer": "Name", "quote": "String", "offer": 1000}},
            ...
        ]"""
        
        try:
            res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=6.0)
            start, end = res.find('['), res.rfind(']')
            if start == -1 or end == -1: raise Exception("AI JSON format error.")
            buyers = json.loads(res[start:end+1])
            
            embed = discord.Embed(title="🕴️ The Black Market", description=f"You brought **{amount}x {found_mob}** to the alleyway.\nThree figures step forward...", color=0x2c3e50)
            for i, b in enumerate(buyers): 
                embed.add_field(name=f"Buyer {i+1}: {b['buyer']}", value=f"💰 **Offer:** {b['offer']:,} 🪙\n🗣️ *\"{b['quote']}\"*", inline=False)
                
            await ctx.send(embed=embed, view=BlackMarketView(ctx, uid, found_mob, amount, buyers))
        except Exception as e: 
            await ctx.send(embed=discord.Embed(description="❌ The black market was raided by the FBI (AI timeout). Try selling later.", color=discord.Color.red()))


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
        user_zoo = db.setdefault("zoo", {}).setdefault(uid, {})
        
        for _ in range(amount):
            total_coins += random.randint(*config["coin_range"])
            total_xp += random.randint(*config["xp_range"])
            
            rarity = random.choices(config["rarities"], weights=config["weights"], k=1)[0]
            mob = f"{random.choice(MONSTERS[rarity]['mobs'])} [Boxed]"
            mobs_caught[mob] = mobs_caught.get(mob, 0) + 1
            user_zoo[mob] = user_zoo.get(mob, 0) + 1

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
    # LEVELING & QUESTS (With Multi-Pet Multipliers)
    # ========================================================================
    @commands.hybrid_command(name="quest", description="Go on an epic quest to earn XP and level up.")
    @commands.cooldown(1, 3600, commands.BucketType.member)
    async def quest(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        level_data = db.setdefault("levels", {}).setdefault(uid, {"xp": 0, "level": 1})
        
        if level_data["level"] >= 13000:
            return await ctx.send(embed=discord.Embed(description="🛑 **Max Level 13,000 Reached!** You are already at the pinnacle.", color=discord.Color.red()))
        
        # XP Multiplier Logic via Team
        team = db.get("team", {}).get(uid, {})
        total_mult = 1.0
        
        for mob in team.values():
            _, _, _, xp_mult = get_mob_stats(mob["name"])
            total_mult += (xp_mult - 1.0)
            
        base_xp = random.randint(300, 800)
        xp_gained = int(base_xp * total_mult)
        level_data["xp"] += xp_gained
        
        req_xp = int(150 * (level_data['level'] ** 1.5))
        leveled_up = False
        
        while level_data["xp"] >= req_xp:
            level_data["xp"] -= req_xp
            level_data["level"] += 1
            leveled_up = True
            req_xp = int(150 * (level_data['level'] ** 1.5))
            
        save_db(db)
        
        bonus_text = f"\n\n🐾 Your team provided a **+{int((total_mult-1.0)*100)}%** XP Boost!" if total_mult > 1.0 else ""
        desc = f"🗡️ **Dungeon run complete!** You braved the depths and earned **{xp_gained:,} XP**!{bonus_text}"
        
        if leveled_up:
            desc += f"\n\n🎉 **LEVEL UP!** You grew stronger and are now Level **{level_data['level']}**!"
            
        await ctx.send(embed=discord.Embed(description=desc, color=discord.Color.orange()))

    @commands.hybrid_command(name="rank", description="Check your current RPG Level and XP.")
    async def rank(self, ctx, m: discord.Member = None): 
        await ctx.defer()
        target = m or ctx.author
        
        level_data = db.setdefault("levels", {}).setdefault(str(target.id), {"xp": 0, "level": 1})
        req = int(150 * (level_data['level'] ** 1.5))
        
        embed = discord.Embed(title=f"Rank: {target.name}", description=f"⭐ Level: **{level_data['level']}**\n✨ XP: **{level_data['xp']:,} / {req:,}**", color=0x3498db)
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
                embed.add_field(name=f"#{i*10 + j + 1}", value=f"<@{uid}> - Level **{data.get('level', 1)}** (XP: {data.get('xp', 0):,})", inline=False)
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
