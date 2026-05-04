import discord
from discord.ext import commands, tasks
import random
import time
import json
import asyncio
from core import db, save_db, get_gif, ask_groq, ai_client
from ui import PaginationView

# ========================================================================
# THE MASTER ITEM REGISTRY (End-Game Scaling)
# ========================================================================
MASTER_ITEMS = {
    "Common": {
        "chance": 50.0, 
        "color": "⚪",
        "items": [
            {"name": "Iron Dagger", "price": 10000}, 
            {"name": "Wooden Buckler", "price": 12000},
            {"name": "Torn Cloak", "price": 8000}
        ]
    },
    "Uncommon": {
        "chance": 25.0, 
        "color": "🟢",
        "items": [
            {"name": "Steel Katana", "price": 35000}, 
            {"name": "Hunter's Bow", "price": 38000},
            {"name": "Iron Gauntlets", "price": 40000}
        ]
    },
    "Rare": {
        "chance": 14.0, 
        "color": "🔵",
        "items": [
            {"name": "Obsidian Blade", "price": 150000}, 
            {"name": "Abyssal Grimoire", "price": 180000},
            {"name": "Assassin's Cowl", "price": 165000}
        ]
    },
    "Epic": {
        "chance": 8.0, 
        "color": "🟣",
        "items": [
            {"name": "Void Scythe", "price": 500000}, 
            {"name": "Returner's Watch", "price": 600000},
            {"name": "Staff of Embers", "price": 550000}
        ]
    },
    "Legendary": {
        "chance": 2.4, 
        "color": "🟡",
        "items": [
            {"name": "Cursed Dual Katana", "price": 2500000}, 
            {"name": "Blade of the Cosmos", "price": 2500000},
            {"name": "Sun God's Aegis", "price": 3000000}
        ]
    },
    "Mythic": {
        "chance": 0.5, 
        "color": "🌌",
        "items": [
            {"name": "Primordial Rune", "price": 15000000}, 
            {"name": "Ji Realm Core", "price": 20000000},
            {"name": "Worldbreaker Hammer", "price": 18000000}
        ]
    },
    "Secret": {
        "chance": 0.1, 
        "color": "💠",
        "items": [
            {"name": "Aizen's Hogyoku Fragment", "price": 50000000}, 
            {"name": "Eye of the Leviathan", "price": 65000000},
            {"name": "Soul King's Crown", "price": 75000000}
        ]
    }
}

def roll_stock():
    stock = []
    rarities = list(MASTER_ITEMS.keys())
    weights = [MASTER_ITEMS[r]["chance"] for r in rarities]
    
    for _ in range(4):
        r = random.choices(rarities, weights=weights, k=1)[0]
        item = random.choice(MASTER_ITEMS[r]["items"])
        stock.append({
            "name": item["name"], 
            "price": item["price"], 
            "rarity": r,
            "icon": MASTER_ITEMS[r]["color"]
        })
    return stock

# ========================================================================
# UI CLASS: DYNAMIC SHOP BUTTONS
# ========================================================================
class DynamicShopView(discord.ui.View):
    def __init__(self, items):
        super().__init__(timeout=None)
        for idx, item in enumerate(items):
            btn = discord.ui.Button(label=f"Buy {item['name']}", style=discord.ButtonStyle.secondary, custom_id=f"shop_{idx}")
            btn.callback = self.create_callback(item)
            self.add_item(btn)

    def create_callback(self, item):
        async def buy_callback(interaction: discord.Interaction):
            uid = str(interaction.user.id)
            bal = db.setdefault("economy", {}).get(uid, 0)
            
            if bal < item["price"]:
                return await interaction.response.send_message(f"❌ You are too broke! You need **{item['price']:,} 🪙** to buy this.", ephemeral=True)
                
            db["economy"][uid] -= item["price"]
            full_item_name = f"{item['icon']} {item['name']} [{item['rarity']}]"
            db.setdefault("inventory", {}).setdefault(uid, []).append(full_item_name)
            save_db(db)
            
            await interaction.response.send_message(f"🛒 **Transaction Complete!** You purchased **{full_item_name}** for **{item['price']:,} 🪙**!", ephemeral=True)
        return buy_callback


