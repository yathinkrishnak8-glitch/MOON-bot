
import discord
from discord.ext import commands, tasks
import random
import asyncio
import json
from core import db, save_db, get_gif, ask_groq, ai_client
from ui import DynamicShopView, PaginationView

# ========================================================================
# UI CLASS: Interactive Server Heist
# ========================================================================
class HeistView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.crew = set()

    @discord.ui.button(label="🔫 Join Crew", style=discord.ButtonStyle.danger)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        if uid in self.crew:
            return await interaction.response.send_message("❌ You are already in the getaway van!", ephemeral=True)
            
        bal = db.setdefault("economy", {}).get(uid, 0)
        if bal < 50000:
            return await interaction.response.send_message("❌ You need at least 50,000 🪙 to buy heist gear to participate.", ephemeral=True)
            
        self.crew.add(uid)
        await interaction.response.send_message(f"✅ You strapped up and joined the crew! ({len(self.crew)} members ready)", ephemeral=True)


# ========================================================================
# COG CLASS: Economy & Grinding
# ========================================================================
class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.shop_restock.start()

    def cog_unload(self):
        self.shop_restock.cancel()

    # ========================================================================
    # BACKGROUND TASK: AI Dynamic Shop Generation
    # Description: Generates 4 unique items every hour.
    # ========================================================================
    @tasks.loop(hours=1)
    async def shop_restock(self):
        if not ai_client: return
        try:
            prompt = "You are an RPG merchant. Generate 4 highly unique, epic, and weird items for a game shop. Output ONLY a raw JSON array of 4 objects. Keys: 'name' (string with an emoji), 'price' (integer between 50000 and 2000000), 'desc' (short funny string). No markdown."
            raw_res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            
            clean = raw_res.replace('```json', '').replace('```', '').strip()
            s, e = clean.find('['), clean.rfind(']')
            items = json.loads(clean[s:e+1])
            
            db["current_shop"] = items
            save_db(db)
        except Exception as e:
            print(f"⚠️ AI Shop Restock Failed: {e}")

    @shop_restock.before_loop
    async def before_restock(self):
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
        # Sort economy dictionary by value (coins) descending
        sorted_eco = sorted(db.get("economy", {}).items(), key=lambda x: x[1], reverse=True)
        
        if not sorted_eco:
            return await ctx.send(embed=discord.Embed(description="The server is completely broke.", color=discord.Color.red()))
            
        embed = discord.Embed(title="🏆 The Forbes Rich List", color=discord.Color.gold())
        
        board = ""
        for i, (uid, coins) in enumerate(sorted_eco[:10]):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "💸"
            board += f"{medal} **<@{uid}>** — {coins:,} 🪙\n"
            
        embed.description = board
        await ctx.send(embed=embed)


    # ========================================================================
    # DAILY & WEEKLY CLAIM
    # ========================================================================
    @commands.hybrid_command(name="daily", description="Claim your daily 500,000 coins.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        db.setdefault("economy", {})[uid] = db["economy"].get(uid, 0) + 500000
        save_db(db)
        
        embed = discord.Embed(title="📅 Daily Reward", description="You claimed your daily **500,000 🪙**!", color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="weekly", description="Claim your weekly 5,000,000 coins.")
    @commands.cooldown(1, 604800, commands.BucketType.user)
    async def weekly(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        db.setdefault("economy", {})[uid] = db["economy"].get(uid, 0) + 5000000
        save_db(db)
        
        embed = discord.Embed(title="📅 Weekly Reward", description="You claimed your massive weekly **5,000,000 🪙**!", color=discord.Color.gold())
        await ctx.send(embed=embed)


    # ========================================================================
    # GRINDING: WORK & CRIME
    # ========================================================================
    @commands.hybrid_command(name="work", description="Work an honest job for coins.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def work(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        earned = random.randint(50000, 150000)
        
        jobs = [
            f"You flipped burgers at McDonald's and earned **{earned:,} 🪙**.",
            f"You coded a Discord bot in Python and sold it for **{earned:,} 🪙**.",
            f"You mowed lawns in the neighborhood and made **{earned:,} 🪙**.",
            f"You streamed on Twitch to 3 viewers and got donated **{earned:,} 🪙**."
        ]
        
        db.setdefault("economy", {})[uid] = db["economy"].get(uid, 0) + earned
        save_db(db)
        
        embed = discord.Embed(description=f"💼 {random.choice(jobs)}", color=discord.Color.blue())
        embed.set_image(url=get_gif("work"))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="crime", description="Commit a crime. High risk, high reward.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def crime(self, ctx):
        await ctx.defer()
        uid = str(ctx.author.id)
        bal = db.setdefault("economy", {}).get(uid, 0)
        
        if random.choice([True, False]): # 50% chance to succeed
            earned = random.randint(150000, 400000)
            db["economy"][uid] += earned
            crimes = [
                f"You successfully hacked the Pentagon and stole **{earned:,} 🪙**!",
                f"You robbed a convenience store and got away with **{earned:,} 🪙**!",
                f"You sold illegal anime figures and made **{earned:,} 🪙**!"
            ]
            embed = discord.Embed(description=f"🦹‍♂️ {random.choice(crimes)}", color=discord.Color.green())
            embed.set_image(url=get_gif("crime_win"))
        else:
            fine = random.randint(50000, 150000)
            db["economy"][uid] = max(0, bal - fine)
            embed = discord.Embed(description=f"🚓 **BUSTED!** The police caught you. You were fined **{fine:,} 🪙**.", color=discord.Color.red())
            embed.set_image(url=get_gif("crime_lose"))
            
        save_db(db)
        await ctx.send(embed=embed)


    # ========================================================================
    # STEALING & HEISTS
    # ========================================================================
    @commands.hybrid_command(name="rob", description="Attempt to steal from another player's bank.")
    @commands.cooldown(1, 7200, commands.BucketType.user)
    async def rob(self, ctx, member: discord.Member):
        await ctx.defer()
        uid = str(ctx.author.id)
        tid = str(member.id)
        
        # 🛡️ EXPLOIT PATCHES
        if member.bot:
            return await ctx.send(embed=discord.Embed(description="❌ You can't rob a bot. They have firewall protection.", color=discord.Color.red()))
        if uid == tid:
            return await ctx.send(embed=discord.Embed(description="❌ You tried to rob yourself. Are you okay?", color=discord.Color.red()))
            
        robber_bal = db.setdefault("economy", {}).get(uid, 0)
        target_bal = db.setdefault("economy", {}).get(tid, 0)
        
        if robber_bal < 100000:
            return await ctx.send(embed=discord.Embed(description="❌ You need at least **100,000 🪙** as collateral to rob someone.", color=discord.Color.red()))
        if target_bal < 100000:
            return await ctx.send(embed=discord.Embed(description=f"❌ **{member.name}** is too poor to rob. Leave them alone.", color=discord.Color.red()))
            
        if random.randint(1, 100) <= 40: # 40% success rate
            stolen = int(target_bal * random.uniform(0.1, 0.3)) # Steal 10% to 30%
            db["economy"][uid] += stolen
            db["economy"][tid] -= stolen
            embed = discord.Embed(description=f"🥷 **SUCCESS!** You broke into {member.mention}'s vault and stole **{stolen:,} 🪙**!", color=discord.Color.green())
            embed.set_image(url=get_gif("rob_win"))
        else:
            fine = int(robber_bal * 0.15) # Lose 15% of your bank to the target
            db["economy"][uid] -= fine
            db["economy"][tid] += fine
            embed = discord.Embed(description=f"🚨 **CAUGHT!** {member.mention} caught you slipping. You had to pay them **{fine:,} 🪙** in damages.", color=discord.Color.red())
            embed.set_image(url=get_gif("rob_lose"))
            
        save_db(db)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="heist", description="Start a server-wide vault heist.")
    @commands.cooldown(1, 14400, commands.BucketType.guild) # Once per 4 hours per server
    async def heist(self, ctx):
        view = HeistView()
        embed = discord.Embed(title="🏦 VAULT HEIST INITIATED", description=f"**{ctx.author.name}** is organizing a bank heist!\n\nYou have **30 seconds** to join the crew. You need at least **3 members** to pull this off.", color=discord.Color.dark_red())
        embed.set_image(url=get_gif("heist"))
        
        msg = await ctx.send(embed=embed, view=view)
        await asyncio.sleep(30)
        
        # Lock the view
        for child in view.children: child.disabled = True
        await msg.edit(view=view)
        
        if len(view.crew) < 3:
            return await ctx.send(embed=discord.Embed(description="🚓 **HEIST FAILED!** Not enough people joined the crew. The driver got scared and bailed.", color=discord.Color.red()))
            
        if random.choice([True, False]): # 50% chance for the whole crew
            total_loot = random.randint(5000000, 15000000)
            split = total_loot // len(view.crew)
            
            mentions = []
            for crew_id in view.crew:
                db["economy"][crew_id] = db.setdefault("economy", {}).get(crew_id, 0) + split
                mentions.append(f"<@{crew_id}>")
                
            save_db(db)
            await ctx.send(embed=discord.Embed(title="💰 HEIST SUCCESSFUL!", description=f"The crew blew the vault open and stole **{total_loot:,} 🪙**!\n\n**Payout per member:** {split:,} 🪙\n**Crew:** {', '.join(mentions)}", color=discord.Color.green()))
        else:
            mentions = []
            for crew_id in view.crew:
                fine = 250000
                db["economy"][crew_id] = max(0, db.setdefault("economy", {}).get(crew_id, 0) - fine)
                mentions.append(f"<@{crew_id}>")
                
            save_db(db)
            await ctx.send(embed=discord.Embed(title="🚨 SWAT DEPLOYED", description=f"The heist was a setup! The crew was ambushed by SWAT and fined **250,000 🪙** each.\n\n**Busted:** {', '.join(mentions)}", color=discord.Color.dark_red()))


    # ========================================================================
    # AI SHOP & CRAFTING
    # ========================================================================
    @commands.hybrid_command(name="shop", description="Browse the AI generated Black Market items.")
    async def shop(self, ctx):
        await ctx.defer()
        shop_items = db.get("current_shop", [])
        if not shop_items:
            return await ctx.send(embed=discord.Embed(description="📦 The shop is currently empty. Waiting for AI restock...", color=discord.Color.red()))
            
        embed = discord.Embed(title="🛒 The Black Market", description="These mysterious items were generated by the AI.\nClick a button to purchase an item.", color=discord.Color.blurple())
        for item in shop_items:
            embed.add_field(name=f"{item['name']}", value=f"💰 **Price:** {item['price']:,} 🪙\n*\"{item['desc']}\"*", inline=False)
            
        await ctx.send(embed=embed, view=DynamicShopView(shop_items))

    @commands.hybrid_command(name="inventory", aliases=["inv"], description="View your purchased items.")
    async def inventory(self, ctx, member: discord.Member = None):
        await ctx.defer()
        target = member or ctx.author
        uid = str(target.id)
        
        inv = db.get("inventory", {}).get(uid, [])
        if not inv:
            return await ctx.send(embed=discord.Embed(description=f"🎒 {target.name}'s inventory is completely empty.", color=discord.Color.red()))
            
        # Count duplicates dynamically
        item_counts = {}
        for item in inv: item_counts[item] = item_counts.get(item, 0) + 1
            
        lines = [f"**{item}** x{count}" for item, count in item_counts.items()]
        chunks = [lines[i:i + 10] for i in range(0, len(lines), 10)]
        
        embeds = [discord.Embed(title=f"🎒 {target.name}'s Inventory ({i+1}/{len(chunks)})", description="\n".join(chunk), color=discord.Color.dark_green()) for i, chunk in enumerate(chunks)]
        await ctx.send(embed=embeds[0], view=PaginationView(ctx, embeds))

    @commands.hybrid_command(name="craft", description="Fuse two items together to create a God-tier AI weapon.")
    async def craft(self, ctx, item1: str, item2: str):
        await ctx.defer()
        uid = str(ctx.author.id)
        inv = db.setdefault("inventory", {}).get(uid, [])
        
        # Case insensitive exact matching
        exact_i1 = next((i for i in inv if i.lower() == item1.lower()), None)
        exact_i2 = next((i for i in inv if i.lower() == item2.lower()), None)
        
        # If they try to fuse the exact same item, ensure they have at least 2 of them
        if exact_i1 and exact_i1 == exact_i2 and inv.count(exact_i1) < 2:
            return await ctx.send(embed=discord.Embed(description=f"❌ You need **2x** of `{exact_i1}` to craft with it twice.", color=discord.Color.red()))
            
        if not exact_i1 or not exact_i2:
            return await ctx.send(embed=discord.Embed(description="❌ You do not own those items. Check your exact spelling in `/inventory`.", color=discord.Color.red()))
            
        if not ai_client: return await ctx.send(embed=discord.Embed(description="❌ The AI Forge is offline.", color=discord.Color.red()))
            
        prompt = f"I am fusing the item '{exact_i1}' and the item '{exact_i2}'. Generate a highly destructive, God-tier weapon/item. Output ONLY a raw JSON object with keys: 'name' (string with an epic emoji) and 'desc' (epic string). No markdown."
        
        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            clean = res.replace('```json', '').replace('```', '').strip()
            s, e = clean.find('{'), clean.rfind('}')
            crafted = json.loads(clean[s:e+1])
            
            # Remove old items
            db["inventory"][uid].remove(exact_i1)
            db["inventory"][uid].remove(exact_i2)
            
            # Add new item
            full_name = f"⚒️ {crafted['name']} (Forged)"
            db["inventory"][uid].append(full_name)
            save_db(db)
            
            embed = discord.Embed(title="⚒️ FORGE SUCCESSFUL", description=f"You sacrificed **{exact_i1}** and **{exact_i2}**...", color=discord.Color.dark_purple())
            embed.add_field(name=full_name, value=f"*{crafted['desc']}*", inline=False)
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(embed=discord.Embed(description="❌ The forge overheated and failed. Your items are safe.", color=discord.Color.red()))


async def setup(bot):
    await bot.add_cog(Economy(bot))
