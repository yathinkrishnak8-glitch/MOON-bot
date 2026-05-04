
import discord
from discord.ext import commands, tasks
import asyncio
import time
from core import db, save_db, get_gif
from ui import ConfirmView

# Transient memory for snipes (Does not need to be in database.json)
snipes = {}
edit_snipes = {}

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tempban_loop.start()

    def cog_unload(self):
        self.tempban_loop.cancel()

    # ========================================================================
    # SECURITY HELPERS
    # ========================================================================
    def check_hierarchy(self, ctx, target: discord.Member):
        """Prevents lower ranks from punishing higher ranks, and protects the bot."""
        if target == ctx.author:
            return False, "❌ You cannot punish yourself."
        if target == self.bot.user:
            return False, "❌ I cannot punish myself. I am beyond your control."
        if ctx.guild.owner == target:
            return False, "❌ You cannot punish the Server Owner."
        if ctx.author != ctx.guild.owner and target.top_role >= ctx.author.top_role:
            return False, "❌ You cannot punish someone with an equal or higher role than you."
        if target.top_role >= ctx.guild.me.top_role:
            return False, "❌ My role is not high enough to punish this user. Move my bot role higher!"
        return True, ""


    # ========================================================================
    # EVENT LISTENERS (Snipe & Auto-Jail)
    # ========================================================================
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild: return
        snipes[message.channel.id] = {
            "content": message.content,
            "author": message.author.name,
            "avatar": str(message.author.display_avatar.url),
            "time": time.time()
        }

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild or before.content == after.content: return
        edit_snipes[before.channel.id] = {
            "before": before.content,
            "after": after.content,
            "author": before.author.name,
            "avatar": str(before.author.display_avatar.url)
        }

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Instantly re-jails users who try to evade by leaving and rejoining."""
        if str(member.id) in db.get("jailed", {}):
            jr = discord.utils.get(member.guild.roles, name="Jailed")
            if jr: 
                try: await member.add_roles(jr)
                except: pass


    # ========================================================================
    # BACKGROUND TASK: Persistent Tempbans
    # ========================================================================
    @tasks.loop(minutes=1)
    async def tempban_loop(self):
        current_time = time.time()
        tempbans = db.setdefault("tempbans", {})
        expired = []

        for uid, data in tempbans.items():
            if current_time >= data["unban_time"]:
                try:
                    guild = self.bot.get_guild(data["guild_id"])
                    if guild:
                        user = discord.Object(id=int(uid))
                        await guild.unban(user, reason="Tempban expired.")
                except: pass
                expired.append(uid)

        for uid in expired:
            del db["tempbans"][uid]
            
        if expired: save_db(db)

    @tempban_loop.before_loop
    async def before_tempban(self):
        await self.bot.wait_until_ready()


    # ========================================================================
    # CORE PUNISHMENTS
    # ========================================================================
    @commands.hybrid_command(name="kick", description="Kick a user from the server.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, m: discord.Member, *, reason: str = "No reason provided."): 
        await ctx.defer()
        valid, msg = self.check_hierarchy(ctx, m)
        if not valid: return await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))

        try: await m.send(f"👢 You were kicked from **{ctx.guild.name}**.\nReason: {reason}")
        except: pass
        
        await m.kick(reason=f"Kicked by {ctx.author.name}: {reason}")
        await ctx.send(embed=discord.Embed(description=f"👢 **{m.mention} was kicked.**\n**Reason:** {reason}", color=discord.Color.red()))

    @commands.hybrid_command(name="ban", description="Permanently ban a user.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, m: discord.Member, *, reason: str = "No reason provided."): 
        await ctx.defer()
        valid, msg = self.check_hierarchy(ctx, m)
        if not valid: return await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))

        try: await m.send(f"🔨 You were permanently banned from **{ctx.guild.name}**.\nReason: {reason}")
        except: pass

        await m.ban(reason=f"Banned by {ctx.author.name}: {reason}")
        await ctx.send(embed=discord.Embed(description=f"🔨 **{m.mention} was permanently banned.**\n**Reason:** {reason}", color=discord.Color.dark_red()))

    @commands.hybrid_command(name="tempban", description="Temporarily ban a user.")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, m: discord.Member, days: int, *, reason: str = "No reason provided."): 
        await ctx.defer()
        if days <= 0 or days > 365: return await ctx.send("❌ Days must be between 1 and 365.")
            
        valid, msg = self.check_hierarchy(ctx, m)
        if not valid: return await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))

        unban_time = time.time() + (days * 86400)
        db.setdefault("tempbans", {})[str(m.id)] = {"unban_time": unban_time, "guild_id": ctx.guild.id}
        save_db(db)

        try: await m.send(f"⏳ You were temporarily banned from **{ctx.guild.name}** for {days} days.\nReason: {reason}")
        except: pass

        await m.ban(reason=f"Tempbanned by {ctx.author.name} for {days} days: {reason}")
        await ctx.send(embed=discord.Embed(title="⏳ Temp Banned", description=f"**{m.name}** was banned for **{days} days**.\n**Reason:** {reason}", color=discord.Color.orange()))

    @commands.hybrid_command(name="timeout", aliases=["tempmute"], description="Timeout a user for X minutes.")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, m: discord.Member, mins: int, *, reason: str = "No reason provided."): 
        await ctx.defer()
        if mins <= 0 or mins > 40320: return await ctx.send("❌ Timeout must be between 1 minute and 28 days.")
            
        valid, msg = self.check_hierarchy(ctx, m)
        if not valid: return await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))

        import datetime
        await m.timeout(datetime.timedelta(minutes=mins), reason=f"Timed out by {ctx.author.name}: {reason}")
        await ctx.send(embed=discord.Embed(title="🔇 Timed Out", description=f"**{m.mention}** has been timed out for **{mins} minutes**.\n**Reason:** {reason}", color=discord.Color.orange()))


    # ========================================================================
    # JAIL SYSTEM (Highest Security)
    # ========================================================================
    @commands.hybrid_command(name="jail", description="Strip a user's roles and send them to jail.")
    @commands.has_permissions(manage_roles=True)
    async def jail(self, ctx, m: discord.Member):
        await ctx.defer()
        valid, msg = self.check_hierarchy(ctx, m)
        if not valid: return await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))

        jr = discord.utils.get(ctx.guild.roles, name="Jailed")
        if not jr: return await ctx.send(embed=discord.Embed(description="⚠️ Error: The 'Jailed' role does not exist. Run `/deployserver` or create it manually.", color=discord.Color.red()))

        if str(m.id) in db.setdefault("jailed", {}):
            return await ctx.send(f"❌ {m.name} is already in jail.")

        # Save all their roles (except @everyone)
        db["jailed"][str(m.id)] = [r.id for r in m.roles if r.id != ctx.guild.default_role.id]
        save_db(db)
        
        # Strip roles and add Jail role
        for r in m.roles[1:]:
            try: await m.remove_roles(r)
            except: pass
            
        await m.add_roles(jr)
        await ctx.send(embed=discord.Embed(description=f"⛓️ **{m.mention} has been stripped of their roles and thrown in jail.**", color=discord.Color.dark_grey()))

    @commands.hybrid_command(name="unjail", description="Release a user from jail and restore their roles.")
    @commands.has_permissions(manage_roles=True)
    async def unjail(self, ctx, m: discord.Member):
        await ctx.defer()
        if str(m.id) not in db.get("jailed", {}):
            return await ctx.send(f"❌ {m.name} is not in jail.")

        jr = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jr and jr in m.roles: 
            await m.remove_roles(jr)
        
        # Restore old roles
        saved_roles = db["jailed"].pop(str(m.id), [])
        for r_id in saved_roles:
            role = ctx.guild.get_role(r_id)
            if role: 
                try: await m.add_roles(role)
                except: pass
                
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🔓 **{m.mention} made bail and was released. Roles restored.**", color=discord.Color.green()))


    # ========================================================================
    # WARNINGS & CHAT CONTROL
    # ========================================================================
    @commands.hybrid_command(name="warn", description="Officially warn a user.")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, m: discord.Member, *, reason: str = "Violation"): 
        await ctx.defer()
        valid, msg = self.check_hierarchy(ctx, m)
        if not valid: return await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.red()))

        db.setdefault("warns", {}).setdefault(str(m.id), []).append(reason)
        save_db(db)
        await ctx.send(embed=discord.Embed(description=f"⚠️ **{m.mention} has been warned.**\n**Reason:** {reason}", color=discord.Color.yellow()))

    @commands.hybrid_command(name="warnings", aliases=["warns"], description="Check a user's warnings.")
    async def warnings(self, ctx, m: discord.Member): 
        await ctx.defer()
        w = db.get("warns", {}).get(str(m.id), [])
        if not w: return await ctx.send(embed=discord.Embed(description=f"✅ **{m.name} has a clean record.**", color=discord.Color.green()))
        
        embed = discord.Embed(title=f"⚠️ Warnings for {m.name} (Total: {len(w)})", color=discord.Color.orange())
        for i, text in enumerate(w): embed.add_field(name=f"Warning {i+1}", value=text, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarns", description="Clear all warnings for a user.")
    @commands.has_permissions(manage_messages=True)
    async def clearwarns(self, ctx, m: discord.Member): 
        await ctx.defer()
        if str(m.id) in db.setdefault("warns", {}):
            del db["warns"][str(m.id)]
            save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🗑️ **Cleared all warnings for {m.name}.**", color=discord.Color.green()))

    @commands.hybrid_command(name="slowmode", description="Set channel slowmode.")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int): 
        await ctx.defer()
        if seconds < 0 or seconds > 21600: return await ctx.send("❌ Slowmode must be between 0 and 21600 seconds.")
        await ctx.channel.edit(slowmode_delay=seconds)
        msg = f"⏱️ **Slowmode set to {seconds}s.**" if seconds > 0 else "⏱️ **Slowmode disabled.**"
        await ctx.send(embed=discord.Embed(description=msg, color=discord.Color.blue()))

    @commands.hybrid_command(name="lockdown", description="Lock the entire server.")
    @commands.has_permissions(administrator=True)
    async def lockdown(self, ctx):
        await ctx.defer()
        await ctx.send(embed=discord.Embed(description="🚨 **LOCKDOWN INITIATED... Securing channels.**", color=discord.Color.red()))
        for c in ctx.guild.text_channels:
            try: await c.set_permissions(ctx.guild.default_role, send_messages=False)
            except: pass

    @commands.hybrid_command(name="unlockdown", description="Lift server lockdown.")
    @commands.has_permissions(administrator=True)
    async def unlockdown(self, ctx):
        await ctx.defer()
        await ctx.send(embed=discord.Embed(description="🔓 **LOCKDOWN LIFTED... Channels restored.**", color=discord.Color.green()))
        for c in ctx.guild.text_channels:
            try: await c.set_permissions(ctx.guild.default_role, send_messages=True)
            except: pass

    @commands.hybrid_command(name="purge", aliases=["clear"], description="Delete bulk messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int): 
        await ctx.defer()
        if amount < 1 or amount > 1000: return await ctx.send("❌ Can only purge between 1 and 1000 messages.")
        
        view = ConfirmView(ctx)
        msg = await ctx.send(embed=discord.Embed(description=f"⚠️ Are you sure you want to delete **{amount}** messages?", color=discord.Color.orange()), view=view)
        await view.wait()
        
        if not view.value: return await msg.edit(embed=discord.Embed(description="🛑 Cancelled.", color=discord.Color.grey()), view=None)
        
        deleted = await ctx.channel.purge(limit=amount + 2) # +2 accounts for the command and the confirmation
        await ctx.send(embed=discord.Embed(description=f"🧹 **Swept {len(deleted)-2} messages.**", color=discord.Color.green()), delete_after=4)

    @commands.hybrid_command(name="nuke", description="Clone and delete a channel to wipe its history.")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx): 
        await ctx.defer()
        view = ConfirmView(ctx)
        msg = await ctx.send(embed=discord.Embed(title="☢️ TACTICAL NUKE", description="Are you sure you want to annihilate this channel?", color=discord.Color.red()), view=view)
        await view.wait()
        
        if not view.value: return await msg.edit(embed=discord.Embed(description="🛑 Aborted.", color=discord.Color.grey()), view=None)
        
        pos = ctx.channel.position
        new_channel = await ctx.channel.clone()
        await ctx.channel.delete()
        await new_channel.edit(position=pos)
        
        embed = discord.Embed(description="☢️ **TACTICAL NUKE DEPLOYED!**\nChannel history has been eradicated.", color=discord.Color.dark_red())
        embed.set_image(url=get_gif("nuke"))
        await new_channel.send(embed=embed)


    # ========================================================================
    # MESSAGE LOGS
    # ========================================================================
    @commands.hybrid_command(name="snipe", description="Recover the last deleted message in the channel.")
    async def snipe(self, ctx):
        await ctx.defer()
        d = snipes.get(ctx.channel.id)
        if not d: return await ctx.send(embed=discord.Embed(description="❌ There is nothing to snipe!", color=discord.Color.red()))
        
        time_ago = int(time.time() - d['time'])
        embed = discord.Embed(description=d["content"], color=discord.Color.dark_theme())
        embed.set_author(name=d["author"], icon_url=d["avatar"])
        embed.set_footer(text=f"Deleted {time_ago} seconds ago")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="editsnipe", description="See what a message said before it was edited.")
    async def editsnipe(self, ctx):
        await ctx.defer()
        d = edit_snipes.get(ctx.channel.id)
        if not d: return await ctx.send(embed=discord.Embed(description="❌ No edited messages found in memory!", color=discord.Color.red()))
        
        embed = discord.Embed(title="📝 Message Edited", color=discord.Color.orange())
        embed.set_author(name=d["author"], icon_url=d["avatar"])
        embed.add_field(name="Original (Before)", value=d["before"], inline=False)
        embed.add_field(name="Current (After)", value=d["after"], inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
