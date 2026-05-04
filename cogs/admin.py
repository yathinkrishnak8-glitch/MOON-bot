import discord
from discord.ext import commands
import json
import asyncio
from core import db, save_db, gif_db, save_gifs, ai_client, ask_groq
from ui import ConfirmView, PaginationView, AIBossFightView

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
        
        self.gifs.pop(self.index)
        gif_db[self.category] = self.gifs
        save_gifs(gif_db)
        
        if self.index >= len(self.gifs) and self.index > 0:
            self.index -= 1
            
        await interaction.followup.send(f"✅ **Deleted GIF #{self.index + 2}** from `{self.category}`.", ephemeral=True)
        await self.update_message(interaction)


# ==========================================
# UI CLASS: AI TEMPLATE DEPLOYMENT
# ==========================================
class AITemplateView(discord.ui.View):
    def __init__(self, ctx, template_data):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.template = template_data

    async def execute_build(self, nuke: bool, interaction: discord.Interaction = None, msg: discord.Message = None):
        user = interaction.user if interaction else self.ctx.author
        if user != self.ctx.author:
            if interaction: return await interaction.response.send_message("❌ You are not the architect.", ephemeral=True)
            return
            
        for child in self.children: child.disabled = True
        
        # Initial Status Update
        if interaction:
            await interaction.response.edit_message(embed=discord.Embed(description="⚙️ **Initializing Construction Protocol...**", color=discord.Color.orange()), view=self)
            work_msg = interaction.message
        else:
            work_msg = msg
            await work_msg.edit(embed=discord.Embed(description="⚙️ **Initializing Construction Protocol...**", color=discord.Color.orange()), view=self)

        g = self.ctx.guild

        if nuke:
            await work_msg.edit(embed=discord.Embed(description="☢️ **Phase 1:** Eradicating old channels and roles...", color=discord.Color.red()), view=self)
            for c in g.channels:
                # 🔥 THE FIX: Do not delete the channel we are currently typing the progress in!
                if c.id == work_msg.channel.id: continue 
                try: await c.delete(); await asyncio.sleep(0.4)
                except: pass
            for r in g.roles:
                if r.name != "@everyone" and not r.managed and r < g.me.top_role:
                    try: await r.delete(); await asyncio.sleep(0.4)
                    except: pass

        # 1. Build Roles
        await work_msg.edit(embed=discord.Embed(description="🛡️ **Phase 2:** Forging server roles...", color=discord.Color.blue()), view=self)
        for r_data in self.template.get("roles", []):
            try: await g.create_role(name=r_data["name"], color=discord.Color(r_data["color"]), hoist=r_data["hoist"]); await asyncio.sleep(0.4)
            except: pass

        # 2. Build Categories & Channels
        await work_msg.edit(embed=discord.Embed(description="🏗️ **Phase 3:** Constructing categories and channels...", color=discord.Color.gold()), view=self)
        for cat_data in self.template.get("categories", []):
            try: 
                new_cat = await g.create_category(cat_data["name"])
                await asyncio.sleep(0.4)
                for chan in cat_data.get("channels", []):
                    if chan["type"] == "text":
                        await g.create_text_channel(chan["name"], category=new_cat)
                    elif chan["type"] == "voice":
                        await g.create_voice_channel(chan["name"], category=new_cat)
                    await asyncio.sleep(0.4)
            except: pass

        # 3. Post Rules (If AI generated them)
        if self.template.get("has_rules") and self.template.get("rules_text"):
            await work_msg.edit(embed=discord.Embed(description="📜 **Phase 4:** Drafting and posting server rules...", color=discord.Color.teal()), view=self)
            rules_channel = next((c for c in g.text_channels if "rule" in c.name.lower()), None)
            
            # If no rules channel found, pick the first one that isn't the active work channel
            if not rules_channel and g.text_channels:
                rules_channel = next((c for c in g.text_channels if c.id != work_msg.channel.id), None)
                if not rules_channel: rules_channel = g.text_channels[0]
                
            if rules_channel:
                rules_embed = discord.Embed(title="📜 Official Server Rules", description=self.template["rules_text"], color=discord.Color.gold())
                if g.icon: rules_embed.set_thumbnail(url=g.icon.url)
                try: await rules_channel.send(embed=rules_embed)
                except: pass

        # Find a clean channel to send the final success ping
        for c in g.text_channels:
            if c.id != work_msg.channel.id:
                try: 
                    await c.send(embed=discord.Embed(title="✅ AI Deployment Complete", description=f"{self.ctx.author.mention}, the architecture is complete.", color=discord.Color.green()))
                    break
                except: pass
                
        try: await work_msg.edit(embed=discord.Embed(title="✅ Deployment Complete", description="Operations successful.", color=discord.Color.green()))
        except: pass
        self.stop()

    @discord.ui.button(label="💥 Rebuild (Wipe & Replace)", style=discord.ButtonStyle.danger)
    async def rebuild_btn(self, interaction, button):
        await self.execute_build(nuke=True, interaction=interaction)

    @discord.ui.button(label="🛠️ Redesign (Add & Expand)", style=discord.ButtonStyle.success)
    async def expand_btn(self, interaction, button):
        await self.execute_build(nuke=False, interaction=interaction)


