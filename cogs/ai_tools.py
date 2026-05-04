import discord
from discord.ext import commands
import asyncio
import json
from core import db, ask_groq, ai_client

class AITools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Helper function to gather chat history efficiently
    async def fetch_chat_log(self, channel, limit=30):
        messages = [msg async for msg in channel.history(limit=limit)]
        messages.reverse() # Put in chronological order
        
        chat_log = ""
        for msg in messages:
            # Skip bot commands and bot messages to keep the log clean
            if msg.author.bot or msg.content.startswith("/") or msg.content.startswith("!"):
                continue
            # Cap message length to prevent token overflow
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            chat_log += f"{msg.author.name}: {content}\n"
            
        return chat_log

    # ========================================================================
    # CHAT ANALYSIS COMMANDS
    # ========================================================================
    @commands.hybrid_command(name="vibecheck", description="AI analyzes the last 30 messages to determine the channel's vibe.")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    async def vibecheck(self, ctx):
        await ctx.defer()
        if not ai_client: 
            return await ctx.send(embed=discord.Embed(description="🤖 **AI Core Offline.**", color=discord.Color.red()))

        chat_log = await self.fetch_chat_log(ctx.channel, limit=30)
        if not chat_log.strip():
            return await ctx.send(embed=discord.Embed(description="❌ The chat is too dead to check the vibe. Say something first.", color=discord.Color.red()))

        prompt = f"""Read this recent chat log from a Discord server:\n\n{chat_log}\n\n
        Analyze the "vibe" of this conversation. Are they being chaotic, nerdy, sad, toxic, or funny? 
        Give a brutally honest, sarcastic, 2-sentence summary of the channel's current energy. Do not use markdown formatting."""

        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            
            embed = discord.Embed(title="🌡️ Channel Vibe Check", description=res, color=discord.Color.purple())
            embed.set_footer(text="Analyzed from the last 30 messages.")
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send("❌ The AI's brain short-circuited trying to read your messages.")

    @commands.hybrid_command(name="tldr", description="AI summarizes the last 50 messages so you can catch up.")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def tldr(self, ctx):
        await ctx.defer()
        if not ai_client: return await ctx.send("🤖 **AI Core Offline.**")

        msg = await ctx.send(embed=discord.Embed(description="📚 **Reading chat history...**", color=discord.Color.dark_grey()))
        chat_log = await self.fetch_chat_log(ctx.channel, limit=50)
        
        if not chat_log.strip():
            return await msg.edit(embed=discord.Embed(description="❌ There is no conversation to summarize.", color=discord.Color.red()))

        prompt = f"""Read this recent chat log from a Discord server:\n\n{chat_log}\n\n
        Summarize exactly what these people are talking about. 
        Output ONLY 3 bullet points. Make it concise and slightly humorous."""

        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            embed = discord.Embed(title="📝 Chat TL;DR", description=res, color=discord.Color.blue())
            await msg.edit(embed=embed)
        except Exception as e:
            await msg.edit(embed=discord.Embed(description="❌ Failed to summarize.", color=discord.Color.red()))

    @commands.hybrid_command(name="roast_history", description="AI dynamically roasts a user based on their last 20 messages.")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def roast_history(self, ctx, member: discord.Member):
        await ctx.defer()
        if not ai_client: return await ctx.send("🤖 **AI Core Offline.**")

        if member.bot:
            return await ctx.send(embed=discord.Embed(description="❌ You cannot roast the machines.", color=discord.Color.red()))

        # Search for messages specifically from the target
        messages = [msg async for msg in ctx.channel.history(limit=150)]
        target_log = ""
        msg_count = 0
        
        for msg in messages:
            if msg.author == member and not msg.content.startswith("/") and not msg.content.startswith("!"):
                target_log += f'"{msg.content}"\n'
                msg_count += 1
            if msg_count >= 15: # Stop when we have 15 good messages
                break

        if not target_log.strip():
            return await ctx.send(embed=discord.Embed(description=f"❌ **{member.name}** hasn't said enough in this channel to roast.", color=discord.Color.red()))

        prompt = f"""You are a ruthless, sarcastic roaster. Look at these quotes recently said by {member.name}:\n\n{target_log}\n\n
        Write a brutal, funny 2-sentence roast specifically mocking the things they just said. Target their spelling, their topics, or their attitude."""

        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            embed = discord.Embed(title=f"🔥 Roast: {member.name}", description=f"{member.mention}, {res}", color=discord.Color.orange())
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send("❌ Failed to roast.")

    # ========================================================================
    # CREATIVE AI UTILITIES (Upgraded Database Connections)
    # ========================================================================
    @commands.hybrid_command(name="lore", description="AI generates an epic RPG backstory based on your real server stats.")
    async def lore(self, ctx, member: discord.Member = None):
        await ctx.defer()
        if not ai_client: return await ctx.send("🤖 **AI Core Offline.**")
        
        target = member or ctx.author
        uid = str(target.id)
        
        # Pull real server stats to feed the AI
        bal = db.get("economy", {}).get(uid, 0)
        level_data = db.get("levels", {}).get(uid, {"level": 1})
        top_role = target.top_role.name if target.top_role.name != "@everyone" else "Wanderer"

        prompt = f"""You are the Grand Historian. Write an epic, Dark Fantasy/Anime lore backstory for the character '{target.name}'.
        You MUST incorporate these true facts about them into the story organically:
        - Current Wealth: {bal} coins
        - Power Level: {level_data['level']}
        - Faction/Title: {top_role}
        
        Make them sound legendary, dangerous, or mysterious. Write exactly 2 epic paragraphs. Do not mention that these are Discord stats."""

        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            embed = discord.Embed(title=f"📖 The Legend of {target.name}", description=res, color=discord.Color.dark_theme())
            embed.set_thumbnail(url=str(target.display_avatar.url))
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"Lore Error: {e}")
            await ctx.send("❌ The scribes lost your lore pages.")

    @commands.hybrid_command(name="debate", description="Challenge the AI to a debate. It will violently take the opposite side.")
    async def debate(self, ctx, *, topic: str):
        await ctx.defer()
        if not ai_client: return await ctx.send("🤖 **AI Core Offline.**")

        prompt = f"""A user just claimed: "{topic}". 
        You must violently, sarcastically, and intelligently argue the EXACT OPPOSITE of what they said. 
        Tear their argument apart using logic (or fake, funny internet logic). 
        Keep it to one paragraph. Do not be overly polite."""

        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            embed = discord.Embed(title="🥊 Debate Mode", color=discord.Color.red())
            embed.add_field(name=f"{ctx.author.name} says:", value=f"*{topic}*", inline=False)
            embed.add_field(name="AI responds:", value=res, inline=False)
            await ctx.send(embed=embed)
        except:
            await ctx.send("❌ The AI refuses to stoop to your level of debate.")

    @commands.hybrid_command(name="urban", description="AI generates a perfectly formatted Urban Dictionary definition.")
    async def urban(self, ctx, *, word: str):
        await ctx.defer()
        if not ai_client: return await ctx.send("🤖 **AI Core Offline.**")

        prompt = f"""You are a top contributor to Urban Dictionary. Write a funny, internet-slang definition for "{word}".
        Output ONLY a raw JSON object matching this schema:
        {{"definition": "The funny meaning of the word", "example": "A funny dialogue quote using the word in a sentence", "author": "Fake edgy internet username"}}
        Keep it PG-13 but edgy. No markdown formatting outside the JSON."""

        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            
            # Bulletproof JSON Parsing
            start, end = res.find('{'), res.rfind('}')
            if start == -1 or end == -1: raise Exception("JSON extraction failed.")
            data = json.loads(res[start:end+1])
            
            embed = discord.Embed(title=f"📚 {word}", color=discord.Color.dark_teal())
            embed.add_field(name="Definition", value=data.get("definition", "Error loading definition."), inline=False)
            embed.add_field(name="Example", value=f"*{data.get('example', 'Error loading example.')}*", inline=False)
            embed.set_footer(text=f"by {data.get('author', 'Anonymous')} • 👍 {random.randint(100, 9000)}  👎 {random.randint(0, 50)}")
            
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"Urban Error: {e}")
            await ctx.send("❌ The dictionary burned down. Try a different word.")

    # ========================================================================
    # TRANSLATOR COMMANDS
    # ========================================================================
    @commands.hybrid_group(name="translate", description="Translate normal text into insane internet personas.")
    async def translate(self, ctx):
        if ctx.invoked_subcommand is None: 
            await ctx.send("Use `/translate gothic`, `/translate brainrot`, or `/translate pirate`.")

    async def run_translation(self, ctx, persona: str, text: str, color: discord.Color):
        await ctx.defer()
        if not ai_client: return await ctx.send("🤖 **AI Core Offline.**")

        prompt = f"""Translate the following text into the style of a {persona}. 
        Keep the core meaning, but completely change the vocabulary and tone to fit the persona.
        Text to translate: "{text}"
        Output ONLY the translated text."""

        try:
            res = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
            embed = discord.Embed(title=f"🗣️ Translated ({persona})", description=res, color=color)
            await ctx.send(embed=embed)
        except:
            await ctx.send("❌ Translation failed.")

    @translate.command(name="gothic", description="Translate text into Dark Fantasy / Edgy Gothic speech.")
    async def gothic(self, ctx, *, text: str):
        await self.run_translation(ctx, "brooding, poetic, dark fantasy vampire character", text, discord.Color.dark_purple())

    @translate.command(name="brainrot", description="Translate text into pure Gen-Z / Brainrot slang.")
    async def brainrot(self, ctx, *, text: str):
        await self.run_translation(ctx, "chronically online Gen-Z TikTok user who says skibidi, rizz, sigma, etc.", text, discord.Color.green())

    @translate.command(name="pirate", description="Translate text into aggressive Pirate speech.")
    async def pirate(self, ctx, *, text: str):
        await self.run_translation(ctx, "drunken, aggressive pirate from the 1700s", text, discord.Color.gold())

async def setup(bot):
    await bot.add_cog(AITools(bot))
