import discord
from discord.ext import commands
import random
import asyncio
from core import get_gif, ask_groq, ai_client

class FunActions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def generate_action_text(self, action_name, user, target, default_text):
        """Helper to let the AI narrate the actions dynamically."""
        if not ai_client: return default_text
        try:
            if target:
                prompt = f"Describe a character named '{user}' doing a dramatic anime '{action_name}' to '{target}' in 1 epic or funny sentence. No markdown headers."
            else:
                prompt = f"Describe a character named '{user}' doing a dramatic anime '{action_name}' in 1 epic or funny sentence. No markdown headers."
            
            # 🔥 TIMEOUT SHIELD: Falls back to default text if AI is too slow
            res = await asyncio.wait_for(ask_groq([{"role": "user", "content": prompt}], inject_personality=False), timeout=4.0)
            return f"**{res}**"
        except:
            return default_text

    # ========================================================================
    # ANIME ACTIONS (Connected to AI & GIF Gallery)
    # ========================================================================
    @commands.command(name="bankai", help="Release your ultimate power.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def bankai(self, ctx, m: discord.Member = None):
        await ctx.message.add_reaction("⚔️")
        target_text = f" against {m.name}" if m else ""
        default = f"⚔️ **{ctx.author.name} released their BANKAI{target_text}!**"
        
        desc = await self.generate_action_text("Bankai release (Bleach style)", ctx.author.name, m.name if m else None, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.dark_red())
        gif = get_gif("bankai")
        if gif: embed.set_image(url=gif)
        await ctx.send(embed=embed)

    @commands.command(name="domain", aliases=["domain_expansion"], help="Expand your domain.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def domain(self, ctx, m: discord.Member = None):
        await ctx.message.add_reaction("🤞")
        target_text = f" to trap {m.name}" if m else ""
        default = f"🤞 **{ctx.author.name} expanded their Domain{target_text}!**"
        
        desc = await self.generate_action_text("Domain Expansion (Jujutsu Kaisen style)", ctx.author.name, m.name if m else None, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.dark_theme())
        gif = get_gif("domain")
        if gif: embed.set_image(url=gif)
        await ctx.send(embed=embed)

    @commands.command(name="pat", help="Pat someone on the head.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pat(self, ctx, m: discord.Member):
        default = f"✋ **{ctx.author.name} gently patted {m.name} on the head.**"
        desc = await self.generate_action_text("wholesome anime headpat", ctx.author.name, m.name, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.green())
        gif = get_gif("pat")
        if gif: embed.set_image(url=gif)
        await ctx.send(embed=embed)

    @commands.command(name="punch", help="Punch someone.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def punch(self, ctx, m: discord.Member):
        default = f"👊 **{ctx.author.name} punched {m.name} into next week!**"
        desc = await self.generate_action_text("devastating anime punch", ctx.author.name, m.name, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.red())
        gif = get_gif("punch")
        if gif: embed.set_image(url=gif)
        await ctx.send(embed=embed)

    @commands.command(name="bite", help="Bite someone.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def bite(self, ctx, m: discord.Member):
        default = f"🧛 **{ctx.author.name} bit {m.name}!**"
        desc = await self.generate_action_text("anime bite attack", ctx.author.name, m.name, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.dark_red())
        gif = get_gif("bite")
        if gif: embed.set_image(url=gif)
        await ctx.send(embed=embed)

    @commands.command(name="kiss", help="Kiss someone.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def kiss(self, ctx, m: discord.Member):
        default = f"💋 **{ctx.author.name} gave {m.name} a kiss!**"
        desc = await self.generate_action_text("romantic anime kiss", ctx.author.name, m.name, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.pink())
        gif = get_gif("kiss")
        if gif: embed.set_image(url=gif)
        await ctx.send(embed=embed)

    @commands.command(name="smug", help="Look incredibly smug.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def smug(self, ctx):
        default = f"😏 **{ctx.author.name} is looking incredibly smug.**"
        desc = await self.generate_action_text("smug anime face expression", ctx.author.name, None, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.gold())
        gif = get_gif("smug")
        if gif: embed.set_image(url=gif)
        await ctx.send(embed=embed)

    @commands.command(name="cry", help="Cry a river.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def cry(self, ctx):
        default = f"😭 **{ctx.author.name} burst into tears!**"
        desc = await self.generate_action_text("dramatic anime crying", ctx.author.name, None, default)
        
        embed = discord.Embed(description=desc, color=discord.Color.blue())
        gif = get_gif("cry")
        if gif: embed.set_image(url=gif)
        await ctx.send(embed=embed)

    # ========================================================================
    # ADDITIONAL ANIME TOOLS
    # ========================================================================
    @commands.command(name="powerlevel", aliases=["scouter"], help="Scan someone's power level.")
    async def powerlevel(self, ctx, m: discord.Member = None):
        target = m or ctx.author
        power = random.randint(100, 150000)
        
        if power > 9000:
            desc = f"💥 **IT'S OVER 9000!**\n{target.name}'s power level is **{power:,}**!"
        else:
            desc = f"🔍 {target.name}'s power level is only **{power:,}**. Weak."
            
        embed = discord.Embed(description=desc, color=discord.Color.orange())
        await ctx.send(embed=embed)

    @commands.command(name="quote", help="Generate an inspiring or badass AI anime quote.")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def quote(self, ctx):
        if not ai_client: return await ctx.send("🤖 **AI is offline.**")
        async with ctx.channel.typing():
            try:
                res = await asyncio.wait_for(ask_groq([{"role": "user", "content": "Generate a completely original, badass, deep anime quote. Format it like: 'Quote' - Anime Name"}]), timeout=5.0)
                embed = discord.Embed(description=f"📜 {res}", color=discord.Color.dark_purple())
                await ctx.send(embed=embed)
            except:
                await ctx.send("❌ The anime protagonist is out of breath.")

async def setup(bot):
    await bot.add_cog(FunActions(bot))
