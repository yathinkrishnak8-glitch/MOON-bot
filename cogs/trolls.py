
import discord
from discord.ext import commands
import random
import asyncio
from core import db, save_db, get_gif, ask_groq, ai_client

class Trolls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def generate_progress_bar(self, percentage):
        """Helper to create a visual loading bar for raters."""
        filled = int((percentage / 100) * 10)
        return f"[{'█' * filled}{'░' * (10 - filled)}]"

    # ========================================================================
    # RATER COMMANDS (Upgraded with Visual Bars)
    # ========================================================================
    @commands.command(name="howgay", help="The ultimate test of true colors.")
    async def howgay(self, ctx, m: discord.Member = None): 
        target = m or ctx.author
        percent = random.randint(0, 100)
        bar = self.generate_progress_bar(percent)
        await ctx.send(embed=discord.Embed(description=f"🏳️‍🌈 **{target.name}** is **{percent}%** gay.\n`{bar}`", color=discord.Color.magenta()))

    @commands.command(name="simpmeter", help="Expose the simps.")
    async def simpmeter(self, ctx, m: discord.Member = None): 
        target = m or ctx.author
        percent = random.randint(0, 100)
        bar = self.generate_progress_bar(percent)
        await ctx.send(embed=discord.Embed(description=f"😳 **{target.name}** is **{percent}%** simp.\n`{bar}`", color=discord.Color.purple()))

    @commands.command(name="susmeter", help="Who is the impostor?")
    async def susmeter(self, ctx, m: discord.Member = None): 
        target = m or ctx.author
        percent = random.randint(0, 100)
        bar = self.generate_progress_bar(percent)
        await ctx.send(embed=discord.Embed(description=f"📮 **{target.name}** is **{percent}%** sus.\n`{bar}`", color=discord.Color.red()))

    @commands.command(name="ship", help="Ship two users together.")
    async def ship(self, ctx, m1: discord.Member, m2: discord.Member = None): 
        target2 = m2 or ctx.author
        percent = random.randint(0, 100)
        bar = self.generate_progress_bar(percent)
        
        if percent >= 75: msg = "❤️ True Love!"
        elif percent >= 40: msg = "🔥 There is a spark."
        else: msg = "💔 Absolutely not."
            
        embed = discord.Embed(title="💘 Matchmaker", description=f"**{m1.name}** x **{target2.name}**\n\n**Match:** {percent}%\n`{bar}`\n*{msg}*", color=discord.Color.pink())
        await ctx.send(embed=embed)


    # ========================================================================
    # CHAOS & PRANKS (Exploit Patched)
    # ========================================================================
    @commands.command(name="fakeban", help="Scare the life out of someone.")
    async def fakeban(self, ctx, m: discord.Member): 
        embed = discord.Embed(description=f"🔨 **{m.name}** has been permanently banned from the server.", color=discord.Color.red())
        embed.set_image(url=get_gif("fakeban"))
        await ctx.send(embed=embed)

    @commands.command(name="rickroll", aliases=["nitro"], help="Anonymously DM a user a 'Nitro' link.")
    @commands.cooldown(1, 300, commands.BucketType.user) # 5 min cooldown to prevent DM harassment
    async def rickroll(self, ctx, m: discord.Member):
        try: 
            await m.send("🎁 **You've been gifted 1 Month of Discord Nitro!**\nClaim here: https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            await ctx.send(embed=discord.Embed(description=f"🤫 Successfully sent the bait to {m.name}.", color=discord.Color.green()))
        except: 
            await ctx.send(embed=discord.Embed(description=f"❌ {m.name} has their DMs closed. Mission failed.", color=discord.Color.red()))

    @commands.command(name="hack", help="Run a realistic fake hacking terminal on a user.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def hack(self, ctx, m: discord.Member): 
        ip = f"{random.randint(11,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"
        passwords = ["ilovekittens123", "password321", "ninja_gamer99", "admin1234", "dont_hack_me"]
        searches = ["how to talk to girls", "free robux generator no virus", "why does my tummy hurt", "how to get unbanned from roblox"]
        
        msg = await ctx.send(embed=discord.Embed(description=f"💻 **Hacking {m.name}...** [10%]", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        await msg.edit(embed=discord.Embed(description=f"📂 **Bypassing firewall...**\nIP Address Found: `{ip}` [45%]", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        await msg.edit(embed=discord.Embed(description=f"📧 **Cracking Database...**\nEmail: `{m.name.lower()}@gmail.com`\nPassword: `{random.choice(passwords)}` [75%]", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        await msg.edit(embed=discord.Embed(description=f"🔍 **Stealing search history...**\nLast Search: *\"{random.choice(searches)}\"* [99%]", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        await msg.edit(embed=discord.Embed(description=f"✅ **Hack Complete!** All of {m.mention}'s data has been sold to the dark web.", color=discord.Color.green()))

    @commands.command(name="jailbreak", help="Attempt to break a jailed user out (HIGH RISK).")
    @commands.cooldown(1, 600, commands.BucketType.user) # 10 minute cooldown
    async def jailbreak(self, ctx, m: discord.Member):
        uid = str(ctx.author.id)
        
        if str(m.id) not in db.get("jailed", {}):
            return await ctx.send(f"❌ {m.name} is not even in jail, bro.")
            
        bal = db.setdefault("economy", {}).get(uid, 0)
        penalty = 50000
        
        if bal < penalty:
            return await ctx.send(embed=discord.Embed(description=f"❌ You need at least **{penalty:,} 🪙** to attempt a jailbreak (in case you need to bribe the guards).", color=discord.Color.red()))

        # 25% Success Rate
        if random.randint(1, 100) <= 25: 
            jr = discord.utils.get(ctx.guild.roles, name="Jailed")
            if jr and jr in m.roles: await m.remove_roles(jr)
            
            # Restore their old roles
            saved_roles = db["jailed"].pop(str(m.id), [])
            for r_id in saved_roles:
                role = ctx.guild.get_role(r_id)
                if role: 
                    try: await m.add_roles(role)
                    except: pass
            save_db(db)
            
            await ctx.send(embed=discord.Embed(title="🔓 JAILBREAK SUCCESSFUL", description=f"**{ctx.author.name}** knocked out the guards and freed **{m.name}**!", color=discord.Color.green()))
        else: 
            # Failed: Deduct penalty
            db["economy"][uid] -= penalty
            save_db(db)
            await ctx.send(embed=discord.Embed(title="🚨 JAILBREAK FAILED", description=f"The guards caught **{ctx.author.name}** trying to pick the lock!\n\nYou were forced to pay a **{penalty:,} 🪙** bribe to walk away free.", color=discord.Color.dark_red()))


    # ========================================================================
    # SOCIAL & AI-POWERED FUN
    # ========================================================================
    @commands.command(name="roast", help="AI dynamically roasts someone.")
    async def roast(self, ctx, m: discord.Member): 
        if not ai_client: return await ctx.send(f"🔥 {m.mention}, you're like a cloud. When you disappear, it's a beautiful day.")
        
        async with ctx.channel.typing():
            try:
                reply = await ask_groq([{"role": "user", "content": f"Write a short, brutal, hilarious 1-sentence roast directed at a user named {m.name}."}], inject_personality=False)
                await ctx.send(embed=discord.Embed(description=f"🔥 {m.mention}, {reply}", color=discord.Color.orange()))
            except:
                await ctx.send(f"🔥 {m.mention}, you aren't even worth the AI's compute time.")

    @commands.command(name="compliment", help="AI generates a nice compliment.")
    async def compliment(self, ctx, m: discord.Member): 
        if not ai_client: return await ctx.send(f"💖 {m.mention}, you actually have really good taste in Discord bots.")
        
        async with ctx.channel.typing():
            try:
                reply = await ask_groq([{"role": "user", "content": f"Write a short, incredibly wholesome and creative 1-sentence compliment for a user named {m.name}."}], inject_personality=False)
                await ctx.send(embed=discord.Embed(description=f"💖 {m.mention}, {reply}", color=discord.Color.pink()))
            except:
                await ctx.send(f"💖 {m.mention}, you are epic.")

    @commands.command(name="dadjoke", help="AI generates a terrible dad joke.")
    async def dadjoke(self, ctx): 
        if not ai_client: return await ctx.send("🧔 **Joke:** Why don't skeletons fight each other? They don't have the guts.")
        
        async with ctx.channel.typing():
            try:
                reply = await ask_groq([{"role": "user", "content": "Tell me a completely original, incredibly cheesy dad joke."}], inject_personality=False)
                await ctx.send(embed=discord.Embed(description=f"🧔 **Joke:** {reply}", color=discord.Color.blue()))
            except:
                pass

    @commands.command(name="confess", help="Send an anonymous confession safely.")
    async def confess(self, ctx, *, msg: str): 
        try: 
            await ctx.message.delete()
        except discord.Forbidden:
            # IDENTITY LEAK PATCH: Abort if bot can't delete the message!
            try: await ctx.author.send("❌ I don't have 'Manage Messages' permissions in that channel, so I couldn't delete your message. Your identity was exposed! Confession aborted.")
            except: pass
            return
            
        await ctx.send(embed=discord.Embed(title="🤫 Anonymous Confession", description=msg, color=discord.Color.dark_theme()))

    @commands.command(name="kill", help="End someone's blocky existence.")
    async def kill(self, ctx, m: discord.Member): 
        deaths = [
            "was struck by lightning.", "fell off a cliff while looking at their phone.", 
            "stepped on a Lego and perished.", "was eaten by a wild HabibiBot."
        ]
        await ctx.send(embed=discord.Embed(description=f"☠️ **{m.name}** {random.choice(deaths)}", color=discord.Color.dark_red()))

    @commands.command(name="revive", help="Bring them back.")
    async def revive(self, ctx, m: discord.Member): 
        await ctx.send(embed=discord.Embed(description=f"👼 **{m.name}** was resurrected by the Habibi Gods!", color=discord.Color.gold()))

    @commands.command(name="spank", help="Discipline them.")
    async def spank(self, ctx, m: discord.Member): 
        await ctx.send(embed=discord.Embed(description=f"🤚 **{ctx.author.name} furiously spanked {m.name}!**", color=discord.Color.dark_orange()))

    @commands.command(name="eightball", aliases=["8ball"], help="Ask the magic 8-ball a question.")
    async def eightball(self, ctx, *, q: str): 
        responses = ["Yes, obviously.", "No way, bro.", "Maybe, but don't count on it.", "100% facts.", "Are you kidding? No.", "Signs point to yes.", "My sources say nah."]
        await ctx.send(embed=discord.Embed(title="🎱 Magic 8-Ball", description=f"**Q:** {q}\n**A:** {random.choice(responses)}", color=discord.Color.dark_grey()))

    @commands.command(name="choose", help="Make the bot choose between multiple things (comma separated).")
    async def choose(self, ctx, *, options: str): 
        opts = [o.strip() for o in options.split(",") if o.strip()]
        if len(opts) < 2: return await ctx.send("❌ Give me at least 2 things to choose from, separated by commas. (e.g. `!choose Apple, Banana`)")
        await ctx.send(embed=discord.Embed(description=f"🤔 I choose: **{random.choice(opts)}**", color=discord.Color.teal()))


async def setup(bot):
    await bot.add_cog(Trolls(bot))
