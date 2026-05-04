
import discord
from discord.ext import commands
import json
import asyncio
from core import db, save_db, gif_db, save_gifs, ConfirmView, PaginationView, ai_client, ask_groq, AIBossFightView

# ==========================================
# INTERACTIVE GIF GALLERY UI
# ==========================================
class GifViewer(discord.ui.View):
    def __init__(self, ctx, category, gifs):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.category = category
        self.gifs = gifs
        self.index = 0

    async def update_message(self, interaction: discord.Interaction):
        if not self.gifs:
            for child in self.children: child.disabled = True
            return await interaction.response.edit_message(content=f"🗑️ The `{self.category}` gallery is now completely empty.", embed=None, view=self)

        embed = discord.Embed(title=f"📂 GIF Gallery: {self.category}", description=f"**Index:** {self.index + 1} of {len(self.gifs)}\n**Link:** [Click Here]({self.gifs[self.index]})", color=discord.Color.blurple())
        embed.set_image(url=self.gifs[self.index])
        
        # Update button states
        self.children[0].disabled = (self.index == 0)
        self.children[1].disabled = (self.index == len(self.gifs) - 1)
        
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.primary)
    async def prev_btn(self, interaction, button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not your gallery!", ephemeral=True)
        self.index -= 1
        await self.update_message(interaction)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction, button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not your gallery!", ephemeral=True)
        self.index += 1
        await self.update_message(interaction)

    @discord.ui.button(label="🗑️ Delete This GIF", style=discord.ButtonStyle.danger)
    async def del_btn(self, interaction, button):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("❌ Not your gallery!", ephemeral=True)
        
        # Remove from the actual database
        removed_url = self.gifs.pop(self.index)
        gif_db[self.category] = self.gifs
        save_gifs(gif_db)
        
        # Adjust index if we deleted the last item in the list
        if self.index >= len(self.gifs) and self.index > 0:
            self.index -= 1
            
        await interaction.followup.send(f"✅ **Deleted GIF #{self.index + 2}** from `{self.category}`.", ephemeral=True)
        await self.update_message(interaction)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # DYNAMIC VISUAL GIF MANAGER
    # ==========================================
    @commands.hybrid_command(name="gif_add", description="[Admin] Add a new GIF to a category.")
    @commands.has_permissions(administrator=True)
    async def gif_add(self, ctx, category: str, url: str):
        await ctx.defer()
        c = category.lower()
        if not url.startswith("http"):
            return await ctx.send(embed=discord.Embed(description="❌ **Invalid Link!** It must start with `http`.", color=discord.Color.red()))
            
        if c not in gif_db: gif_db[c] = []
        gif_db[c].append(url)
        save_gifs(gif_db)
        
        embed = discord.Embed(description=f"✅ **GIF Added to `{c}`!** (Index: {len(gif_db[c])})", color=discord.Color.green())
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="gif_remove", description="[Admin] Manually remove a GIF by its Index Number.")
    @commands.has_permissions(administrator=True)
    async def gif_remove(self, ctx, category: str, index_number: int):
        await ctx.defer()
        c = category.lower()
        if c not in gif_db or not gif_db[c]:
            return await ctx.send(embed=discord.Embed(description=f"❌ Category `{c}` is empty or doesn't exist.", color=discord.Color.red()))
            
        if index_number < 1 or index_number > len(gif_db[c]):
            return await ctx.send(embed=discord.Embed(description=f"❌ Invalid Index. Choose a number between 1 and {len(gif_db[c])}.", color=discord.Color.red()))
            
        removed = gif_db[c].pop(index_number - 1)
        save_gifs(gif_db)
        await ctx.send(embed=discord.Embed(description=f"🗑️ **Deleted GIF #{index_number}** from `{c}`.", color=discord.Color.red()))

    @commands.hybrid_command(name="gif_list", description="[Admin] Open the Interactive Visual GIF Gallery.")
    @commands.has_permissions(administrator=True)
    async def gif_list(self, ctx, category: str = None):
        await ctx.defer()
        # If no category provided, show the master list of folders
        if not category:
            cats = "\n".join([f"**{k}**: {len(v)} GIFs" for k, v in gif_db.items()])
            return await ctx.send(embed=discord.Embed(title="📂 Database Categories", description=cats + "\n\n*Use `/gif_list <category>` to view them visually!*", color=discord.Color.blue()))
            
        c = category.lower()
        if c not in gif_db or not gif_db[c]:
            return await ctx.send(embed=discord.Embed(description=f"❌ The `{c}` category is empty.", color=discord.Color.red()))
            
        # Spawn the TV Screen Viewer
        gifs = gif_db[c].copy()
        view = GifViewer(ctx, c, gifs)
        embed = discord.Embed(title=f"📂 GIF Gallery: {c}", description=f"**Index:** 1 of {len(gifs)}\n**Link:** [Click Here]({gifs[0]})", color=discord.Color.blurple())
        embed.set_image(url=gifs[0])
        
        # Lock Prev button on launch
        view.children[0].disabled = True
        if len(gifs) == 1: view.children[1].disabled = True 
        
        await ctx.send(embed=embed, view=view)


    # ==========================================
    # SERVER DEPLOYMENT & SETUP
    # ==========================================
    @commands.hybrid_command(name="setaichannel", description="Sets AI auto-reply channel.")
    @commands.has_permissions(administrator=True)
    async def setaichannel(self, ctx): 
        db["config"]["ai_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🤖 **AI Auto-Chat bound to {ctx.channel.mention}.**", color=discord.Color.green()))

    @commands.hybrid_command(name="setcmdchannel", description="Locks commands.")
    @commands.has_permissions(administrator=True)
    async def setcmdchannel(self, ctx): 
        db["config"]["cmd_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🔒 **Commands locked to {ctx.channel.mention}.**", color=discord.Color.green()))

    @commands.hybrid_command(name="seteventchannel", description="Sets AI event channel.")
    @commands.has_permissions(administrator=True)
    async def seteventchannel(self, ctx): 
        db["config"]["event_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(embed=discord.Embed(description=f"🌟 **AI Events bound to {ctx.channel.mention}.**", color=discord.Color.green()))

    @commands.hybrid_command(name="deployserver", description="Wipes and builds server layout.")
    @commands.has_permissions(administrator=True)
    async def deployserver(self, ctx):
        view = ConfirmView(ctx)
        msg = await ctx.send(embed=discord.Embed(title="⚠️ CLEAN SLATE PROTOCOL", description="Are you sure you want to completely WIPE and rebuild the server?", color=discord.Color.red()), view=view)
        await view.wait()
        if not view.value: return await msg.edit(embed=discord.Embed(description="🛑 Protocol Cancelled.", color=discord.Color.grey()), view=None)

        await msg.edit(embed=discord.Embed(description="⚙️ Wiping channels & roles...", color=discord.Color.orange()), view=None)
        g = ctx.guild
        for c in g.channels:
            try: await c.delete(); await asyncio.sleep(0.5)
            except: pass
        for r in g.roles:
            if r.name != "@everyone" and not r.managed and r < g.me.top_role:
                try: await r.delete(); await asyncio.sleep(0.5)
                except: pass
                
        cr = {}
        for r in [{"name": "Admin", "color": discord.Color.red()}, {"name": "Moderator", "color": discord.Color.orange()}, {"name": "Jailed", "color": discord.Color.dark_grey()}]:
            try: cr[r["name"]] = await g.create_role(name=r["name"], color=r["color"], permissions=discord.Permissions(administrator=(r["name"] == "Admin")), hoist=True); await asyncio.sleep(1)
            except: pass
        try: await ctx.author.add_roles(cr.get("Admin"))
        except: pass
        
        ci = await g.create_category("📌 INFORMATION"); await g.create_text_channel("rules", category=ci)
        cc = await g.create_category("💬 CHAT")
        gc = await g.create_text_channel("general", category=cc)
        bc = await g.create_text_channel("bot-commands", category=cc)
        ac = await g.create_text_channel("talk-to-ai", category=cc)
        cv = await g.create_category("🔊 VOICE"); await g.create_voice_channel("General VC", category=cv)
        
        if "Jailed" in cr:
            for cat in g.categories:
                try: await cat.set_permissions(cr["Jailed"], read_messages=False, connect=False)
                except: pass
                
        db["config"]["cmd_channel"] = bc.id; db["config"]["ai_channel"] = ac.id; db["config"]["event_channel"] = gc.id; save_db(db)
        await gc.send(embed=discord.Embed(title="✅ Deployment Complete", description=f"{ctx.author.mention}, server is operational.", color=discord.Color.green()))


    # ==========================================
    # GOD MODE & AI FEATURES
    # ==========================================
    @commands.hybrid_command(name='aicommand', description="Master AI brain. Execute python dynamically.")
    @commands.has_permissions(administrator=True)
    async def aicommand(self, ctx, *, instruction: str):
        await ctx.defer() 
        if not ai_client: return await ctx.send(embed=discord.Embed(description="🤖 **AI is offline.**", color=discord.Color.red()))
        prompt = f"""Omnipotent Discord bot. Boss commanded: "{instruction}"
        Output a JSON array: 1. Reply: {{"action": "reply", "message": "text"}} 2. Execute Python: {{"action": "execute", "code": "await ctx.send('Done!')"}}
        STRICT RULES: Output ONLY a valid JSON array. Write valid discord.py async code."""
        try:
            raw_res = await ask_groq([{"role": "user", "content": prompt}])
            s, e = raw_res.find('['), raw_res.rfind(']')
            clean = raw_res[s:e+1] if s != -1 else raw_res.replace('```json', '').replace('```python', '').replace('```', '').strip()
            if clean.startswith('{'): clean = f"[{clean}]"
            for act in json.loads(clean):
                if act.get("action") == "reply": await ctx.send(embed=discord.Embed(description=f"🤖 {act.get('message')}", color=discord.Color.blurple()))
                elif act.get("action") == "execute":
                    msg = await ctx.send(embed=discord.Embed(description="⚡ **Executing Python...**", color=discord.Color.orange()))
                    try:
                        w = "async def __ai_exec():\n" + "\n".join([f"    {l}" for l in act.get("code", "").split("\n")])
                        env = {'discord': discord, 'bot': self.bot, 'ctx': ctx, 'asyncio': asyncio, 'db': db}
                        exec(w, env); await env['__ai_exec'](); await msg.edit(embed=discord.Embed(description="✅ **Execution Successful!**", color=discord.Color.green()))
                    except Exception as err: await msg.edit(embed=discord.Embed(description=f"⚠️ **Failed:**\n```py\n{err}\n```", color=discord.Color.red()))
        except Exception as e: await ctx.send(embed=discord.Embed(description=f"❌ **Error:** {e}", color=discord.Color.red()))

    @commands.hybrid_command(name="bossfight", description="Start an interactive Story-Mode Anime Boss Raid.")
    async def bossfight(self, ctx):
        await ctx.defer()
        if not ai_client: return await ctx.send(embed=discord.Embed(description="❌ AI offline.", color=discord.Color.red()))
        chat_history = [
            {"role": "system", "content": "You are an elite AI Dungeon Master running an immersive Anime/RPG story mode boss raid. Narrate the environment, combat, and mechanics vividly. Keep responses to 2 short paragraphs. Append '[CONTINUE]', '[WIN]', or '[LOSE]' at the exact end of every response."}, 
            {"role": "user", "content": "Generate the opening cinematic scene of an epic Anime Raid Boss encounter. Describe a terrifying, colossal boss spawning in. Do NOT resolve the fight yet. End with the boss preparing its first strike."}
        ]
        try: scen = await ask_groq(chat_history)
        except: return await ctx.send(embed=discord.Embed(description="❌ Connection failed.", color=discord.Color.red()))
        chat_history.append({"role": "assistant", "content": scen})
        
        # Import the get_gif dynamically to avoid circular import loops just in case
        from core import get_gif 
        
        embed = discord.Embed(title="⚔️ RAID BOSS SPAWNED", description=scen, color=discord.Color.dark_red())
        embed.set_image(url=get_gif("boss_spawn"))
        await ctx.send(embed=embed, view=AIBossFightView(ctx, ai_client, chat_history))

    @commands.hybrid_command(name="masterlist", description="View all 100+ bot commands in high detail.")
    async def masterlist(self, ctx):
        e1 = discord.Embed(title="🤖 Masterlist: Admin & Setup (Page 1/6)", description="Bot configuration and setup.", color=discord.Color.blue())
        e1.add_field(name="Setup", value="`/deployserver`, `/setaichannel`, `/setcmdchannel`, `/seteventchannel`, `/unsetchannel`", inline=False)
        e1.add_field(name="Database GIFs", value="`/gif_add`, `/gif_remove`, `/gif_list`", inline=False)
        
        e2 = discord.Embed(title="🛡️ Masterlist: Moderation (Page 2/6)", description="Keep the server safe.", color=discord.Color.red())
        e2.add_field(name="Punishments", value="`/kick`, `/ban`, `/tempban`, `/tempmute`, `/jail`, `/unjail`", inline=False)
        e2.add_field(name="Warnings", value="`/warn`, `/warnings`, `/clearwarns`", inline=False)
        e2.add_field(name="Security", value="`/lockdown`, `/unlockdown`, `/purge`, `/nuke`, `/slowmode`", inline=False)
        e2.add_field(name="Logs", value="`/snipe`, `/editsnipe`", inline=False)

        e3 = discord.Embed(title="💰 Masterlist: Economy (Page 3/6)", description="Get rich or die trying.", color=discord.Color.gold())
        e3.add_field(name="Money", value="`/bal`, `/rich`, `/daily`, `/weekly`, `/give`", inline=False)
        e3.add_field(name="Hustle", value="`/work`, `/crime`, `/rob`, `/heist`, `/bounty`, `/claimbounty`", inline=False)
        e3.add_field(name="Items", value="`/shop`, `/inventory`, `/trade`", inline=False)
        
        e4 = discord.Embed(title="⚔️ Masterlist: RPG, AI & Games (Page 4/6)", description="Features and utilities.", color=discord.Color.green())
        e4.add_field(name="AI Tools", value="`/aicommand`, `/bossfight`, `/vibecheck`, `/roast_history`, `/tldr`, `/lore`, `/debate`, `/define`, `/urban`, `/forceevent`, `/gothic_translate`", inline=False)
        e4.add_field(name="Casino", value="`/slots`, `/blackjack`, `/coinflip`", inline=False)
        e4.add_field(name="RPG & Levels", value="`/level`, `/leaderboard_levels`, `/givexp`, `/removexp`, `/setlevel`, `/rewards`, `/fish`, `/hunt`, `/mine`, `/quest`", inline=False)

        e5 = discord.Embed(title="⚙️ Masterlist: Utilities (Page 5/6)", description="Helpful server tools.", color=discord.Color.light_grey())
        e5.add_field(name="Social", value="`/rep`, `/leaderboard_rep`, `/poll`, `/remindme`, `/afk`", inline=False)
        e5.add_field(name="Stats", value="`/userhistory`, `/roleinfo`, `/servericon`, `/avatar`, `/serverinfo`, `/ping`", inline=False)
        e5.add_field(name="Misc", value="`/giveaway_start`, `/giveaway_reroll`, `/ticket_setup`, `/ticket_close`, `/weather`, `/calc`, `/translate`", inline=False)

        e6 = discord.Embed(title="🤡 Masterlist: Prefix (Page 6/6)", description="**Use `!` for these (e.g., `!hack`)**", color=discord.Color.purple())
        e6.add_field(name="Trolls", value="`!fakeban`, `!rickroll`, `!roast`, `!compliment`, `!confess`, `!kill`, `!revive`, `!meme`, `!dadjoke`, `!choose`, `!spank`, `!jailbreak`, `!eightball`, `!hack`, `!ship`", inline=False)
        e6.add_field(name="Raters", value="`!howgay`, `!simpmeter`, `!susmeter`", inline=False)
        e6.add_field(name="Anime Actions", value="`!pat`, `!punch`, `!bite`, `!kiss`, `!smug`, `!cry`, `!quote`, `!powerlevel`, `!domain_expansion`, `!bankai`", inline=False)
        
        await ctx.send(embed=e1, view=PaginationView(ctx, [e1, e2, e3, e4, e5, e6]))

async def setup(bot):
    await bot.add_cog(Admin(bot))
