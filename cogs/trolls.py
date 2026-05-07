import discord
from discord.ext import commands
import random
import asyncio
import string
from core import db, save_db, get_gif, ask_groq, ai_client

class Trolls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def generate_progress_bar(self, percentage):
        """Helper to create a visual loading bar for raters."""
        filled = int((percentage / 100) * 10)
        return f"[{'█' * filled}{'░' * (10 - filled)}]"

    # ========================================================================
    # RATER COMMANDS (Now beautifully connected to AI for dynamic reactions)
    # ========================================================================
    @commands.command(name="howgay", help="The ultimate test of true colors.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def howgay(self, ctx, m: discord.Member = None): 
        target = m or ctx.author
        percent = random.randint(0, 100)
        bar = self.generate_progress_bar(percent)
        
        ai_comment = ""
        if ai_client:
            try:
                prompt = f"User {target.name} just scored {percent}% on a 'How Gay Are You' test. Write a funny, sarcastic 1-sentence reaction."
                res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
                ai_comment = f"\n\n🤖 *{res}*"
            except: pass

        embed = discord.Embed(description=f"🏳️‍🌈 **{target.name}** is **{percent}%** gay.\n`{bar}`{ai_comment}", color=discord.Color.magenta())
        embed.set_image(url=get_gif("howgay"))
        await ctx.send(embed=embed)

    @commands.command(name="simpmeter", aliases=["simp"], help="Expose the simps.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def simpmeter(self, ctx, m: discord.Member = None): 
        target = m or ctx.author
        percent = random.randint(0, 100)
        bar = self.generate_progress_bar(percent)
        
        ai_comment = ""
        if ai_client:
            try:
                prompt = f"User {target.name} just scored {percent}% on a 'Simp Meter' test. Write a brutal, funny 1-sentence reaction exposing them."
                res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
                ai_comment = f"\n\n🤖 *{res}*"
            except: pass
            
        embed = discord.Embed(description=f"😳 **{target.name}** is **{percent}%** simp.\n`{bar}`{ai_comment}", color=discord.Color.purple())
        embed.set_image(url=get_gif("simpmeter"))
        await ctx.send(embed=embed)

    @commands.command(name="susmeter", aliases=["sus"], help="Who is the impostor?")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def susmeter(self, ctx, m: discord.Member = None): 
        target = m or ctx.author
        percent = random.randint(0, 100)
        bar = self.generate_progress_bar(percent)
        
        ai_comment = ""
        if ai_client:
            try:
                prompt = f"User {target.name} scored {percent}% on an Among Us 'Sus Meter'. Write a funny 1-sentence reaction accusing them or defending them."
                res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
                ai_comment = f"\n\n🤖 *{res}*"
            except: pass
            
        embed = discord.Embed(description=f"📮 **{target.name}** is **{percent}%** sus.\n`{bar}`{ai_comment}", color=discord.Color.red())
        embed.set_image(url=get_gif("susmeter"))
        await ctx.send(embed=embed)

    @commands.command(name="rizz", help="Check someone's unspoken rizz.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def rizz(self, ctx, m: discord.Member = None): 
        target = m or ctx.author
        percent = random.randint(0, 100)
        bar = self.generate_progress_bar(percent)
        
        ai_comment = ""
        if ai_client:
            try:
                prompt = f"User {target.name} has a 'Rizz Level' of {percent}%. Write a funny 1-sentence reaction praising or destroying their flirting skills."
                res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
                ai_comment = f"\n\n🤖 *{res}*"
            except: pass
            
        embed = discord.Embed(description=f"😎 **{target.name}'s** Rizz Level is **{percent}%**.\n`{bar}`{ai_comment}", color=discord.Color.gold())
        embed.set_image(url=get_gif("rizz"))
        await ctx.send(embed=embed)

    @commands.command(name="iq", help="Accurately measure someone's braincells.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def iq(self, ctx, m: discord.Member = None): 
        target = m or ctx.author
        iq = random.randint(10, 200)
        
        ai_comment = ""
        if ai_client:
            try:
                prompt = f"User {target.name} just took an IQ test and scored {iq}. Write a hilarious 1-sentence reaction about their brain capacity."
                res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
                ai_comment = f"\n*{res}*"
            except: 
                if iq < 50: ai_comment = "\n*Absolute monkey brain.*"
                elif iq > 150: ai_comment = "\n*Albert Einstein has been real quiet since this dropped.*"
        
        embed = discord.Embed(description=f"🧠 **{target.name}'s** IQ is **{iq}**.{ai_comment}", color=discord.Color.blue())
        embed.set_image(url=get_gif("iq"))
        await ctx.send(embed=embed)

    @commands.command(name="ship", help="Ship two users together.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ship(self, ctx, m1: discord.Member, m2: discord.Member = None): 
        target2 = m2 or ctx.author
        percent = random.randint(0, 100)
        bar = self.generate_progress_bar(percent)
        
        ai_comment = "*❤️ Let's see how this goes...*"
        if ai_client:
            try:
                prompt = f"Matchmaker bot just shipped {m1.name} and {target2.name} with a compatibility rating of {percent}%. Write a funny 1-sentence prediction about their relationship."
                res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
                ai_comment = f"*{res}*"
            except: pass
            
        embed = discord.Embed(title="💘 Matchmaker", description=f"**{m1.name}** x **{target2.name}**\n\n**Match:** {percent}%\n`{bar}`\n\n🤖 {ai_comment}", color=discord.Color.pink())
        embed.set_image(url=get_gif("ship"))
        await ctx.send(embed=embed)


    # ========================================================================
    # CHAOS & PRANKS
    # ========================================================================
    @commands.command(name="fakeban", help="Scare the life out of someone.")
    async def fakeban(self, ctx, m: discord.Member): 
        embed = discord.Embed(description=f"🔨 **{m.name}** has been permanently banned from the server.", color=discord.Color.red())
        embed.set_image(url=get_gif("fakeban"))
        await ctx.send(embed=embed)

    @commands.command(name="token", help="Run a terrifying fake Discord token grabber.")
    async def token(self, ctx, m: discord.Member): 
        chars = string.ascii_letters + string.digits
        fake_token = ''.join(random.choice(chars) for _ in range(24)) + "." + ''.join(random.choice(chars) for _ in range(6)) + "." + ''.join(random.choice(chars) for _ in range(27))
        
        embed = discord.Embed(title="⚠️ COMPROMISED", description=f"Successfully extracted Discord Login Token for **{m.name}**:\n\n`{fake_token}`", color=discord.Color.red())
        embed.set_image(url=get_gif("token"))
        await ctx.send(embed=embed)

    @commands.command(name="rickroll", aliases=["nitro"], help="Anonymously DM a user a 'Nitro' link.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def rickroll(self, ctx, m: discord.Member):
        try: 
            await m.send("🎁 **You've been gifted 1 Month of Discord Nitro!**\nClaim here: https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            embed = discord.Embed(description=f"🤫 Successfully sent the bait to {m.name}.", color=discord.Color.green())
            embed.set_image(url=get_gif("rickroll"))
            await ctx.send(embed=embed)
        except: 
            await ctx.send(embed=discord.Embed(description=f"❌ {m.name} has their DMs closed. Mission failed.", color=discord.Color.red()))

    @commands.command(name="hack", help="Run a realistic fake hacking terminal on a user.")
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def hack(self, ctx, m: discord.Member): 
        ip = f"{random.randint(11,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"
        passwords = ["ilovekittens123", "password321", "ninja_gamer99", "admin1234", "dont_hack_me"]
        search_history = "how to talk to girls"
        
        # Connect hack to AI to dynamically generate embarrassing search history based on their name!
        if ai_client:
            try:
                prompt = f"Generate 1 highly embarrassing, funny, PG-13 internet search query that a gamer named '{m.name}' might search for. Output ONLY the query."
                search_history = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
            except: pass

        msg = await ctx.send(embed=discord.Embed(description=f"💻 **Hacking {m.name}...** [10%]", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        await msg.edit(embed=discord.Embed(description=f"📂 **Bypassing firewall...**\nIP Address Found: `{ip}` [45%]", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        await msg.edit(embed=discord.Embed(description=f"📧 **Cracking Database...**\nEmail: `{m.name.lower().replace(' ', '')}@gmail.com`\nPassword: `{random.choice(passwords)}` [75%]", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        await msg.edit(embed=discord.Embed(description=f"🔍 **Stealing search history...**\nLast Search: *\"{search_history.strip('\"')}\"* [99%]", color=discord.Color.dark_grey()))
        await asyncio.sleep(1.5)
        
        embed = discord.Embed(description=f"✅ **Hack Complete!** All of {m.mention}'s data has been sold to the dark web.", color=discord.Color.green())
        embed.set_image(url=get_gif("hack"))
        await msg.edit(embed=embed)

    @commands.command(name="jailbreak", help="Attempt to break a jailed user out (HIGH RISK).")
    @commands.cooldown(1, 600, commands.BucketType.user)
    async def jailbreak(self, ctx, m: discord.Member):
        uid = str(ctx.author.id)
        
        if str(m.id) not in db.get("jailed", {}):
            return await ctx.send(f"❌ {m.name} is not even in jail, bro.")
            
        bal = db.setdefault("economy", {}).get(uid, 0)
        penalty = 50000
        
        if bal < penalty:
            return await ctx.send(embed=discord.Embed(description=f"❌ You need at least **{penalty:,} 🪙** to attempt a jailbreak.", color=discord.Color.red()))

        # 25% Success Rate
        if random.randint(1, 100) <= 25: 
            jr = discord.utils.get(ctx.guild.roles, name="Jailed")
            if jr and jr in m.roles: await m.remove_roles(jr)
            
            saved_roles = db["jailed"].pop(str(m.id), [])
            for r_id in saved_roles:
                role = ctx.guild.get_role(r_id)
                if role: 
                    try: await m.add_roles(role)
                    except: pass
            save_db(db)
            
            embed = discord.Embed(title="🔓 JAILBREAK SUCCESSFUL", description=f"**{ctx.author.name}** knocked out the guards and freed **{m.name}**!", color=discord.Color.green())
            embed.set_image(url=get_gif("jailbreak_success"))
            await ctx.send(embed=embed)
        else: 
            db["economy"][uid] -= penalty
            save_db(db)
            embed = discord.Embed(title="🚨 JAILBREAK FAILED", description=f"The guards caught **{ctx.author.name}** trying to pick the lock!\n\nYou were forced to pay a **{penalty:,} 🪙** bribe to walk away free.", color=discord.Color.dark_red())
            embed.set_image(url=get_gif("jailbreak_fail"))
            await ctx.send(embed=embed)


    # ========================================================================
    # SOCIAL & AI-POWERED FUN
    # ========================================================================
    @commands.command(name="roast", help="AI dynamically roasts someone.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def roast(self, ctx, m: discord.Member): 
        embed = discord.Embed(color=discord.Color.orange())
        embed.set_image(url=get_gif("roast"))
        if not ai_client: 
            embed.description = f"🔥 {m.mention}, you're like a cloud. When you disappear, it's a beautiful day."
            return await ctx.send(embed=embed)
        
        async with ctx.channel.typing():
            try:
                reply = await asyncio.wait_for(ask_groq([{"role": "user", "content": f"Write a short, brutal, hilarious 1-sentence roast directed at a user named {m.name}."}], inject_personality=False), timeout=5.0)
                embed.description = f"🔥 {m.mention}, {reply}"
                await ctx.send(embed=embed)
            except:
                embed.description = f"🔥 {m.mention}, you aren't even worth the AI's compute time."
                await ctx.send(embed=embed)

    @commands.command(name="compliment", help="AI generates a nice compliment.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def compliment(self, ctx, m: discord.Member): 
        embed = discord.Embed(color=discord.Color.pink())
        embed.set_image(url=get_gif("compliment"))
        if not ai_client: 
            embed.description = f"💖 {m.mention}, you actually have really good taste in Discord bots."
            return await ctx.send(embed=embed)
        
        async with ctx.channel.typing():
            try:
                reply = await asyncio.wait_for(ask_groq([{"role": "user", "content": f"Write a short, incredibly wholesome and creative 1-sentence compliment for a user named {m.name}."}], inject_personality=False), timeout=5.0)
                embed.description = f"💖 {m.mention}, {reply}"
                await ctx.send(embed=embed)
            except:
                embed.description = f"💖 {m.mention}, you are epic."
                await ctx.send(embed=embed)

    @commands.command(name="dadjoke", help="AI generates a terrible dad joke.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def dadjoke(self, ctx): 
        embed = discord.Embed(color=discord.Color.blue())
        embed.set_image(url=get_gif("dadjoke"))
        if not ai_client: 
            embed.description = "🧔 **Joke:** Why don't skeletons fight each other? They don't have the guts."
            return await ctx.send(embed=embed)
        
        async with ctx.channel.typing():
            try:
                reply = await asyncio.wait_for(ask_groq([{"role": "user", "content": "Tell me a completely original, incredibly cheesy dad joke."}], inject_personality=False), timeout=5.0)
                embed.description = f"🧔 **Joke:** {reply}"
                await ctx.send(embed=embed)
            except: pass

    @commands.command(name="confess", help="Send an anonymous confession safely.")
    async def confess(self, ctx, *, msg: str): 
        try: 
            await ctx.message.delete()
        except discord.Forbidden:
            try: await ctx.author.send("❌ I don't have 'Manage Messages' permissions in that channel, so I couldn't delete your message. Your identity was exposed! Confession aborted.")
            except: pass
            return
            
        embed = discord.Embed(title="🤫 Anonymous Confession", description=msg, color=discord.Color.dark_theme())
        embed.set_image(url=get_gif("confess"))
        await ctx.send(embed=embed)


    # ========================================================================
    # INTERACTIVE ANIME / ACTION TROLLS (AI Enhanced)
    # ========================================================================
    async def generate_action_text(self, action_name, user, target, default_text):
        """Helper to let the AI narrate the actions dynamically."""
        if not ai_client: return default_text
        try:
            prompt = f"Describe {user} fiercely doing a '{action_name}' action to {target} in a dramatic, funny, anime-style 1-sentence narration."
            res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=4.0)
            return f"**{res}**"
        except:
            return default_text

    @commands.command(name="kill", help="End someone's blocky existence.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def kill(self, ctx, m: discord.Member): 
        deaths = ["was struck by lightning.", "fell off a cliff while looking at their phone.", "stepped on a Lego and perished.", "was eaten by a wild HabibiBot."]
        default = f"☠️ **{m.name}** {random.choice(deaths)}"
        
        desc = await self.generate_action_text("fatality / finish him", ctx.author.name, m.name, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.dark_red())
        embed.set_image(url=get_gif("kill"))
        await ctx.send(embed=embed)

    @commands.command(name="revive", help="Bring them back.")
    async def revive(self, ctx, m: discord.Member): 
        embed = discord.Embed(description=f"👼 **{m.name}** was resurrected by the Habibi Gods!", color=discord.Color.gold())
        embed.set_image(url=get_gif("revive"))
        await ctx.send(embed=embed)

    @commands.command(name="spank", help="Discipline them.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def spank(self, ctx, m: discord.Member): 
        default = f"🤚 **{ctx.author.name} furiously spanked {m.name}!**"
        desc = await self.generate_action_text("dramatic spank", ctx.author.name, m.name, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.dark_orange())
        embed.set_image(url=get_gif("spank"))
        await ctx.send(embed=embed)

    @commands.command(name="slap", help="Slap some sense into them.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slap(self, ctx, m: discord.Member): 
        default = f"👋 **{ctx.author.name} slapped {m.name} across the face!**"
        desc = await self.generate_action_text("anime slap across the face", ctx.author.name, m.name, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.red())
        embed.set_image(url=get_gif("slap"))
        await ctx.send(embed=embed)

    @commands.command(name="bonk", help="Send them to horny jail.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def bonk(self, ctx, m: discord.Member): 
        default = f"🏏 **{ctx.author.name} BONKED {m.name}! Go to jail!**"
        desc = await self.generate_action_text("bonk with a baseball bat", ctx.author.name, m.name, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.orange())
        embed.set_image(url=get_gif("bonk"))
        await ctx.send(embed=embed)

    @commands.command(name="hug", help="Give someone a warm hug.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def hug(self, ctx, m: discord.Member): 
        default = f"🫂 **{ctx.author.name} gave {m.name} a tight hug!**"
        desc = await self.generate_action_text("warm, emotional anime hug", ctx.author.name, m.name, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.pink())
        embed.set_image(url=get_gif("hug"))
        await ctx.send(embed=embed)


    # ========================================================================
    # RANDOMIZERS
    # ========================================================================
    @commands.command(name="eightball", aliases=["8ball"], help="Ask the magic 8-ball a question.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def eightball(self, ctx, *, q: str): 
        responses = ["Yes, obviously.", "No way, bro.", "Maybe, but don't count on it.", "100% facts.", "Are you kidding? No.", "Signs point to yes.", "My sources say nah."]
        answer = random.choice(responses)
        
        if ai_client:
            try:
                prompt = f"Answer this yes/no question as a sarcastic, all-knowing magic 8-ball: '{q}'. 1 short sentence."
                answer = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
            except: pass
            
        embed = discord.Embed(title="🎱 Magic 8-Ball", description=f"**Q:** {q}\n**A:** {answer}", color=discord.Color.dark_grey())
        embed.set_image(url=get_gif("eightball"))
        await ctx.send(embed=embed)

    @commands.command(name="choose", help="Make the bot choose between multiple things (comma separated).")
    async def choose(self, ctx, *, options: str): 
        opts = [o.strip() for o in options.split(",") if o.strip()]
        if len(opts) < 2: return await ctx.send("❌ Give me at least 2 things to choose from, separated by commas. (e.g. `!choose Apple, Banana`)")
        
        choice = random.choice(opts)
        reason = ""
        
        if ai_client:
            try:
                prompt = f"I forced you to choose between these options: {', '.join(opts)}. You chose '{choice}'. Give a funny, 1-sentence sarcastic reason why."
                res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=5.0)
                reason = f"\n\n🤖 *{res}*"
            except: pass

        embed = discord.Embed(description=f"🤔 I choose: **{choice}**{reason}", color=discord.Color.teal())
        embed.set_image(url=get_gif("choose"))
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Trolls(bot))
