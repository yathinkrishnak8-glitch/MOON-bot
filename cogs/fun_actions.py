
import discord
from discord.ext import commands
import random
from core import get_gif, ask_groq, ai_client

# ========================================================================
# COG CLASS: Fun & Anime Actions
# Description: Prefix-based roleplay commands (!pat, !punch, etc.)
# ========================================================================
class FunActions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def check_targets(self, ctx, m: discord.Member, action: str):
        """Helper to handle self-targeting and bot-targeting."""
        if m == self.bot.user:
            return False, "🤖 ***Dodges effortlessly...* Nice try, human.**"
        if m == ctx.author:
            return False, f"Bro... you can't {action} yourself. Are you okay?"
        return True, ""


    # ========================================================================
    # INTERACTIVE ANIME ACTIONS (With Dodge Mechanics!)
    # ========================================================================
    @commands.command(name="pat", help="Give someone a wholesome headpat.")
    async def pat(self, ctx, m: discord.Member): 
        valid, msg = self.check_targets(ctx, m, "pat")
        if not valid: return await ctx.send(msg)

        embed = discord.Embed(description=f"🤚 **{ctx.author.name}** gave {m.mention} a headpat!", color=discord.Color.pink())
        embed.set_image(url=get_gif("pat"))
        await ctx.send(embed=embed)

    @commands.command(name="punch", help="Punch someone into the next dimension.")
    async def punch(self, ctx, m: discord.Member): 
        valid, msg = self.check_targets(ctx, m, "punch")
        if not valid: return await ctx.send(msg)

        # 🔥 5% RNG Dodge Mechanic
        if random.randint(1, 100) <= 5:
            return await ctx.send(embed=discord.Embed(description=f"💥 **ULTRA INSTINCT!** {m.mention} effortlessly dodged **{ctx.author.name}**'s punch!", color=discord.Color.gold()))

        embed = discord.Embed(description=f"👊 **{ctx.author.name}** punched {m.mention} right in the face!", color=discord.Color.red())
        embed.set_image(url=get_gif("punch"))
        await ctx.send(embed=embed)

    @commands.command(name="bite", help="Bite someone.")
    async def bite(self, ctx, m: discord.Member): 
        valid, msg = self.check_targets(ctx, m, "bite")
        if not valid: return await ctx.send(msg)

        if random.randint(1, 100) <= 5:
            return await ctx.send(embed=discord.Embed(description=f"🛡️ **BLOCKED!** {m.mention} stuffed a garlic clove in **{ctx.author.name}**'s mouth!", color=discord.Color.gold()))

        embed = discord.Embed(description=f"🧛 **{ctx.author.name}** bit {m.mention}!", color=discord.Color.dark_red())
        embed.set_image(url=get_gif("bite"))
        await ctx.send(embed=embed)

    @commands.command(name="kiss", help="Kiss someone.")
    async def kiss(self, ctx, m: discord.Member): 
        valid, msg = self.check_targets(ctx, m, "kiss")
        if not valid: return await ctx.send(msg)

        embed = discord.Embed(description=f"💋 **{ctx.author.name}** kissed {m.mention}!", color=discord.Color.magenta())
        embed.set_image(url=get_gif("kiss"))
        await ctx.send(embed=embed)


    # ========================================================================
    # SOLO ANIME REACTIONS
    # ========================================================================
    @commands.command(name="smug", help="Look down on the peasants.")
    async def smug(self, ctx): 
        embed = discord.Embed(description=f"😏 **{ctx.author.name}** is looking mighty smug.", color=discord.Color.purple())
        embed.set_image(url=get_gif("smug"))
        await ctx.send(embed=embed)

    @commands.command(name="cry", help="Shed dramatic anime tears.")
    async def cry(self, ctx): 
        embed = discord.Embed(description=f"😭 **{ctx.author.name}** bursts into tears.", color=discord.Color.blue())
        embed.set_image(url=get_gif("cry"))
        await ctx.send(embed=embed)


    # ========================================================================
    # ULTIMATE ANIME ABILITIES (With Targeting)
    # ========================================================================
    @commands.command(name="domain_expansion", aliases=["domain"], help="Trap them in your innate domain.")
    async def domain_expansion(self, ctx, m: discord.Member = None): 
        if m:
            if m == self.bot.user: return await ctx.send("🤖 **My Simple Domain neutralized your attack.**")
            desc = f"🤞 **{ctx.author.name}** trapped {m.mention} inside their Domain Expansion!"
        else:
            desc = f"🤞 **{ctx.author.name}** cast Domain Expansion!"
            
        embed = discord.Embed(description=desc, color=discord.Color.dark_blue())
        embed.set_image(url=get_gif("domain"))
        await ctx.send(embed=embed)

    @commands.command(name="bankai", help="Release your ultimate spiritual pressure.")
    async def bankai(self, ctx, m: discord.Member = None): 
        desc = f"⚔️ **{ctx.author.name}** released their BANKAI against {m.mention}!" if m else f"⚔️ **{ctx.author.name}** released their BANKAI!"
        embed = discord.Embed(description=desc, color=discord.Color.dark_red())
        embed.set_image(url=get_gif("bankai"))
        await ctx.send(embed=embed)


    # ========================================================================
    # TEXT-BASED FUN COMMANDS
    # ========================================================================
    @commands.command(name="quote", help="Drop an epic, AI-generated anime quote.")
    async def quote(self, ctx): 
        if not ai_client:
            # Fallback if Groq is offline
            quotes = ["If you don't fight, you can't win.", "People die if they are killed.", "Tatatakae."]
            return await ctx.send(embed=discord.Embed(description=f"📜 *\"{random.choice(quotes)}\"*", color=discord.Color.dark_theme()))
            
        async with ctx.channel.typing():
            try:
                prompt = "Generate a completely original, extremely edgy, epic, and dramatic anime quote. Include a fake anime character name who said it at the end. Output ONLY the quote."
                reply = await ask_groq([{"role": "user", "content": prompt}], inject_personality=False)
                await ctx.send(embed=discord.Embed(description=f"📜 {reply}", color=discord.Color.dark_theme()))
            except:
                await ctx.send("❌ The scribe lost his pen. Try again later.")

    @commands.command(name="powerlevel", help="Scouter check!")
    async def powerlevel(self, ctx, m: discord.Member = None): 
        target = m or ctx.author
        
        if target == self.bot.user:
            return await ctx.send(embed=discord.Embed(description="💥 **ERROR!** The scouter exploded trying to read my power level!", color=discord.Color.red()))
            
        p = random.randint(10, 15000000)
        
        if p > 9000000:
            msg = f"💥 **IT'S OVER 9 MILLION!** {target.name}'s power level is **{p:,}**!"
            color = discord.Color.gold()
        elif p < 1000:
            msg = f"🥱 The scouter says {target.name}'s power level is only **{p:,}**... Pathetic."
            color = discord.Color.dark_grey()
        else:
            msg = f"🔍 The scouter says {target.name}'s power level is **{p:,}**."
            color = discord.Color.green()
            
        await ctx.send(embed=discord.Embed(description=msg, color=color))


async def setup(bot):
    await bot.add_cog(FunActions(bot))