# ==========================================
# COG CLASS: Admin & Setup
# ==========================================
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
        if not url.startswith("http"): return await ctx.send("❌ **Invalid Link!**")
        if c not in gif_db: gif_db[c] = []
        gif_db[c].append(url); save_gifs(gif_db)
        await ctx.send(embed=discord.Embed(description=f"✅ **GIF Added to `{c}`!**", color=discord.Color.green()).set_image(url=url))

    @commands.hybrid_command(name="gif_remove", description="[Admin] Remove a GIF by its Index Number.")
    @commands.has_permissions(administrator=True)
    async def gif_remove(self, ctx, category: str, index_number: int):
        await ctx.defer()
        c = category.lower()
        if c not in gif_db or not gif_db[c]: return await ctx.send("❌ Category is empty.")
        if index_number < 1 or index_number > len(gif_db[c]): return await ctx.send("❌ Invalid Index.")
        gif_db[c].pop(index_number - 1); save_gifs(gif_db)
        await ctx.send(embed=discord.Embed(description=f"🗑️ **Deleted GIF #{index_number}**.", color=discord.Color.red()))

    @commands.hybrid_command(name="gif_list", description="[Admin] Open the Interactive Visual GIF Gallery.")
    @commands.has_permissions(administrator=True)
    async def gif_list(self, ctx, category: str = None):
        await ctx.defer()
        if not category:
            cats = "\n".join([f"**{k}**: {len(v)} GIFs" for k, v in gif_db.items()])
            return await ctx.send(embed=discord.Embed(title="📂 Database Categories", description=cats, color=discord.Color.blue()))
        c = category.lower()
        if c not in gif_db or not gif_db[c]: return await ctx.send("❌ Category is empty.")
        gifs = gif_db[c].copy()
        view = GifViewer(ctx, c, gifs)
        embed = discord.Embed(title=f"📂 GIF Gallery: {c}", description=f"**Index:** 1 of {len(gifs)}", color=discord.Color.blurple()).set_image(url=gifs[0])
        view.children[0].disabled = True
        if len(gifs) == 1: view.children[1].disabled = True 
        await ctx.send(embed=embed, view=view)


    # ==========================================
    # AI ARCHITECT (PROMPT -> SERVER)
    # ==========================================
    @commands.hybrid_command(name="ai_template", description="Generate an entire server layout and ruleset using an AI prompt.")
    @commands.has_permissions(administrator=True)
    async def ai_template(self, ctx, *, prompt: str):
        await ctx.defer()
        if not ai_client: return await ctx.send(embed=discord.Embed(description="🤖 **AI is offline.**", color=discord.Color.red()))
        
        sys_prompt = f"""You are an expert Discord Server Architect. Generate a high-quality server layout based on this prompt: "{prompt}"
        Output ONLY a raw, perfectly formatted JSON object.
        SCHEMA:
        {{
          "roles": [{{"name": "string", "color": 16711680, "hoist": true}}],
          "categories": [{{"name": "string", "channels": [{{"name": "string", "type": "text"}}, {{"name": "string", "type": "voice"}}]}}],
          "has_rules": true,
          "rules_text": "Detailed and themed server rules using \\n for line breaks. Leave empty if has_rules is false."
        }}
        Generate at least 5 roles and 4 categories with multiple channels. Set "has_rules" to true and write engaging rules if the prompt implies a community or RP server."""
        
        msg = await ctx.send(embed=discord.Embed(description="🧠 **AI is drafting the server blueprint and rulesets...**", color=discord.Color.purple()))
        
        try:
            raw_res = await ask_groq([{"role": "user", "content": sys_prompt}], inject_personality=False)
            
            s, e = raw_res.find('{'), raw_res.rfind('}')
            if s == -1 or e == -1: raise Exception("AI did not return valid JSON structure.")
            clean = raw_res[s:e+1].strip()
            blueprint = json.loads(clean)
            
            desc = "**🛡️ Roles:** " + ", ".join([r.get('name', 'Role') for r in blueprint.get('roles', [])]) + "\n\n**🏗️ Layout:**\n"
            for cat in blueprint.get('categories', []):
                desc += f"📁 **{cat.get('name', 'Category')}**\n"
                for chan in cat.get('channels', []):
                    icon = "💬" if chan.get('type') == 'text' else "🔊"
                    desc += f"  {icon} {chan.get('name', 'channel')}\n"
                    
            if blueprint.get("has_rules"):
                desc += "\n📜 **Rules Included:** The AI generated a custom ruleset."
            
            embed = discord.Embed(title="🏗️ AI Blueprint Generated", description=desc[:4000], color=discord.Color.gold())
            embed.set_footer(text="Choose how you want to apply this blueprint.")
            await msg.edit(embed=embed, view=AITemplateView(ctx, blueprint))
            
        except Exception as e:
            await msg.edit(embed=discord.Embed(description=f"❌ **Failed to generate blueprint:** {e}", color=discord.Color.red()))


    # ==========================================
    # STATIC TEMPLATES & DEPLOYMENT
    # ==========================================
    @commands.hybrid_command(name="template_save", description="Copy the current server layout and save it as a template.")
    @commands.has_permissions(administrator=True)
    async def template_save(self, ctx, name: str):
        await ctx.defer()
        g = ctx.guild
        template_data = {"roles": [], "categories": [], "uncategorized": [], "has_rules": False, "rules_text": ""}

        for r in g.roles:
            if r.name != "@everyone" and not r.managed:
                template_data["roles"].append({"name": r.name, "color": r.color.value, "hoist": r.hoist})

        for cat in g.categories:
            cat_data = {"name": cat.name, "channels": []}
            for chan in cat.channels:
                if isinstance(chan, discord.TextChannel): cat_data["channels"].append({"name": chan.name, "type": "text"})
                elif isinstance(chan, discord.VoiceChannel): cat_data["channels"].append({"name": chan.name, "type": "voice"})
            template_data["categories"].append(cat_data)

        for chan in g.channels:
            if chan.category is None:
                if isinstance(chan, discord.TextChannel): template_data["uncategorized"].append({"name": chan.name, "type": "text"})
                elif isinstance(chan, discord.VoiceChannel): template_data["uncategorized"].append({"name": chan.name, "type": "voice"})

        db.setdefault("server_templates", {})[name.lower()] = template_data
        save_db(db)
        await ctx.send(embed=discord.Embed(title="💾 Template Saved", description=f"Successfully copied **{g.name}** into template: `{name.lower()}`", color=discord.Color.green()))

    @commands.hybrid_command(name="template_list", description="List all saved server blueprints.")
    @commands.has_permissions(administrator=True)
    async def template_list(self, ctx):
        await ctx.defer()
        templates = db.get("server_templates", {})
        if not templates: return await ctx.send(embed=discord.Embed(description="❌ No templates saved.", color=discord.Color.red()))
        desc = ""
        for name, data in templates.items(): desc += f"📁 **{name}** (Roles: {len(data.get('roles', []))} | Cats: {len(data.get('categories', []))})\n"
        await ctx.send(embed=discord.Embed(title="🗄️ Saved Server Templates", description=desc, color=discord.Color.blurple()))

    @commands.hybrid_command(name="template_deploy", description="Wipe the server and deploy a custom saved template.")
    @commands.has_permissions(administrator=True)
    async def template_deploy(self, ctx, name: str):
        template_name = name.lower()
        templates = db.get("server_templates", {})
        if template_name not in templates: return await ctx.send("❌ Template does not exist.")
        
        view = ConfirmView(ctx)
        msg = await ctx.send(embed=discord.Embed(title=f"⚠️ DEPLOYING: {template_name.upper()}", description="Are you sure? This will wipe the ENTIRE server.", color=discord.Color.red()), view=view)
        await view.wait()
        
        if not view.value: return await msg.edit(embed=discord.Embed(description="🛑 Aborted.", color=discord.Color.grey()), view=None)

        view_bridge = AITemplateView(ctx, templates[template_name])
        await view_bridge.execute_build(nuke=True, msg=msg)


    @commands.hybrid_command(name="deployserver", description="Wipes and builds the DEFAULT server layout.")
    @commands.has_permissions(administrator=True)
    async def deployserver(self, ctx):
        view = ConfirmView(ctx)
        msg = await ctx.send(embed=discord.Embed(title="⚠️ CLEAN SLATE PROTOCOL", description="Are you sure you want to completely WIPE and rebuild the server with the Default Template?", color=discord.Color.red()), view=view)
        await view.wait()
        if not view.value: return await msg.edit(embed=discord.Embed(description="🛑 Protocol Cancelled.", color=discord.Color.grey()), view=None)

        await msg.edit(embed=discord.Embed(description="⚙️ Wiping channels & roles...", color=discord.Color.orange()), view=None)
        g = ctx.guild
        for c in g.channels:
            if c.id == msg.channel.id: continue # 🔥 Fixed here too!
            try: await c.delete(); await asyncio.sleep(0.4)
            except: pass
        for r in g.roles:
            if r.name != "@everyone" and not r.managed and r < g.me.top_role:
                try: await r.delete(); await asyncio.sleep(0.4)
                except: pass
                
        cr = {}
        for r in [{"name": "Admin", "color": discord.Color.red()}, {"name": "Moderator", "color": discord.Color.orange()}, {"name": "Jailed", "color": discord.Color.dark_grey()}]:
            try: cr[r["name"]] = await g.create_role(name=r["name"], color=r["color"], permissions=discord.Permissions(administrator=(r["name"] == "Admin")), hoist=True); await asyncio.sleep(0.5)
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
        await gc.send(embed=discord.Embed(title="✅ Default Deployment Complete", description=f"{ctx.author.mention}, server is operational.", color=discord.Color.green()))
        try: await msg.edit(embed=discord.Embed(title="✅ Complete", description="Deployment operational.", color=discord.Color.green()))
        except: pass


    # ==========================================
    # GOD MODE & CHANNEL CONFIGS
    # ==========================================
    @commands.hybrid_command(name="setaichannel", description="Sets AI auto-reply channel.")
    @commands.has_permissions(administrator=True)
    async def setaichannel(self, ctx): 
        db["config"]["ai_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(f"🤖 **AI Auto-Chat bound to {ctx.channel.mention}.**")

    @commands.hybrid_command(name="setcmdchannel", description="Locks commands.")
    @commands.has_permissions(administrator=True)
    async def setcmdchannel(self, ctx): 
        db["config"]["cmd_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(f"🔒 **Commands locked to {ctx.channel.mention}.**")

    @commands.hybrid_command(name="seteventchannel", description="Sets AI event channel.")
    @commands.has_permissions(administrator=True)
    async def seteventchannel(self, ctx): 
        db["config"]["event_channel"] = ctx.channel.id; save_db(db)
        await ctx.send(f"🌟 **AI Events bound to {ctx.channel.mention}.**")

    @commands.hybrid_command(name='aicommand', description="Master AI brain. Execute python dynamically.")
    @commands.is_owner()
    async def aicommand(self, ctx, *, instruction: str):
        await ctx.defer() 
        if not ai_client: return await ctx.send("🤖 **AI is offline.**")
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

    @commands.hybrid_command(name="masterlist", description="View all 100+ bot commands in one massive list.")
    async def masterlist(self, ctx):
        await ctx.defer()
        embed = discord.Embed(title="📜 The Ultimate Masterlist", description="Every single command baked into the HabibiBot engine.", color=discord.Color.gold())
        embed.add_field(name="🤖 Setup & Admin", value="`/ai_template`, `/template_save`, `/template_deploy`, `/template_list`, `/deployserver`, `/setaichannel`, `/setcmdchannel`, `/seteventchannel`\n`/gif_add`, `/gif_remove`, `/gif_list`", inline=False)
        embed.add_field(name="🛡️ Moderation", value="**Punishments:** `/kick`, `/ban`, `/tempban`, `/timeout`, `/jail`, `/unjail`\n**Warnings:** `/warn`, `/warnings`, `/clearwarns`\n**Security:** `/lockdown`, `/unlockdown`, `/purge`, `/nuke`, `/slowmode`\n**Logs:** `/snipe`, `/editsnipe`", inline=False)
        embed.add_field(name="💰 Economy & Hustle", value="**Money:** `/bal`, `/rich`, `/daily`, `/weekly`\n**Hustle:** `/work`, `/crime`, `/rob`, `/heist`\n**Items:** `/shop`, `/inventory`, `/trade`, `/craft`", inline=False)
        embed.add_field(name="⚔️ RPG, AI & Games", value="**AI Tools:** `/aicommand`, `/bossfight`, `/vibecheck`, `/roast_history`, `/tldr`, `/lore`, `/debate`, `/define`, `/urban`, `/gothic_translate`\n**Casino:** `/slots`, `/blackjack`, `/coinflip`\n**RPG & Levels:** `/hunt`, `/zoo`, `/sell_monster`, `/fuse_monster`, `/lootbox`, `/rank`, `/leaderboard_levels`, `/givexp`, `/quest`", inline=False)
        embed.add_field(name="⚙️ Utilities", value="**Profiles:** `/profile`, `/userhistory`, `/roleinfo`, `/servericon`, `/avatar`, `/serverinfo`, `/ping`\n**Misc:** `/giveaway_start`, `/giveaway_roll`, `/remindme`, `/calc`, `/poll`", inline=False)
        embed.add_field(name="🤡 Prefix Trolls & Anime (Use !)", value="**Trolls:** `!fakeban`, `!rickroll`, `!roast`, `!compliment`, `!confess`, `!kill`, `!revive`, `!dadjoke`, `!choose`, `!spank`, `!jailbreak`, `!eightball`, `!hack`, `!ship`\n**Raters:** `!howgay`, `!simpmeter`, `!susmeter`\n**Anime Actions:** `!pat`, `!punch`, `!bite`, `!kiss`, `!smug`, `!cry`, `!quote`, `!powerlevel`, `!domain_expansion`, `!bankai`", inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Admin(bot))
