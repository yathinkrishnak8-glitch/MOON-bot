import discord
from discord.ext import commands
import asyncio
from core import db, ask_groq, ai_client

class AITools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ========================================================================
    # CREATIVE AI UTILITIES
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
        top_role = target.top_role.name if getattr(target, "top_role", None) and target.top_role.name != "@everyone" else "Wanderer"

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

# ========================================================================
# STANDARD SETUP FUNCTION
# ========================================================================
async def setup(bot):
    await bot.add_cog(AITools(bot))
