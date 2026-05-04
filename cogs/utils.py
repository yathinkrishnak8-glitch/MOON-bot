
import discord
from discord.ext import commands, tasks
import asyncio
import time
import re
import random
from core import db, save_db, ask_groq, ai_client


# ========================================================================
# COG CLASS: Utils & Tools
# ========================================================================
class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()


    # ========================================================================
    # BACKGROUND TASK: Persistent Reminder Loop
    # Description: Checks the database every 30 seconds for expired reminders.
    # ========================================================================
    @tasks.loop(seconds=30)
    async def reminder_loop(self):
        current_time = time.time()
        reminders = db.setdefault("reminders", {})
        expired = []

        for uid, user_reminders in reminders.items():
            for rem in user_reminders:
                if current_time >= rem["time"]:
                    try:
                        user = await self.bot.fetch_user(int(uid))
                        embed = discord.Embed(title="⏰ Reminder!", description=rem["message"], color=discord.Color.gold())
                        embed.set_footer(text="You asked me to remind you about this!")
                        await user.send(embed=embed)
                    except:
                        pass # DMs are closed, ignore
                    expired.append((uid, rem))

        # Clean up expired reminders
        for uid, rem in expired:
            db["reminders"][uid].remove(rem)
            if not db["reminders"][uid]:
                del db["reminders"][uid]
        
        if expired:
            save_db(db)

    @reminder_loop.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()


    # ========================================================================
    # AI-POWERED UTILITIES (With Token Shields)
    # ========================================================================
    @commands.hybrid_command(name="define", description="AI powered precise dictionary.")
    async def define(self, ctx, word: str): 
        await ctx.defer()
        word = word[:100] # Anti-spam clamp
        if not ai_client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await ask_groq([{"role": "user", "content": f"Provide a precise, 1-2 sentence dictionary definition for the word: '{word}'"}], inject_personality=False)
        await ctx.send(embed=discord.Embed(title=f"📖 Definition: {word.title()}", description=reply, color=discord.Color.dark_blue()))

    @commands.hybrid_command(name="urban", description="AI generated Urban Dictionary slang definitions.")
    async def urban(self, ctx, word: str): 
        await ctx.defer()
        word = word[:100] # Anti-spam clamp
        if not ai_client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await ask_groq([{"role": "user", "content": f"Provide the internet slang 'Urban Dictionary' definition for: '{word}'. Keep it safe for work."}], inject_personality=False)
        await ctx.send(embed=discord.Embed(title=f"🏙️ Urban Slang: {word.title()}", description=reply, color=discord.Color.dark_green()))

    @commands.hybrid_command(name="gothic_translate", description="Translate normal text into dark gothic fantasy lore.")
    async def gothic_translate(self, ctx, *, text: str): 
        await ctx.defer()
        text = text[:1500] # 🔥 TOKEN SHIELD: Max 1500 chars
        if not ai_client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await ask_groq([{"role": "user", "content": f"Rewrite this text into epic, dark gothic fantasy lore:\n{text}"}], inject_personality=False)
        await ctx.send(embed=discord.Embed(title="🦇 Gothic Translation", description=reply, color=discord.Color.purple()))

    @commands.hybrid_command(name="lore", description="Generate an epic AI backstory for the server.")
    async def lore(self, ctx): 
        await ctx.defer()
        if not ai_client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await ask_groq([{"role": "user", "content": f"Generate an epic, 2-paragraph mythic backstory for a kingdom called '{ctx.guild.name}'."}], inject_personality=False)
        await ctx.send(embed=discord.Embed(title=f"📖 The Lore of {ctx.guild.name}", description=reply, color=discord.Color.dark_theme()))

    @commands.hybrid_command(name="debate", description="Start an argument with the AI.")
    async def debate(self, ctx, *, topic: str): 
        await ctx.defer()
        topic = topic[:1500] # 🔥 TOKEN SHIELD
        if not ai_client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        reply = await ask_groq([{"role": "system", "content": "You are a master debater. Aggressively but politely argue the exact opposite of whatever the user says."}, {"role": "user", "content": topic}], inject_personality=False)
        await ctx.send(embed=discord.Embed(title=f"⚖️ Debating: {topic[:50]}...", description=reply, color=discord.Color.dark_grey()))


    # ========================================================================
    # SERVER STATS & ULTIMATE PROFILES
    # ========================================================================
    @commands.hybrid_command(name="profile", description="View a player's complete global profile & stats.")
    async def profile(self, ctx, member: discord.Member = None):
        await ctx.defer()
        target = member or ctx.author
        uid = str(target.id)

        # Gather Database Info
        bal = db.get("economy", {}).get(uid, 0)
        level_data = db.get("levels", {}).get(uid, {"xp": 0, "level": 1})
        lvl = level_data["level"]
        xp = level_data["xp"]
        req_xp = int(150 * (lvl ** 1.5))
        
        # 🔥 VISUAL XP BAR GENERATOR
        ratio = min(xp / req_xp, 1.0) if req_xp > 0 else 0
        filled_blocks = int(ratio * 10)
        xp_bar = f"[{'█' * filled_blocks}{'░' * (10 - filled_blocks)}]"
        
        inv_count = len(db.get("inventory", {}).get(uid, []))
        zoo_count = sum(db.get("zoo", {}).get(uid, {}).values()) 
        warns = len(db.get("warns", {}).get(uid, []))
        is_jailed = uid in db.get("jailed", {})
        afk_status = db.get("afk", {}).get(uid, False)

        embed = discord.Embed(title=f"👤 Profile: {target.name}", color=target.color if target.color != discord.Color.default() else discord.Color.blurple())
        embed.set_thumbnail(url=str(target.display_avatar.url))
        
        embed.add_field(name="⭐ RPG Stats", value=f"**Level:** {lvl}\n**XP:** {xp:,} / {req_xp:,}\n`{xp_bar}`", inline=False)
        embed.add_field(name="💰 Economy", value=f"**Net Worth:** {bal:,} 🪙", inline=True)
        embed.add_field(name="🎒 Collection", value=f"**Items:** {inv_count}\n**Monsters:** {zoo_count}", inline=True)
        
        status_lines = []
        if afk_status: status_lines.append(f"💤 **AFK:** {afk_status}")
        if warns > 0: status_lines.append(f"⚠️ **Warnings:** {warns} active infractions")
        if is_jailed: status_lines.append("⛓️ **Status:** Currently JAILED")
        
        if status_lines: embed.add_field(name="📋 Active Status", value="\n".join(status_lines), inline=False)
        embed.set_footer(text=f"Account created: {target.created_at.strftime('%b %d, %Y')}")
        
        await ctx.send(embed=embed)


    @commands.hybrid_command(name="userhistory", description="Check when a user joined.")
    async def userhistory(self, ctx, m: discord.Member): 
        await ctx.defer()
        embed = discord.Embed(title=f"📜 History: {m.name}", color=discord.Color.blue())
        embed.add_field(name="Account Created", value=m.created_at.strftime('%Y-%m-%d'), inline=False)
        embed.add_field(name="Joined Server", value=m.joined_at.strftime('%Y-%m-%d'), inline=False)
        embed.set_thumbnail(url=str(m.display_avatar.url))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="roleinfo", description="Check how many people have a role.")
    async def roleinfo(self, ctx, r: discord.Role): 
        await ctx.send(embed=discord.Embed(description=f"🛡️ The **{r.name}** role has **{len(r.members)}** members.", color=r.color))

    @commands.hybrid_command(name="serverinfo", description="Get stats about the server.")
    async def serverinfo(self, ctx): 
        await ctx.defer()
        embed = discord.Embed(title=ctx.guild.name, color=discord.Color.gold())
        embed.add_field(name="Owner", value=ctx.guild.owner.mention, inline=True)
        embed.add_field(name="Members", value=ctx.guild.member_count, inline=True)
        embed.add_field(name="Roles", value=len(ctx.guild.roles), inline=True)
        if ctx.guild.icon: embed.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)


    # ========================================================================
    # ADVANCED GIVEAWAY SYSTEM
    # ========================================================================
    @commands.hybrid_command(name="giveaway_start", description="Start a giveaway in the current channel.")
    @commands.has_permissions(manage_messages=True)
    async def giveaway_start(self, ctx, prize: str): 
        await ctx.defer()
        embed = discord.Embed(title=f"🎉 GIVEAWAY: {prize}!", description="React with 🎉 to enter!\n*Admins: Use `/giveaway_roll <message_id>` to pick a winner!*", color=discord.Color.gold())
        m = await ctx.send(embed=embed)
        await m.add_reaction("🎉")

    @commands.hybrid_command(name="giveaway_roll", description="Pick a winner from an active giveaway.")
    @commands.has_permissions(manage_messages=True)
    async def giveaway_roll(self, ctx, message_id: str):
        await ctx.defer()
        try:
            msg = await ctx.channel.fetch_message(int(message_id))
            reaction = discord.utils.get(msg.reactions, str(reaction.emoji) == "🎉")
            
            if not reaction: return await ctx.send("❌ No 🎉 reactions found on that message.")
                
            users = [user async for user in reaction.users() if not user.bot]
            if not users: return await ctx.send("❌ Nobody entered the giveaway!")
                
            winner = random.choice(users)
            await ctx.send(embed=discord.Embed(description=f"🎊 **CONGRATULATIONS** {winner.mention}! You won the giveaway!", color=discord.Color.green()))
        except Exception as e:
            await ctx.send(embed=discord.Embed(description="❌ Could not find that message. Are you in the right channel?", color=discord.Color.red()))


    # ========================================================================
    # RANDOM UTILITIES (Safe Math & Reminders)
    # ========================================================================
    @commands.hybrid_command(name="remindme", description="Set a persistent timer to remind you about something.")
    async def remindme(self, ctx, minutes: int, *, message: str): 
        await ctx.defer()
        if minutes <= 0: return await ctx.send("❌ Minutes must be greater than 0.")
        if minutes > 43200: return await ctx.send("❌ Max reminder time is 30 days.") # 1 month limit
        
        target_time = time.time() + (minutes * 60)
        uid = str(ctx.author.id)
        
        db.setdefault("reminders", {}).setdefault(uid, []).append({"time": target_time, "message": message[:500]})
        save_db(db)
        
        await ctx.send(embed=discord.Embed(description=f"✅ **Saved!** I will DM you in {minutes} minute(s).", color=discord.Color.green()))

    @commands.hybrid_command(name="calc", description="Calculate a math equation securely.")
    async def calc(self, ctx, *, equation: str): 
        await ctx.defer()
        # 🔥 THE VAULT: Strip spaces and run strict Regex
        clean_eq = equation.replace(" ", "")
        if not re.match(r'^[\d\+\-\*\/\(\)\.]+$', clean_eq):
            return await ctx.send(embed=discord.Embed(description="❌ Security Block: Only numbers and basic math operators `( + - * / )` are allowed.", color=discord.Color.red()))
        
        try: 
            # Safe to eval because Regex mathematically blocked all letters/code
            result = eval(clean_eq, {'__builtins__': None}, {})
            await ctx.send(embed=discord.Embed(title="🧮 Habibi Calculator", description=f"**Equation:** `{clean_eq}`\n**Result:** `{result}`", color=discord.Color.green()))
        except ZeroDivisionError:
            await ctx.send(embed=discord.Embed(description="❌ You cannot divide by zero.", color=discord.Color.red()))
        except: 
            await ctx.send(embed=discord.Embed(description="❌ Invalid math format.", color=discord.Color.red()))


async def setup(bot):
    await bot.add_cog(Utils(bot))
