
import discord
from discord.ext import commands
import random
import asyncio
from core import db, save_db, PaginationView, get_gif

# ========================================================================
# MONSTER GACHA SYSTEM (OwO Bot Style)
# Description: Defines the rarities, drop rates, and sell values of monsters.
# ========================================================================
MONSTERS = {
    "Common": {"chance": 60, "value": 1500, "mobs": ["🟢 Slime", "🦇 Cave Bat", "🐀 Plague Rat"]},
    "Uncommon": {"chance": 25, "value": 5000, "mobs": ["👺 Goblin", "🐺 Dire Wolf", "💀 Skeleton Warrior"]},
    "Rare": {"chance": 10, "value": 25000, "mobs": ["👹 Orc Brute", "🗿 Stone Gargoyle", "👻 Cursed Wraith"]},
    "Epic": {"chance": 4, "value": 100000, "mobs": ["🐉 Lesser Dragon", "🦅 Griffin", "🐍 Basilisk"]},
    "Legendary": {"chance": 1, "value": 1000000, "mobs": ["🔥 Immortal Phoenix", "🐙 Abyssal Kraken", "⚡ Storm Behemoth"]}
}

class RPG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ========================================================================
    # COMMAND: /hunt (OwO Style)
    # Description: Catch monsters with weighted RNG. 
    # ========================================================================
    @commands.hybrid_command(name="hunt", description="Hunt for monsters in the wild. Rare monsters sell for millions!")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def hunt(self, ctx): 
        await ctx.defer()
        uid = str(ctx.author.id)
        
        # Weighted RNG Roll
        rarities = list(MONSTERS.keys())
        weights = [MONSTERS[r]["chance"] for r in rarities]
        caught_rarity = random.choices(rarities, weights=weights, k=1)[0]
        caught_mob = random.choice(MONSTERS[caught_rarity]["mobs"])
        
        # Save to Zoo
        db.setdefault("zoo", {}).setdefault(uid, {})
        db["zoo"][uid][caught_mob] = db["zoo"][uid].get(caught_mob, 0) + 1
        save_db(db)

        # Set Colors based on rarity
        colors = {"Common": discord.Color.light_grey(), "Uncommon": discord.Color.green(), "Rare": discord.Color.blue(), "Epic": discord.Color.purple(), "Legendary": discord.Color.gold()}
        
        embed = discord.Embed(title="🏹 The Hunt!", color=colors[caught_rarity])
        embed.description = f"You ventured into the wild and caught a **{caught_mob}**!\n\n**Rarity:** {caught_rarity}\n**Value:** {MONSTERS[caught_rarity]['value']:,} 🪙"
        
        if caught_rarity == "Legendary":
            embed.description += "\n\n🌟 **ABSOLUTE LEGENDARY PULL!** 🌟"
            
        await ctx.send(embed=embed)


    # ========================================================================
    # COMMAND: /zoo
    # Description: View all the monsters you've hunted and collected.
    # ========================================================================
    @commands.hybrid_command(name="zoo", description="View your collection of hunted monsters.")
    async def zoo(self, ctx, member: discord.Member = None):
        await ctx.defer()
        target = member or ctx.author
        uid = str(target.id)
        
        zoo_inv = db.get("zoo", {}).get(uid, {})
        if not zoo_inv:
            return await ctx.send(embed=discord.Embed(description=f"🐾 {target.name}'s Zoo is completely empty. Go `/hunt`!", color=discord.Color.red()))
            
        # Format the zoo list
        lines = []
        for mob, count in zoo_inv.items():
            lines.append(f"**{mob}** x{count}")
            
        chunks = [lines[i:i + 10] for i in range(0, len(lines), 10)]
        embeds = []
        for i, chunk in enumerate(chunks):
            e = discord.Embed(title=f"🐾 {target.name}'s Bestiary ({i+1}/{len(chunks)})", description="\n".join(chunk), color=discord.Color.dark_green())
            embeds.append(e)
            
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))


    # ========================================================================
    # COMMAND: /sell_monster
    # Description: Sell caught monsters for coins.
    # ========================================================================
    @commands.hybrid_command(name="sell_monster", description="Sell a monster from your zoo for coins.")
    async def sell_monster(self, ctx, exact_name: str, amount: int = 1):
        await ctx.defer()
        uid = str(ctx.author.id)
        zoo_inv = db.setdefault("zoo", {}).get(uid, {})
        
        # Search for the monster
        found_mob = next((m for m in zoo_inv if exact_name.lower() in m.lower()), None)
        
        if not found_mob or zoo_inv[found_mob] < amount:
            return await ctx.send(embed=discord.Embed(description=f"❌ You don't have {amount}x of that monster.", color=discord.Color.red()))
            
        # Find its value
        mob_value = 0
        for rarity, data in MONSTERS.items():
            if found_mob in data["mobs"]:
                mob_value = data["value"]
                break
                
        total_payout = mob_value * amount
        
        # Deduct mob, add coins
        zoo_inv[found_mob] -= amount
        if zoo_inv[found_mob] <= 0:
            del zoo_inv[found_mob]
            
        db.setdefault("economy", {})[uid] = db["economy"].get(uid, 0) + total_payout
        save_db(db)
        
        await ctx.send(embed=discord.Embed(description=f"🤝 Sold **{amount}x {found_mob}** for **{total_payout:,} 🪙**!", color=discord.Color.green()))


    # ========================================================================
    # LOOTBOX SYSTEM
    # Description: Buy and open lootboxes for massive randomized rewards.
    # ========================================================================
    @commands.hybrid_group(name="lootbox", description="Buy and open mysterious lootboxes.")
    async def lootbox(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/lootbox buy` or `/lootbox open`.")

    @lootbox.command(name="buy", description="Buy a Mystic Lootbox for 100,000 coins.")
    async def lootbox_buy(self, ctx, amount: int = 1):
        await ctx.defer()
        uid = str(ctx.author.id)
        cost = 100000 * amount
        
        if db.setdefault("economy", {}).get(uid, 0) < cost:
            return await ctx.send(embed=discord.Embed(description=f"❌ You need **{cost:,} coins** to buy {amount} Lootbox(es).", color=discord.Color.red()))
            
        db["economy"][uid] -= cost
        db.setdefault("lootboxes", {})[uid] = db.get("lootboxes", {}).get(uid, 0) + amount
        save_db(db)
        
        await ctx.send(embed=discord.Embed(description=f"🎁 Successfully bought **{amount}x Mystic Lootbox(es)**! Use `/lootbox open` to unbox it.", color=discord.Color.green()))

    @lootbox.command(name="open", description="Open a Mystic Lootbox.")
    async def lootbox_open(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        
        if db.setdefault("lootboxes", {}).get(uid, 0) <= 0:
            return await ctx.send(embed=discord.Embed(description="❌ You don't have any Lootboxes! Buy one with `/lootbox buy`.", color=discord.Color.red()))
            
        # Deduct box
        db["lootboxes"][uid] -= 1
        
        # Fake suspense animation
        msg = await ctx.send(embed=discord.Embed(title="🎁 Opening Lootbox...", description="*Unlocking the magical seals...*", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        await msg.edit(embed=discord.Embed(title="🎁 Opening Lootbox...", description="*The box is glowing intensely!*", color=discord.Color.gold()))
        await asyncio.sleep(1.5)
        
        # Generate Rewards (Coins + XP + Random Monster)
        coins = random.randint(10000, 250000)
        xp = random.randint(100, 500)
        
        # Roll a monster (Slightly better odds than normal hunting)
        rarities = list(MONSTERS.keys())
        weights = [40, 30, 20, 8, 2] # Lootboxes have better legendary rates!
        caught_rarity = random.choices(rarities, weights=weights, k=1)[0]
        caught_mob = random.choice(MONSTERS[caught_rarity]["mobs"])
        
        # Apply rewards
        db.setdefault("economy", {})[uid] = db["economy"].get(uid, 0) + coins
        db.setdefault("levels", {}).setdefault(uid, {"xp": 0, "level": 1})["xp"] += xp
        db.setdefault("zoo", {}).setdefault(uid, {})[caught_mob] = db["zoo"][uid].get(caught_mob, 0) + 1
        save_db(db)
        
        # Final Reveal
        embed = discord.Embed(title="✨ LOOTBOX OPENED! ✨", color=discord.Color.purple())
        embed.add_field(name="💰 Coins", value=f"+{coins:,}", inline=True)
        embed.add_field(name="📈 XP", value=f"+{xp}", inline=True)
        embed.add_field(name=f"🐾 Monster ({caught_rarity})", value=caught_mob, inline=False)
        
        await msg.edit(embed=embed)


    # ========================================================================
    # STANDARD RPG COMMANDS (Fishing, Mining, Leveling)
    # ========================================================================
    @commands.hybrid_command(name="fish", description="Cast a line and catch fish.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def fish(self, ctx): 
        await ctx.defer()
        fish = random.choice(["Old Boot", "Common Carp", "Rare Salmon", "Legendary Shark"])
        reward = {"Old Boot": 0, "Common Carp": 5000, "Rare Salmon": 20000, "Legendary Shark": 100000}[fish]
        db.setdefault("economy", {})[str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🎣 Caught a {fish}! Sold for {reward:,} coins.", color=discord.Color.blue()))

    @commands.hybrid_command(name="mine", description="Mine for ores.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def mine(self, ctx): 
        await ctx.defer()
        ore = random.choice(["Stone", "Iron Ore", "Raw Diamond"])
        reward = {"Stone": 500, "Iron Ore": 8000, "Raw Diamond": 120000}[ore]
        db.setdefault("economy", {})[str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⛏️ Mined {ore}! Sold for {reward:,} coins.", color=discord.Color.light_grey()))

    @commands.hybrid_command(name="quest", description="Go on an epic quest.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def quest(self, ctx):
        await ctx.defer(); u = str(ctx.author.id)
        if db.setdefault("levels", {}).setdefault(u, {"xp": 0, "level": 1})["level"] >= 13000: return await ctx.send(embed=discord.Embed(description="🛑 **Max Level 13,000!**", color=discord.Color.red()))
        x = random.randint(300, 800); db["levels"][u]["xp"] += x; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🗡️ **Dungeon run complete!** Earned **{x} XP**!", color=discord.Color.orange()))

    @commands.hybrid_command(name="rank", description="Check XP Rank.")
    async def rank(self, ctx, m: discord.Member = None): 
        await ctx.defer(); t = m or ctx.author; l = db.setdefault("levels", {}).setdefault(str(t.id), {"xp": 0, "level": 1})
        req = int(150 * (l['level'] ** 1.5))
        embed = discord.Embed(title=f"Rank: {t.name}", description=f"⭐ Lvl: **{l['level']}**\n✨ XP: **{l['xp']} / {req}**", color=discord.Color.blue())
        embed.set_thumbnail(url=str(t.display_avatar.url)); await ctx.send(embed=embed)

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

    @commands.hybrid_command(name="givexp", description="Admin command to grant XP.")
    @commands.has_permissions(administrator=True)
    async def givexp(self, ctx, m: discord.Member, a: int): 
        await ctx.defer(); db.setdefault("levels", {}).setdefault(str(m.id), {"xp": 0, "level": 1})["xp"] += a; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"📈 Granted {a} XP to {m.name}.", color=discord.Color.green()))

    @commands.hybrid_command(name="removexp", description="Admin command to remove XP.")
    @commands.has_permissions(administrator=True)
    async def removexp(self, ctx, m: discord.Member, a: int): 
        await ctx.defer(); u = str(m.id); db["levels"][u]["xp"] = max(0, db.setdefault("levels", {}).get(u, {"xp":0})["xp"] - a); save_db(db)
        await ctx.send(embed=discord.Embed(description=f"📉 Removed {a} XP from {m.name}.", color=discord.Color.red()))

    @commands.hybrid_command(name="setlevel", description="Admin command to set level.")
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, m: discord.Member, l: int): 
        await ctx.defer(); db.setdefault("levels", {}).setdefault(str(m.id), {"xp": 0, "level": 1})["level"] = l; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⭐ Set {m.name} to Lvl {l}.", color=discord.Color.gold()))

async def setup(bot):
    await bot.add_cog(RPG(bot))