# ========================================================================
# UI CLASSES: INTERACTIVE FORGE HUB (Select Menus & Modals)
# ========================================================================
class AwakenModal(discord.ui.Modal, title="Awaken Artifact"):
    item_name = discord.ui.TextInput(label="Exact Artifact Name", placeholder="e.g. Obsidian Blade", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        inv = db.setdefault("inventory", {}).get(uid, [])
        exact_item_name = self.item_name.value.strip()
        
        exact_match = next((i for i in inv if exact_item_name.lower() in i.lower()), None)
        
        if not exact_match:
            return await interaction.followup.send(f"❌ You do not own an item matching `{exact_item_name}`.", ephemeral=True)
            
        if inv.count(exact_match) < 2:
            return await interaction.followup.send(f"❌ You need **2x** of `{exact_match}` to Awaken it. You only have 1.", ephemeral=True)
            
        db["inventory"][uid].remove(exact_match)
        db["inventory"][uid].remove(exact_match)
        
        awakened_item = exact_match.replace("[", "").replace("]", "").strip() 
        new_item = f"🔥 {awakened_item} [AWAKENED]"
        db["inventory"][uid].append(new_item)
        save_db(db)
        
        embed = discord.Embed(title="⚒️ AWAKENING SUCCESSFUL", description=f"You sacrificed two **{exact_match}**s to the Forge...", color=discord.Color.gold())
        embed.add_field(name="God-Tier Artifact Created:", value=f"**{new_item}**", inline=False)
        await interaction.followup.send(embed=embed)


class ForgeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="View Weekly Blueprint", emoji="📜", description="See the AI Grandmaster's current recipe.", value="view"),
            discord.SelectOption(label="Check My Materials", emoji="🎒", description="Scan your inventory for required components.", value="check"),
            discord.SelectOption(label="Forge Secret Artifact", emoji="🔮", description="Consume materials to craft the AI weapon.", value="craft"),
            discord.SelectOption(label="Awaken Artifact", emoji="🔥", description="Combine 2 duplicate items for a massive upgrade.", value="awaken")
        ]
        super().__init__(placeholder="Select a Forge Operation...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        action = self.values[0]
        rec = db.get("weekly_recipe")

        # Handle AWAKEN (Triggers Modal, must be done before deferring)
        if action == "awaken":
            return await interaction.response.send_modal(AwakenModal())

        await interaction.response.defer()

        # Check if recipe exists for the other 3 actions
        if not rec and action in ["view", "check", "craft"]:
            return await interaction.followup.send("❌ The AI Forge is currently closed. Wait for the weekly reset.", ephemeral=True)

        inv = db.setdefault("inventory", {}).get(uid, [])
        i1_match = next((i for i in inv if rec['item1'].lower() in i.lower()), None)
        i2_match = next((i for i in inv if rec['item2'].lower() in i.lower()), None)

        if action == "view":
            time_left = max(0, int(db.get("recipe_expiry", 0) - time.time()))
            days, rem = divmod(time_left, 86400)
            hours, mins = divmod(rem, 3600)
            
            embed = discord.Embed(title="📜 The Grandmaster's Weekly Blueprint", description="*Gather these specific items from the Hourly Shop to forge a legendary artifact!*", color=discord.Color.blurple())
            embed.add_field(name="Required Materials", value=f"🔹 1x **{rec['item1']}**\n🔹 1x **{rec['item2']}**", inline=False)
            embed.add_field(name="Resulting Artifact", value=f"🔮 **{rec['result_name']}**\n*{rec['desc']}*", inline=False)
            embed.set_footer(text=f"⏳ Recipe rotates in {days}d {hours}h {mins//60}m.")
            await interaction.message.edit(embed=embed)

        elif action == "check":
            status1 = f"✅ You have this: **{i1_match}**" if i1_match else f"❌ Missing: **{rec['item1']}**"
            status2 = f"✅ You have this: **{i2_match}**" if i2_match else f"❌ Missing: **{rec['item2']}**"
            
            embed = discord.Embed(title="🎒 Material Scanner", description="Scanning your `/inventory` for the required weekly materials...", color=discord.Color.dark_grey())
            embed.add_field(name="Component 1", value=status1, inline=False)
            embed.add_field(name="Component 2", value=status2, inline=False)
            await interaction.message.edit(embed=embed)

        elif action == "craft":
            if not i1_match or not i2_match:
                return await interaction.followup.send(f"❌ You lack the materials to Forge this! Use 'Check My Materials' to see what you need.", ephemeral=True)
                
            # Deduct items
            db["inventory"][uid].remove(i1_match)
            db["inventory"][uid].remove(i2_match)
            
            # Add the AI item
            full_artifact = f"🔮 {rec['result_name']} [SECRET FORGE]"
            db["inventory"][uid].append(full_artifact)
            save_db(db)
            
            embed = discord.Embed(title="🌌 SECRET FORGE COMPLETE", description=f"You combined **{i1_match}** and **{i2_match}** at the altar...", color=discord.Color.dark_purple())
            embed.add_field(name="A mythical artifact was born:", value=f"**{full_artifact}**\n*{rec['desc']}*", inline=False)
            await interaction.message.edit(embed=embed)

class ForgeHubView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(ForgeSelect())


# ========================================================================
# COG CLASS: Economy, Shop, & AI Forge
# ========================================================================
class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.background_loops.start()

    def cog_unload(self):
        self.background_loops.cancel()

    # ========================================================================
    # BACKGROUND TASKS: Hourly Shop & Weekly AI Recipe
    # ========================================================================
    @tasks.loop(hours=1)
    async def background_loops(self):
        # 1. Update Hourly Shop
        db["current_shop"] = roll_stock()
        
        # 2. Check Weekly AI Recipe
        current_time = time.time()
        expiry_time = db.get("recipe_expiry", 0)
        
        if current_time >= expiry_time and ai_client:
            print("⚙️ [SYSTEM] Generating new Weekly AI Forge Recipe...")
            all_items = [i["name"] for cat in MASTER_ITEMS.values() for i in cat["items"]]
            
            prompt = f"""You are the Grandmaster Blacksmith. Pick EXACTLY TWO different items from this list: {all_items}. 
            Fuse them into a God-Tier, ultra-powerful weapon. Output ONLY a raw JSON object.
            SCHEMA: {{"item1": "Exact Name from list", "item2": "Exact Name from list", "result_name": "Epic Custom Name", "desc": "Cool Lore"}}"""
            
            try:
                res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
                start, end = res.find('{'), res.rfind('}')
                if start == -1 or end == -1: raise Exception("JSON format hallucination.")
                
                recipe_data = json.loads(res[start:end+1])
                db["weekly_recipe"] = recipe_data
                db["recipe_expiry"] = current_time + 604800 # 7 Days
                print(f"✅ [SYSTEM] New Recipe Live: {recipe_data['result_name']}")
            except Exception as e:
                print(f"⚠️ [SYSTEM] AI Recipe Generation Failed: {e}")
                
        save_db(db)

    @background_loops.before_loop
    async def before_loops(self):
        await self.bot.wait_until_ready()

    # ========================================================================
    # BANK & LEADERBOARD
    # ========================================================================
    @commands.hybrid_command(name="bal", aliases=["balance", "bank"], description="Check your bank balance.")
    async def bal(self, ctx, member: discord.Member = None):
        await ctx.defer()
        target = member or ctx.author
        uid = str(target.id)
        bal = db.setdefault("economy", {}).get(uid, 0)
        embed = discord.Embed(title=f"💳 {target.name}'s Bank Account", description=f"**Net Worth:** {bal:,} 🪙", color=discord.Color.gold())
        embed.set_thumbnail(url=str(target.display_avatar.url))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rich", description="View the wealthiest players in the server.")
    async def rich(self, ctx):
        await ctx.defer()
        sorted_eco = sorted(db.get("economy", {}).items(), key=lambda x: x[1], reverse=True)
        if not sorted_eco: return await ctx.send(embed=discord.Embed(description="The server is empty.", color=discord.Color.red()))
        embed = discord.Embed(title="🏆 The Forbes Rich List", color=discord.Color.gold())
        board = ""
        for i, (uid, coins) in enumerate(sorted_eco[:10]):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "💸"
            board += f"{medal} **<@{uid}>** — {coins:,} 🪙\n"
        embed.description = board
        await ctx.send(embed=embed)

    # ========================================================================
    # INCOME & HUSTLE
    # ========================================================================
    @commands.hybrid_command(name="daily", description="Claim your daily coins.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        db.setdefault("economy", {})[uid] = db["economy"].get(uid, 0) + 500000; save_db(db)
        await ctx.send(embed=discord.Embed(description="📅 You claimed your daily **500,000 🪙**!", color=discord.Color.green()))

    @commands.hybrid_command(name="work", description="Work an honest job for coins.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def work(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        earned = random.randint(50000, 150000)
        db.setdefault("economy", {})[uid] = db["economy"].get(uid, 0) + earned; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"💼 You worked hard and earned **{earned:,} 🪙**.", color=discord.Color.blue()))

    @commands.hybrid_command(name="rob", description="Attempt to steal from another player's bank.")
    @commands.cooldown(1, 7200, commands.BucketType.user)
    async def rob(self, ctx, member: discord.Member):
        await ctx.defer()
        uid, tid = str(ctx.author.id), str(member.id)
        if member.bot or uid == tid: return await ctx.send("❌ Invalid target.")
        
        robber_bal = db.setdefault("economy", {}).get(uid, 0)
        target_bal = db.setdefault("economy", {}).get(tid, 0)
        
        if robber_bal < 100000: return await ctx.send("❌ You need **100,000 🪙** collateral in your bank to rob someone.")
        if target_bal < 100000: return await ctx.send("❌ They are too poor to rob.")
            
        if random.randint(1, 100) <= 40: 
            stolen = int(target_bal * random.uniform(0.1, 0.3))
            db["economy"][uid] += stolen; db["economy"][tid] -= stolen
            embed = discord.Embed(description=f"🥷 **SUCCESS!** You broke in and stole **{stolen:,} 🪙** from {member.mention}!", color=discord.Color.green())
        else:
            fine = int(robber_bal * 0.15)
            db["economy"][uid] -= fine; db["economy"][tid] += fine
            embed = discord.Embed(description=f"🚨 **CAUGHT!** You got busted and paid a **{fine:,} 🪙** fine to {member.mention}.", color=discord.Color.red())
            
        save_db(db)
        await ctx.send(embed=embed)

    # ========================================================================
    # FOMO SHOP & INVENTORY
    # ========================================================================
    @commands.hybrid_command(name="shop", aliases=["store"], description="Browse the rotating Hourly Stock.")
    async def shop(self, ctx):
        await ctx.defer()
        shop_items = db.get("current_shop", [])
        
        if not shop_items:
            db["current_shop"] = roll_stock(); save_db(db)
            shop_items = db["current_shop"]
            
        embed = discord.Embed(title="🛒 The Traveling Merchant", description="*\"My stock rotates every hour. Buy it while you can!\"*\n", color=discord.Color.dark_teal())
        
        for item in shop_items:
            highlight = "**" if item['rarity'] in ["Mythic", "Secret"] else ""
            embed.add_field(
                name=f"{item['icon']} {highlight}{item['name']}{highlight}", 
                value=f"💎 **Rarity:** {item['rarity']}\n💰 **Price:** {item['price']:,} 🪙", 
                inline=False
            )
            
        embed.set_footer(text="Stock resets at the top of the hour! ⏳")
        await ctx.send(embed=embed, view=DynamicShopView(shop_items))

    @commands.hybrid_command(name="inventory", aliases=["inv"], description="View your purchased weapons and items.")
    async def inventory(self, ctx, member: discord.Member = None):
        await ctx.defer()
        target = member or ctx.author
        inv = db.get("inventory", {}).get(str(target.id), [])
        
        if not inv: 
            return await ctx.send(embed=discord.Embed(description=f"🎒 {target.name}'s inventory is completely empty.", color=discord.Color.red()))
            
        item_counts = {}
        for item in inv: item_counts[item] = item_counts.get(item, 0) + 1
            
        lines = [f"**{item}** x{count}" for item, count in item_counts.items()]
        chunks = [lines[i:i + 10] for i in range(0, len(lines), 10)]
        embeds = [discord.Embed(title=f"🎒 {target.name}'s Inventory ({i+1}/{len(chunks)})", description="\n".join(chunk), color=discord.Color.dark_green()) for i, chunk in enumerate(chunks)]
        
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))

    # ========================================================================
    # THE UNIFIED FORGE DASHBOARD
    # ========================================================================
    @commands.hybrid_command(name="forge", aliases=["craft", "recipe"], description="Open the Interactive Forge Hub.")
    async def forge(self, ctx):
        embed = discord.Embed(title="🔥 The Grandmaster's Forge", description="Welcome to the Alchemy Forge.\n\nUse the control panel below to view the current **Weekly Blueprint**, check your required **Materials**, **Forge** a secret artifact, or **Awaken** your duplicates.", color=discord.Color.orange())
        embed.set_image(url="https://media.giphy.com/media/l41YkxvU8c7J7Bba0/giphy.gif")
        await ctx.send(embed=embed, view=ForgeHubView())


async def setup(bot):
    await bot.add_cog(Economy(bot))
