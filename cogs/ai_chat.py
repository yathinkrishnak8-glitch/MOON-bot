
import discord
from discord.ext import commands
import random
import re
from core import db, save_db, get_gif, ask_groq, xp_cooldown

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ========================================================================
    # EVENT LISTENER: on_message
    # ========================================================================
    @commands.Cog.listener()
    async def on_message(self, message):
        # 1. Ignore all bots (including itself) to prevent infinite loops
        if message.author.bot: 
            return
            
        uid = str(message.author.id)

        # ---------------------------------------------------
        # 2. LIGHTNING FAST AUTOMOD (Regex)
        # ---------------------------------------------------
        filter_words = db.get("config", {}).get("filterwords", [])
        if filter_words:
            pattern = re.compile(r'\b(' + '|'.join(map(re.escape, filter_words)) + r')\b', re.IGNORECASE)
            if pattern.search(message.content):
                try: 
                    await message.delete()
                    await message.channel.send(embed=discord.Embed(description=f"⚠️ {message.author.mention}, watch your language! That word is blacklisted.", color=discord.Color.red()), delete_after=5)
                except: pass
                return

        # ---------------------------------------------------
        # 3. AFK SYSTEM
        # ---------------------------------------------------
        if uid in db.setdefault("afk", {}):
            del db["afk"][uid]
            save_db(db)
            await message.channel.send(embed=discord.Embed(description=f"👋 Welcome back {message.author.mention}, your AFK status was removed.", color=discord.Color.green()), delete_after=10)
        
        for m in message.mentions:
            if str(m.id) in db.get("afk", {}): 
                await message.channel.send(embed=discord.Embed(description=f"💤 **{m.name}** is currently AFK: {db['afk'][str(m.id)]}", color=discord.Color.dark_grey()))

        # ---------------------------------------------------
        # 4. HARDCORE LEVELING
        # ---------------------------------------------------
        if uid not in db.setdefault("levels", {}): db["levels"][uid] = {"xp": 0, "level": 1}
        
        if uid not in xp_cooldown and not message.content.startswith(('!', '/')):
            xp_cooldown.add(uid)
            self.bot.loop.call_later(60, lambda: xp_cooldown.discard(uid) if uid in xp_cooldown else None)
            
            db["levels"][uid]["xp"] += random.randint(15, 30)
            current_lvl = db["levels"][uid]["level"]
            req_xp = int(150 * (current_lvl ** 1.5))
            
            if db["levels"][uid]["xp"] >= req_xp and current_lvl < 13000:
                db["levels"][uid]["level"] += 1
                save_db(db)
                
                lvl_up = discord.Embed(title="LEVEL UP!", description=f"🎉 **{message.author.mention}** conquered the grind and reached **Level {db['levels'][uid]['level']}**!", color=discord.Color.gold())
                lvl_up.set_image(url=get_gif("level_up"))
                await message.channel.send(embed=lvl_up)
            else: 
                save_db(db)

        # ---------------------------------------------------
        # 5. PURE TEXT AI CHAT (MULTI-USER AWARENESS)
        # ---------------------------------------------------
        if message.content.startswith(('!', '/')):
            if message.content.startswith('!') and len(message.content) > 1:
                cmd = message.content[1:].split()[0].lower()
                if cmd in db.get("custom_commands", {}): 
                    await message.channel.send(embed=discord.Embed(description=db["custom_commands"][cmd], color=discord.Color.blue()))
            return 

        is_dm = not message.guild
        is_ai_chan = message.guild and message.channel.id == db.get("config", {}).get("ai_channel")
        is_bot_mentioned = self.bot.user in message.mentions
        
        if is_dm or is_ai_chan or is_bot_mentioned:
            async with message.channel.typing():
                try: 
                    hist = []
                    # Fetching last 8 messages
                    recent = [m async for m in message.channel.history(limit=8)]
                    recent.reverse()
                    
                    for m in recent:
                        clean_content = m.content.replace(f'<@{self.bot.user.id}>', 'Habibi').strip()
                        if clean_content: 
                            if m.author == self.bot.user:
                                # It's the bot speaking
                                hist.append({"role": "assistant", "content": clean_content})
                            else:
                                # 🔥 THE MULTI-USER FIX: Inject the Display Name!
                                # Example: "Alex: What's up guys?"
                                hist.append({"role": "user", "content": f"{m.author.display_name}: {clean_content}"})
                    
                    reply = await ask_groq(hist)
                    
                    if is_bot_mentioned and not is_ai_chan:
                        await message.reply(reply[:2000], mention_author=False)
                    else:
                        await message.channel.send(reply[:2000])
                except Exception as e: 
                    print(f"⚠️ AI Chat Error: {e}")


    # ========================================================================
    # AI ANALYSIS COMMANDS
    # ========================================================================
    @commands.hybrid_command(name="vibecheck", description="AI thoroughly analyzes a user's vibe based on chat history.")
    async def vibecheck(self, ctx, member: discord.Member):
        await ctx.defer()
        log = "\n".join([m.content async for m in ctx.channel.history(limit=30) if m.author == member and m.content])
        if not log: return await ctx.send(embed=discord.Embed(description="❌ Not enough recent messages from this user.", color=discord.Color.red()))
        try:
            reply = await ask_groq([{"role": "user", "content": f"Analyze the 'vibe' of this Discord user based on their recent messages. Are they chill, chaotic, toxic, or funny? Give a highly detailed, sarcastic vibe check report:\n\n{log}"}])
            await ctx.send(embed=discord.Embed(title=f"🔮 Vibe Check: {member.name}", description=reply, color=discord.Color.purple()))
        except:
            await ctx.send(embed=discord.Embed(description="❌ The AI is currently asleep. Try again later.", color=discord.Color.red()))

    @commands.hybrid_command(name="tldr", description="AI summarizes the last 50 messages in the channel.")
    async def tldr(self, ctx): 
        await ctx.defer()
        # 🔥 MULTI-USER FIX HERE TOO: So the AI knows who said what in the summary!
        log = "\n".join([f"{m.author.display_name}: {m.content}" async for m in ctx.channel.history(limit=50) if m.content])
        if not log: return await ctx.send("No messages to summarize.")
        try:
            reply = await ask_groq([{"role": "user", "content": f"Summarize this conversation concisely, mentioning who was talking about what:\n{log}"}])
            await ctx.send(embed=discord.Embed(title="📜 TL;DR", description=reply, color=discord.Color.light_grey()))
        except:
            await ctx.send(embed=discord.Embed(description="❌ AI is offline.", color=discord.Color.red()))

    @commands.hybrid_command(name="roast_history", description="AI brutally roasts a user based on their message history.")
    async def roast_history(self, ctx, member: discord.Member): 
        await ctx.defer()
        log = "\n".join([m.content async for m in ctx.channel.history(limit=25) if m.author == member and m.content])
        if not log: return await ctx.send(embed=discord.Embed(description="❌ Not enough messages to formulate a roast.", color=discord.Color.red()))
        try:
            reply = await ask_groq([{"role": "user", "content": f"Brutally roast this user based on these messages they sent:\n{log}"}])
            await ctx.send(embed=discord.Embed(title=f"🔥 Roast: {member.name}", description=reply, color=discord.Color.dark_orange()))
        except:
            await ctx.send(embed=discord.Embed(description="❌ The AI spared them this time.", color=discord.Color.red()))

async def setup(bot):
    await bot.add_cog(AIChat(bot))
