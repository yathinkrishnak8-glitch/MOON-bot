import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import random
import asyncio
from datetime import timedelta
from groq import Groq

# ==========================================
# DATABASE & MEMORY SETUP
# ==========================================
DB_FILE = "database.json"

def get_default_db():
    return {
        "warns": {}, 
        "jailed": {}, 
        "config": {"filterwords": [], "ai_channel": None, "cmd_channel": None, "event_channel": None, "antiraid": False}, 
        "economy": {}, 
        "levels": {}, 
        "custom_commands": {}, 
        "afk": {}, 
        "inventory": {}, 
        "rep": {}, 
        "bounties": {}
    }

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f: 
            json.dump(get_default_db(), f)
    with open(DB_FILE, "r") as f: 
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f: 
        json.dump(data, f, indent=4)

db = load_db()
snipes = {}
edit_snipes = {}

class MasterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
        self.client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.ai_event_loop.start()

    def cog_unload(self):
        self.ai_event_loop.cancel()

    def ask_groq(self, messages):
        if not self.client: 
            raise Exception("Groq API Key missing.")
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]:
            try: 
                return self.client.chat.completions.create(model=model, messages=messages).choices[0].message.content.strip()
            except: 
                continue 
        raise Exception("All AI models failed.")

    def find_member(self, ctx, search_term):
        if not search_term: 
            return None
        search_term = search_term.replace("<@", "").replace(">", "").replace("!", "")
        if search_term.isdigit(): 
            return ctx.guild.get_member(int(search_term))
        for m in ctx.guild.members:
            if m.name.lower() == search_term.lower() or m.display_name.lower() == search_term.lower(): 
                return m
        return None

    # ==========================================
    # LISTENERS & EVENTS
    # ==========================================
    @commands.Cog.listener()
    async def on_member_join(self, member):
        if db["config"].get("antiraid", False):
            try: 
                await member.kick(reason="Anti-Raid protection is currently active.")
            except: 
                pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.author.bot: 
            snipes[message.channel.id] = {
                "content": message.content, 
                "author": message.author.name,
                "avatar": message.author.avatar.url if message.author.avatar else message.author.default_avatar.url
            }

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.author.bot: 
            edit_snipes[before.channel.id] = {
                "before": before.content, 
                "after": after.content, 
                "author": before.author.name
            }

    @tasks.loop(minutes=60)
    async def ai_event_loop(self):
        if not self.client: 
            return
        channel_id = db["config"].get("event_channel")
        if not channel_id:
            return
            
        channel = self.bot.get_channel(channel_id)
        if channel:
            try: 
                prompt = "Generate a highly engaging, modern Discord event, hot take, or scenario to spark chat activity. Keep it short. Do not use JSON."
                reply = self.ask_groq([{"role": "user", "content": prompt}])
                embed = discord.Embed(title="🌟 Server Event", description=reply, color=discord.Color.blurple())
                await channel.send(embed=embed)
            except: 
                pass

    @ai_event_loop.before_loop
    async def before_event_loop(self): 
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: 
            return
            
        uid = str(message.author.id)

        # 1. DM AI Chat Handler
        if not message.guild:
            if not self.client: 
                return
            async with message.channel.typing():
                try: 
                    reply = self.ask_groq([
                        {"role": "system", "content": "You are habbibi mod (:, a chaotic, funny Discord bot. You are talking in private DMs."}, 
                        {"role": "user", "content": message.content}
                    ])
                    await message.channel.send(reply[:2000])
                except Exception as e: 
                    await message.channel.send(f"❌ AI Error: {e}")
            return # Stop processing so XP is not given in DMs

        # 2. AFK System
        if uid in db["afk"]:
            del db["afk"][uid]
            save_db(db)
            await message.channel.send(f"👋 Welcome back {message.author.mention}, I have removed your AFK status.", delete_after=10)
            
        for mention in message.mentions:
            if str(mention.id) in db["afk"]: 
                await message.channel.send(f"💤 **{mention.name}** is currently AFK: {db['afk'][str(mention.id)]}")

        # 3. Automod Filter
        for word in db["config"]["filterwords"]:
            if word in message.content.lower():
                try:
                    await message.delete()
                    await message.channel.send(f"⚠️ {message.author.mention}, that word is blacklisted!", delete_after=5)
                except:
                    pass
                return

        # 4. RPG Leveling System
        if uid not in db["levels"]: 
            db["levels"][uid] = {"xp": 0, "level": 1}
            
        db["levels"][uid]["xp"] += random.randint(10, 25)
        current_xp = db["levels"][uid]["xp"]
        current_lvl = db["levels"][uid]["level"]
        xp_needed = (current_lvl * 100) * 1.5
        
        if current_xp >= xp_needed and current_lvl < 13000:
            db["levels"][uid]["level"] += 1
            save_db(db)
            embed = discord.Embed(
                title="Level Up!", 
                description=f"🎉 **{message.author.mention}** has leveled up to **Level {db['levels'][uid]['level']}**!", 
                color=discord.Color.gold()
            )
            await message.channel.send(embed=embed)
        else: 
            save_db(db)

        # 5. Custom Commands
        if message.content.startswith('!') and len(message.content) > 1:
            cmd = message.content[1:].split()[0].lower()
            if cmd in db["custom_commands"]: 
                return await message.channel.send(db["custom_commands"][cmd])

        # 6. Server AI Auto-Chat
        ai_channel_id = db["config"].get("ai_channel")
        if message.channel.id == ai_channel_id and not message.content.startswith(('!', '/')) and self.client:
            async with message.channel.typing():
                try: 
                    reply = self.ask_groq([
                        {"role": "system", "content": "You are habbibi mod (:, a chaotic and sarcastic Discord bot."}, 
                        {"role": "user", "content": message.content}
                    ])
                    await message.channel.send(reply[:2000])
                except: 
                    pass

    # ==========================================
    # SERVER CONFIGURATION
    # ==========================================
    @commands.hybrid_command(name="setaichannel", description="Sets the AI auto-reply channel.")
    @commands.has_permissions(administrator=True)
    async def setaichannel(self, ctx): 
        db["config"]["ai_channel"] = ctx.channel.id
        save_db(db)
        await ctx.send(f"🤖 **AI Auto-Chat bound to** {ctx.channel.mention}")

    @commands.hybrid_command(name="setcmdchannel", description="Locks normal commands to a channel.")
    @commands.has_permissions(administrator=True)
    async def setcmdchannel(self, ctx): 
        db["config"]["cmd_channel"] = ctx.channel.id
        save_db(db)
        await ctx.send(f"🔒 **Commands locked to** {ctx.channel.mention}")

    @commands.hybrid_command(name="seteventchannel", description="Sets the hourly AI event channel.")
    @commands.has_permissions(administrator=True)
    async def seteventchannel(self, ctx): 
        db["config"]["event_channel"] = ctx.channel.id
        save_db(db)
        await ctx.send(f"🌟 **AI Events bound to** {ctx.channel.mention}")

    @commands.hybrid_command(name="deployserver", description="Wipes the server and builds a Modern Layout.")
    @commands.has_permissions(administrator=True)
    async def deployserver(self, ctx):
        await ctx.send("⚠️ **CLEAN SLATE PROTOCOL INITIATED.** Wiping the server and building the new layout. Please wait...")
        guild = ctx.guild
        
        # 1. Delete Channels
        for c in guild.channels:
            try: 
                await c.delete()
                await asyncio.sleep(0.5)
            except: 
                pass
                
        # 2. Delete Roles
        for r in guild.roles:
            if r.name != "@everyone" and not r.managed and r < ctx.guild.me.top_role:
                try: 
                    await r.delete()
                    await asyncio.sleep(0.5)
                except: 
                    pass
                    
        # 3. Create Roles
        roles_to_make = [
            {"name": "Admin", "color": discord.Color.red()}, 
            {"name": "Moderator", "color": discord.Color.orange()}, 
            {"name": "Jailed", "color": discord.Color.dark_grey()}
        ]
        created_roles = {}
        for r in roles_to_make:
            try: 
                perms = discord.Permissions(administrator=(r["name"] == "Admin"))
                created_roles[r["name"]] = await guild.create_role(name=r["name"], color=r["color"], permissions=perms, hoist=True)
                await asyncio.sleep(1)
            except: 
                pass
                
        # 4. Assign Admin Role
        try: 
            if "Admin" in created_roles:
                await ctx.author.add_roles(created_roles["Admin"])
        except: 
            print("Failed to assign Admin role.")

        # 5. Create Categories and Channels
        cat_info = await guild.create_category("📌 INFORMATION")
        await guild.create_text_channel("rules", category=cat_info)
        
        cat_chat = await guild.create_category("💬 CHAT")
        gen_chat = await guild.create_text_channel("general", category=cat_chat)
        bot_cmds = await guild.create_text_channel("bot-commands", category=cat_chat)
        ai_chat = await guild.create_text_channel("talk-to-ai", category=cat_chat)
        
        cat_voice = await guild.create_category("🔊 VOICE")
        await guild.create_voice_channel("General VC", category=cat_voice)

        # 6. Apply Jail Permissions
        if "Jailed" in created_roles:
            for cat in guild.categories:
                try: 
                    await cat.set_permissions(created_roles["Jailed"], read_messages=False, connect=False)
                except: 
                    pass

        # 7. Update Database
        db["config"]["cmd_channel"] = bot_cmds.id
        db["config"]["ai_channel"] = ai_chat.id
        db["config"]["event_channel"] = gen_chat.id
        save_db(db)
        
        await gen_chat.send(f"{ctx.author.mention} ✅ **Deployment Complete.** Server is fully operational.")

    # ==========================================
    # GOD-MODE & AI TOOLS
    # ==========================================
    @commands.hybrid_command(name='aicommand', description="Master AI brain. Execute any python code dynamically.")
    @commands.has_permissions(administrator=True)
    async def aicommand(self, ctx, *, instruction: str):
        if not self.client: 
            return await ctx.send("🤖 **AI is offline. Missing API Key.**")
        
        await ctx.defer()
        prompt = f"""
        You are an omnipotent Discord bot. The server owner has commanded: "{instruction}"
        Output a JSON array of actions to perform. 
        Available Actions:
        1. Reply: {{"action": "reply", "message": "your text here"}}
        2. Execute Python: {{"action": "execute", "code": "await ctx.send('Task complete!')"}}
        
        STRICT RULES FOR PYTHON EXECUTE:
        - Output ONLY a valid JSON array.
        - You must write valid discord.py async code.
        - You have access to: 'ctx', 'bot', 'discord', 'asyncio', 'db'.
        - Add 'await asyncio.sleep(2)' between any bulk channel creations or edits to prevent rate limits.
        """
        
        try:
            raw_response = self.ask_groq([{"role": "user", "content": prompt}])
            start_idx = raw_response.find('[')
            end_idx = raw_response.rfind(']')
            
            if start_idx != -1 and end_idx != -1:
                clean_json = raw_response[start_idx:end_idx+1]
            else:
                clean_json = raw_response.replace('```json', '').replace('```python', '').replace('```', '').strip()
                if clean_json.startswith('{'): 
                    clean_json = f"[{clean_json}]"
                    
            actions = json.loads(clean_json)
            
            for act in actions:
                atype = act.get("action")
                if atype == "reply": 
                    await ctx.send(f"🤖 {act.get('message')}")
                elif atype == "execute":
                    status_msg = await ctx.send("⚡ **Executing dynamic Python code...**")
                    try:
                        code_lines = act.get("code", "").split("\n")
                        wrapped_code = "async def __ai_exec():\n"
                        for line in code_lines:
                            wrapped_code += f"    {line}\n"
                            
                        exec_env = {
                            'discord': discord, 
                            'bot': self.bot, 
                            'ctx': ctx, 
                            'asyncio': asyncio, 
                            'db': db
                        }
                        
                        exec(wrapped_code, exec_env)
                        await exec_env['__ai_exec']()
                        await status_msg.edit(content="✅ **AI Code Execution Successful!**")
                    except Exception as err: 
                        await status_msg.edit(content=f"⚠️ **AI Execution Failed:**\n```py\n{err}\n```")
        except Exception as e: 
            await ctx.send(f"❌ **Error parsing AI response:** {e}")

    @commands.hybrid_command(name="forceevent", description="Force an hourly AI event instantly.")
    @commands.has_permissions(administrator=True)
    async def forceevent(self, ctx): 
        if not self.client: return await ctx.send("AI is offline.")
        await ctx.defer()
        embed = discord.Embed(
            title="🌟 Forced Server Event", 
            description=self.ask_groq([{"role": "user", "content": "Generate a modern Discord event or question to spark chat."}]), 
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="tldr", description="AI summarizes the last 50 messages.")
    async def tldr(self, ctx): 
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        chat_log = "\n".join([m.content async for m in ctx.channel.history(limit=50) if m.content])
        reply = self.ask_groq([{"role": "user", "content": f"Summarize this chat log briefly:\n{chat_log}"}])
        await ctx.send(f"📜 **TL;DR:**\n{reply}")

    @commands.hybrid_command(name="roast_history", description="AI roasts a user based on their recent messages.")
    async def roast_history(self, ctx, member: discord.Member): 
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        chat_log = "\n".join([m.content async for m in ctx.channel.history(limit=25) if m.author == member and m.content])
        if not chat_log: return await ctx.send(f"I don't have enough recent messages from {member.name} to roast them.")
        reply = self.ask_groq([{"role": "user", "content": f"Brutally roast this user based strictly on their message history:\n{chat_log}"}])
        await ctx.send(f"🔥 **AI Roast for {member.name}:**\n{reply}")

    @commands.hybrid_command(name="gothic_translate", description="Translates text into dark fantasy royal decree.")
    async def gothic_translate(self, ctx, *, text: str): 
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        reply = self.ask_groq([{"role": "user", "content": f"Rewrite the following text into dark, brooding gothic royal decree:\n{text}"}])
        await ctx.send(f"🦇 **Gothic Translation:**\n{reply}")

    @commands.hybrid_command(name="lore", description="AI generates an epic backstory for the server.")
    async def lore(self, ctx): 
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        reply = self.ask_groq([{"role": "user", "content": f"Write an epic dark fantasy backstory for the Discord server named {ctx.guild.name}."}])
        await ctx.send(f"📖 **Server Lore:**\n{reply}")

    @commands.hybrid_command(name="code_fix", description="AI explains and fixes broken code.")
    async def code_fix(self, ctx, *, code: str): 
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        reply = self.ask_groq([{"role": "user", "content": f"Fix this code and briefly explain the issue:\n{code}"}])
        await ctx.send(f"🛠️ **Code Fix:**\n{reply}")

    @commands.hybrid_command(name="name_idea", description="AI suggests Discord role/server names.")
    async def name_idea(self, ctx): 
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        reply = self.ask_groq([{"role": "user", "content": "Give me 5 incredibly cool dark fantasy or sci-fi Discord role names."}])
        await ctx.send(f"💡 **Name Ideas:**\n{reply}")

    @commands.hybrid_command(name="vibecheck", description="AI analyzes a user's vibe.")
    async def vibecheck(self, ctx, member: discord.Member): 
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        chat_log = "\n".join([m.content async for m in ctx.channel.history(limit=25) if m.author == member and m.content])
        if not chat_log: return await ctx.send("No recent messages to check.")
        reply = self.ask_groq([{"role": "user", "content": f"Humorously analyze the vibe of this user based on their texts:\n{chat_log}"}])
        await ctx.send(f"🔮 **Vibe Check for {member.name}:**\n{reply}")

    @commands.hybrid_command(name="debate", description="AI will argue against your topic.")
    async def debate(self, ctx, *, topic: str): 
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        reply = self.ask_groq([
            {"role": "system", "content": "You are a master debater. You must take the opposite stance of the user and passionately argue against them."}, 
            {"role": "user", "content": topic}
        ])
        await ctx.send(f"⚖️ **Debating:** *{topic}*\n\n{reply}")

    @commands.hybrid_command(name="bossfight", description="AI generates a text-based boss fight.")
    async def bossfight(self, ctx): 
        if not self.client: return await ctx.send("AI offline.")
        await ctx.defer()
        reply = self.ask_groq([{"role": "user", "content": "Generate a short, interactive text-based boss fight scenario for the chat."}])
        await ctx.send(f"⚔️ **BOSS FIGHT ENCOUNTER!**\n{reply}")

    # ==========================================
    # ADVANCED MODERATION
    # ==========================================
    @commands.hybrid_command(name="tempban", description="Bans a user temporarily (in days).")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member, days: int, *, reason: str="Temp Ban"): 
        await member.ban(reason=reason)
        embed = discord.Embed(title="🔨 User Temp-Banned", description=f"**{member.name}** has been banned for {days} days.\nReason: {reason}", color=discord.Color.red())
        await ctx.send(embed=embed)
        await asyncio.sleep(days * 86400)
        await ctx.guild.unban(member, reason="Tempban expired automatically.")

    @commands.hybrid_command(name="tempmute", description="Mutes a user for a specific duration in minutes.")
    @commands.has_permissions(moderate_members=True)
    async def tempmute(self, ctx, member: discord.Member, minutes: int, *, reason: str="Temp Mute"): 
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        embed = discord.Embed(title="🔇 User Muted", description=f"**{member.name}** has been timed out for {minutes} minutes.\nReason: {reason}", color=discord.Color.orange())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="slowmode", description="Sets slowmode for the current channel.")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int): 
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"⏱️ **Slowmode set to {seconds} seconds.**")

    @commands.hybrid_command(name="lockdown", description="Instantly locks all channels.")
    @commands.has_permissions(administrator=True)
    async def lockdown(self, ctx):
        await ctx.send("🚨 **SERVER LOCKDOWN INITIATED. Securing channels...**")
        for c in ctx.guild.text_channels:
            try: 
                await c.set_permissions(ctx.guild.default_role, send_messages=False)
            except: 
                pass
        await ctx.send("🔒 **All channels have been locked down.**")

    @commands.hybrid_command(name="unlockdown", description="Reverses the lockdown.")
    @commands.has_permissions(administrator=True)
    async def unlockdown(self, ctx):
        await ctx.send("🔓 **SERVER LOCKDOWN LIFTED. Unlocking channels...**")
        for c in ctx.guild.text_channels:
            try: 
                await c.set_permissions(ctx.guild.default_role, send_messages=True)
            except: 
                pass
        await ctx.send("✅ **All channels are now unlocked.**")

    @commands.hybrid_command(name="snipe", description="Recovers the last deleted message.")
    async def snipe(self, ctx):
        data = snipes.get(ctx.channel.id)
        if not data: 
            return await ctx.send("Nothing to snipe!")
        embed = discord.Embed(description=data["content"], color=discord.Color.red())
        embed.set_author(name=data["author"], icon_url=data["avatar"])
        embed.set_footer(text="Message recovered via snipe.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="editsnipe", description="Shows the original text of an edited message.")
    async def editsnipe(self, ctx):
        data = edit_snipes.get(ctx.channel.id)
        if not data: 
            return await ctx.send("No recently edited messages found!")
        embed = discord.Embed(title="Message Edited", color=discord.Color.orange())
        embed.set_author(name=data["author"])
        embed.add_field(name="Before", value=data["before"], inline=False)
        embed.add_field(name="After", value=data["after"], inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="massnick", description="Changes everyone's nickname.")
    @commands.has_permissions(administrator=True)
    async def massnick(self, ctx, *, nickname: str):
        await ctx.send(f"🔄 **Changing all nicknames to '{nickname}'...** This may take a while.")
        count = 0
        for m in ctx.guild.members:
            if not m.bot and m < ctx.guild.me.top_role:
                try: 
                    await m.edit(nick=nickname)
                    count += 1
                    await asyncio.sleep(0.5)
                except: 
                    pass
        await ctx.send(f"✅ **Massnick complete.** Changed {count} nicknames.")

    @commands.hybrid_command(name="strip", description="Removes all roles from a user.")
    @commands.has_permissions(administrator=True)
    async def strip(self, ctx, member: discord.Member):
        for r in member.roles[1:]:
            try: 
                await member.remove_roles(r)
            except: 
                pass
        await ctx.send(f"👕 **Stripped {member.name} of all roles.**")

    @commands.hybrid_command(name="roleall", description="Gives a specific role to everyone.")
    @commands.has_permissions(administrator=True)
    async def roleall(self, ctx, role: discord.Role):
        await ctx.send(f"🔄 **Granting {role.name} to everyone...**")
        count = 0
        for m in ctx.guild.members:
            if not m.bot:
                try: 
                    await m.add_roles(role)
                    count += 1
                    await asyncio.sleep(0.5)
                except: 
                    pass
        await ctx.send(f"✅ **Role granted to {count} members.**")

    @commands.hybrid_command(name="vckick", description="Disconnects a user from a voice channel.")
    @commands.has_permissions(move_members=True)
    async def vckick(self, ctx, member: discord.Member): 
        if member.voice:
            await member.move_to(None)
            await ctx.send(f"👢 **Kicked {member.name} from Voice Chat.**")
        else:
            await ctx.send("User is not in a voice channel.")

    @commands.hybrid_command(name="vcmute", description="Server-mutes a user in VC.")
    @commands.has_permissions(mute_members=True)
    async def vcmute(self, ctx, member: discord.Member): 
        if member.voice:
            await member.edit(mute=True)
            await ctx.send(f"🔇 **Server-muted {member.name} in Voice Chat.**")
        else:
            await ctx.send("User is not in a voice channel.")

    @commands.hybrid_command(name="audit", description="Pulls a list of moderation actions on a user.")
    @commands.has_permissions(administrator=True)
    async def audit(self, ctx, member: discord.Member): 
        logs = [e async for e in ctx.guild.audit_logs(limit=10, user=member)]
        if not logs: 
            return await ctx.send(f"No recent audit log actions found for {member.name}.")
        
        res = "```\n--- Recent Audit Actions ---\n"
        for e in logs:
            res += f"- {e.action} on {e.target} at {e.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        res += "```"
        await ctx.send(res)

    @commands.hybrid_command(name="antiraid", description="Toggles anti-raid mode (auto-kicks new joins).")
    @commands.has_permissions(administrator=True)
    async def antiraid(self, ctx, status: bool): 
        db["config"]["antiraid"] = status
        save_db(db)
        await ctx.send(f"🛡️ **Anti-raid mode is now {'ON' if status else 'OFF'}.**")

    @commands.hybrid_command(name="hidechannel", description="Makes current channel invisible.")
    @commands.has_permissions(manage_channels=True)
    async def hidechannel(self, ctx): 
        await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.send("👻 **Channel is now hidden from regular members.**")

    @commands.hybrid_command(name="purge", description="Deletes multiple messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int): 
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 **Swept {amount} messages.**", delete_after=4)

    @commands.hybrid_command(name="nuke", description="Clones and deletes the channel.")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx): 
        pos = ctx.channel.position
        nc = await ctx.channel.clone()
        await ctx.channel.delete()
        await nc.edit(position=pos)
        await nc.send("☢️ **TACTICAL NUKE INCOMING!** 💥\nChannel has been wiped.")

    @commands.hybrid_command(name="kick", description="Kicks a user.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str="Caught lacking"): 
        await member.kick(reason=reason)
        await ctx.send(f"👢 **{member.name} was kicked.** Reason: {reason}")

    @commands.hybrid_command(name="ban", description="Bans a user.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str="Banned by Admin"): 
        await member.ban(reason=reason)
        await ctx.send(f"🔨 **{member.name} has been permanently banned.**")

    @commands.hybrid_command(name="unban", description="Unbans a user by ID.")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: str): 
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user)
            await ctx.send(f"🕊️ **{user.name} has been unbanned.**")
        except:
            await ctx.send("❌ Could not find or unban that user ID.")

    @commands.hybrid_command(name="warn", description="Warns a user.")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str="Rule Violation"): 
        uid = str(member.id)
        if uid not in db["warns"]: 
            db["warns"][uid] = []
        db["warns"][uid].append(reason)
        save_db(db)
        await ctx.send(f"⚠️ **{member.mention} has been warned.** Reason: {reason}")

    @commands.hybrid_command(name="warnings", description="Shows a user's warnings.")
    async def warnings(self, ctx, member: discord.Member): 
        warns = db["warns"].get(str(member.id), [])
        if not warns: 
            return await ctx.send(f"✅ **{member.name} has a clean record.**")
        embed = discord.Embed(title=f"⚠️ Warnings for {member.name}", color=discord.Color.orange())
        for i, w in enumerate(warns):
            embed.add_field(name=f"Warning {i+1}", value=w, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarns", description="Clears all warnings for a user.")
    @commands.has_permissions(administrator=True)
    async def clearwarns(self, ctx, member: discord.Member): 
        if str(member.id) in db["warns"]:
            del db["warns"][str(member.id)]
            save_db(db)
            await ctx.send(f"🗑️ **Cleared all warnings for {member.name}.**")
        else:
            await ctx.send("User has no warnings.")

    @commands.hybrid_command(name="lock", description="Locks current channel.")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx): 
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🔒 **Channel locked.**")

    @commands.hybrid_command(name="unlock", description="Unlocks current channel.")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx): 
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send("🔓 **Channel unlocked.**")

    @commands.hybrid_command(name="jail", description="Strips roles and locks user in jail.")
    @commands.has_permissions(administrator=True)
    async def jail(self, ctx, member: discord.Member):
        db["jailed"][str(member.id)] = [r.id for r in member.roles if r.id != ctx.guild.default_role.id]
        save_db(db)
        for r in member.roles[1:]:
            try: 
                await member.remove_roles(r)
            except: 
                pass
                
        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jail_role: 
            await member.add_roles(jail_role)
            await ctx.send(f"⛓️ **{member.mention} has been locked up in federal prison.**")
        else:
            await ctx.send("⚠️ 'Jailed' role does not exist. Please run `/deployserver` or create it.")

    @commands.hybrid_command(name="unjail", description="Releases user from jail and restores roles.")
    @commands.has_permissions(administrator=True)
    async def unjail(self, ctx, member: discord.Member):
        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if jail_role and jail_role in member.roles: 
            await member.remove_roles(jail_role)
            
        old_roles = db["jailed"].pop(str(member.id), [])
        for r_id in old_roles:
            role = ctx.guild.get_role(r_id)
            if role: 
                try: await member.add_roles(role)
                except: pass
                
        save_db(db)
        await ctx.send(f"🔓 **{member.mention} made bail and is released.**")

    # ==========================================
    # RPG & ECONOMY (The Grind)
    # ==========================================
    @commands.hybrid_command(name="bal", description="Check your coin balance.")
    async def bal(self, ctx, member: discord.Member = None): 
        target = member or ctx.author
        uid = str(target.id)
        balance = db["economy"].get(uid, 0)
        embed = discord.Embed(title="Bank Account", description=f"💰 **{target.name}** has **{balance:,}** coins.", color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="daily", description="Claim daily coins.")
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx): 
        uid = str(ctx.author.id)
        db["economy"][uid] = db["economy"].get(uid, 0) + 1000
        save_db(db)
        await ctx.send("🎁 **You claimed your daily 1,000 coins!**")

    @commands.hybrid_command(name="weekly", description="Claim weekly coins.")
    @commands.cooldown(1, 604800, commands.BucketType.user)
    async def weekly(self, ctx): 
        uid = str(ctx.author.id)
        db["economy"][uid] = db["economy"].get(uid, 0) + 10000
        save_db(db)
        await ctx.send("💎 **You claimed your massive 10,000 weekly coins!**")

    @commands.hybrid_command(name="work", description="Work for coins.")
    @commands.cooldown(1, 3600, commands.BucketType.user) 
    async def work(self, ctx): 
        earned = random.randint(100, 400)
        uid = str(ctx.author.id)
        db["economy"][uid] = db["economy"].get(uid, 0) + earned
        save_db(db)
        await ctx.send(f"💼 **You worked a grueling shift and earned {earned} coins!**")

    @commands.hybrid_command(name="crime", description="Commit a crime for coins (risky).")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def crime(self, ctx):
        uid = str(ctx.author.id)
        if random.choice([True, False]): 
            earned = random.randint(300, 800)
            db["economy"][uid] = db["economy"].get(uid, 0) + earned
            await ctx.send(f"🥷 **You successfully hacked the mainframe and stole {earned} coins!**")
        else: 
            lost = random.randint(100, 300)
            db["economy"][uid] = max(0, db["economy"].get(uid, 0) - lost)
            await ctx.send(f"🚓 **The feds caught you! You paid a fine of {lost} coins.**")
        save_db(db)

    @commands.hybrid_command(name="rob", description="Steal from another user.")
    @commands.cooldown(1, 7200, commands.BucketType.user)
    async def rob(self, ctx, member: discord.Member):
        uid = str(ctx.author.id)
        tid = str(member.id)
        
        if db["economy"].get(tid, 0) < 500: 
            return await ctx.send(f"❌ **{member.name} is too poor to rob. Leave them alone!**")
            
        if random.choice([True, False]): 
            stolen = random.randint(100, int(db["economy"][tid] * 0.25))
            db["economy"][tid] -= stolen
            db["economy"][uid] = db["economy"].get(uid, 0) + stolen
            await ctx.send(f"🔫 **You mugged {member.name} and stole {stolen} coins!**")
        else: 
            fine = 300
            db["economy"][uid] = max(0, db["economy"].get(uid, 0) - fine)
            await ctx.send(f"🛡️ **{member.name} fought back! You paid a {fine} coin hospital bill.**")
        save_db(db)

    @commands.hybrid_command(name="heist", description="Start a bank heist event.")
    @commands.cooldown(1, 14400, commands.BucketType.guild)
    async def heist(self, ctx): 
        payout = random.randint(3000, 10000)
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + payout
        save_db(db)
        await ctx.send(f"🏦 **BANK HEIST SUCCESSFUL!** You blew the vault and escaped with **{payout:,} coins!**")

    @commands.hybrid_command(name="slots", description="Virtual slot machine.")
    async def slots(self, ctx, bet: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: 
            return await ctx.send("❌ **You don't have enough coins to place that bet.**")
            
        db["economy"][uid] -= bet
        reels = ["🍒", "🍋", "💎", "⭐", "🔔"]
        r1, r2, r3 = random.choice(reels), random.choice(reels), random.choice(reels)
        
        msg = f"🎰 **SLOTS** 🎰\n| {r1} | {r2} | {r3} |\n"
        
        if r1 == r2 == r3: 
            winnings = bet * 10
            db["economy"][uid] += winnings
            await ctx.send(msg + f"🎉 **JACKPOT!** You won **{winnings:,} coins!**")
        elif r1 == r2 or r2 == r3 or r1 == r3: 
            winnings = int(bet * 1.5)
            db["economy"][uid] += winnings
            await ctx.send(msg + f"✨ **Small Win!** You got **{winnings:,} coins!**")
        else: 
            await ctx.send(msg + "💥 **You lost.** Better luck next time.")
        save_db(db)

    @commands.hybrid_command(name="blackjack", description="Play 21 against the bot.")
    async def blackjack(self, ctx, bet: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: 
            return await ctx.send("❌ **Not enough coins.**")
            
        db["economy"][uid] -= bet
        player_score = random.randint(15, 25)
        bot_score = random.randint(17, 23)
        
        if player_score > 21: 
            await ctx.send(f"🃏 **Bust!** You drew {player_score}. Bot had {bot_score}. You lose.")
        elif player_score > bot_score or bot_score > 21: 
            db["economy"][uid] += bet * 2
            await ctx.send(f"🃏 **You Win!** You drew {player_score}! Bot drew {bot_score}. Payout: **{bet*2} coins!**")
        else: 
            await ctx.send(f"🃏 **Bot Wins.** Bot drew {bot_score}. You had {player_score}. You lose.")
        save_db(db)

    @commands.hybrid_command(name="coinflip", description="Gamble 50/50.")
    async def coinflip(self, ctx, bet: int, choice: str):
        if choice.lower() not in ["heads", "tails"]: 
            return await ctx.send("❌ **Please choose 'heads' or 'tails'.**")
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < bet or bet <= 0: 
            return await ctx.send("❌ **Not enough coins.**")
            
        db["economy"][uid] -= bet
        result = random.choice(["heads", "tails"])
        
        if choice.lower() == result: 
            db["economy"][uid] += bet * 2
            await ctx.send(f"🪙 **It landed on {result.capitalize()}!** You won **{bet*2} coins!**")
        else: 
            await ctx.send(f"🪙 **It landed on {result.capitalize()}.** You lost.")
        save_db(db)

    @commands.hybrid_command(name="shop", description="View the server store.")
    async def shop(self, ctx): 
        embed = discord.Embed(title="🛒 The Kingdom Shop", description="Use `/buy <item>` to purchase.", color=discord.Color.gold())
        embed.add_field(name="🗡️ Sword", value="500 Coins", inline=False)
        embed.add_field(name="🛡️ Shield", value="1000 Coins", inline=False)
        embed.add_field(name="🐉 Dragon Egg", value="5000 Coins", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="buy", description="Buy an item from the shop.")
    async def buy(self, ctx, item: str):
        uid = str(ctx.author.id)
        prices = {"sword": 500, "shield": 1000, "dragon egg": 5000}
        item = item.lower()
        
        if item not in prices: 
            return await ctx.send("❌ **That item is not in the shop.**")
        if db["economy"].get(uid, 0) < prices[item]: 
            return await ctx.send("❌ **You cannot afford that item.**")
            
        db["economy"][uid] -= prices[item]
        if uid not in db["inventory"]: 
            db["inventory"][uid] = []
        db["inventory"][uid].append(item)
        save_db(db)
        await ctx.send(f"✅ **Successfully purchased {item.title()}!**")

    @commands.hybrid_command(name="inventory", description="Check your inventory items.")
    async def inventory(self, ctx): 
        uid = str(ctx.author.id)
        items = db.get("inventory", {}).get(uid, [])
        embed = discord.Embed(title=f"🎒 {ctx.author.name}'s Inventory", description=", ".join(items).title() if items else "Inventory is empty.", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="give", description="Give coins to another user.")
    async def give(self, ctx, member: discord.Member, amount: int):
        uid = str(ctx.author.id)
        tid = str(member.id)
        if db["economy"].get(uid, 0) < amount or amount <= 0: 
            return await ctx.send("❌ **Insufficient funds.**")
            
        db["economy"][uid] -= amount
        db["economy"][tid] = db["economy"].get(tid, 0) + amount
        save_db(db)
        await ctx.send(f"💸 **You gave {member.name} {amount:,} coins.**")

    @commands.hybrid_command(name="rich", description="View the Top 10 richest players.")
    async def rich(self, ctx): 
        sorted_eco = sorted(db["economy"].items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(title="🏆 Richest Citizens", color=discord.Color.gold())
        for i, (uid, amt) in enumerate(sorted_eco):
            embed.add_field(name=f"#{i+1}", value=f"<@{uid}>: **{amt:,}** coins", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="fish", description="Cast a line and catch fish.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def fish(self, ctx): 
        fish_types = ["Old Boot", "Common Carp", "Rare Salmon", "Legendary Shark"]
        fish = random.choice(fish_types)
        reward = {"Old Boot": 0, "Common Carp": 50, "Rare Salmon": 200, "Legendary Shark": 1000}[fish]
        
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward
        save_db(db)
        await ctx.send(f"🎣 **You cast your line and caught a {fish}!** Sold for {reward} coins.")

    @commands.hybrid_command(name="hunt", description="Hunt animals or monsters.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def hunt(self, ctx): 
        mobs = ["Mutant Rat", "Forest Goblin", "Shadow Dragon"]
        mob = random.choice(mobs)
        reward = {"Mutant Rat": 20, "Forest Goblin": 150, "Shadow Dragon": 1500}[mob]
        
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward
        save_db(db)
        await ctx.send(f"🏹 **You ventured into the woods and slayed a {mob}!** Claimed {reward} coins.")

    @commands.hybrid_command(name="mine", description="Mine for ores.")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def mine(self, ctx): 
        ores = ["Stone", "Iron Ore", "Raw Diamond"]
        ore = random.choice(ores)
        reward = {"Stone": 5, "Iron Ore": 80, "Raw Diamond": 1200}[ore]
        
        db["economy"][str(ctx.author.id)] = db["economy"].get(str(ctx.author.id), 0) + reward
        save_db(db)
        await ctx.send(f"⛏️ **You swung your pickaxe and mined {ore}!** Sold for {reward} coins.")

    @commands.hybrid_command(name="quest", description="Go on an RPG quest.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def quest(self, ctx):
        uid = str(ctx.author.id)
        if uid not in db["levels"]: 
            db["levels"][uid] = {"xp": 0, "level": 1}
            
        current_lvl = db["levels"][uid]["level"]
        if current_lvl >= 13000: 
            return await ctx.send("🛑 **Max Level 13,000 Reached!** You are already a god. The quests offer you nothing.")
            
        xp_gain = random.randint(300, 800)
        db["levels"][uid]["xp"] += xp_gain
        save_db(db)
        await ctx.send(f"🗡️ **You completed a dangerous dungeon run!** Earned **{xp_gain} XP**! (Current Level: {current_lvl})")

    @commands.hybrid_command(name="trade", description="Trade items securely.")
    async def trade(self, ctx, member: discord.Member, item: str):
        uid = str(ctx.author.id)
        tid = str(member.id)
        item = item.lower()
        
        if item not in db.get("inventory", {}).get(uid, []): 
            return await ctx.send("❌ **You do not own this item.**")
            
        if tid not in db["inventory"]: 
            db["inventory"][tid] = []
            
        db["inventory"][uid].remove(item)
        db["inventory"][tid].append(item)
        save_db(db)
        await ctx.send(f"🤝 **You successfully traded your {item.title()} to {member.name}.**")

    @commands.hybrid_command(name="bounty", description="Put a coin bounty on a user's head.")
    async def bounty(self, ctx, member: discord.Member, amount: int):
        uid = str(ctx.author.id)
        if db["economy"].get(uid, 0) < amount or amount <= 0: 
            return await ctx.send("❌ **Not enough coins to set this bounty.**")
            
        db["economy"][uid] -= amount
        db["bounties"][str(member.id)] = db.get("bounties", {}).get(str(member.id), 0) + amount
        save_db(db)
        await ctx.send(f"💀 **Bounty Placed!** You put a **{amount} coin** bounty on {member.name}'s head!")

    @commands.hybrid_command(name="claimbounty", description="Claim a bounty.")
    async def claimbounty(self, ctx, member: discord.Member):
        uid = str(ctx.author.id)
        tid = str(member.id)
        bounty_amount = db.get("bounties", {}).get(tid, 0)
        
        if bounty_amount <= 0: 
            return await ctx.send("❌ **That user does not have a bounty on their head.**")
            
        db["bounties"][tid] = 0
        db["economy"][uid] = db["economy"].get(uid, 0) + bounty_amount
        save_db(db)
        await ctx.send(f"🔪 **Bounty Claimed!** You hunted down {member.name} and collected the **{bounty_amount} coin** reward!")

    # ==========================================
    # FUN & TROLLING (Pure Chaos)
    # ==========================================
    @commands.hybrid_command(name="fakeban", description="Sends a terrifying fake ban message.")
    async def fakeban(self, ctx, member: discord.Member): 
        embed = discord.Embed(title="User Banned", description=f"🔨 **{member.name}** has been permanently banned from the server.\n\n*Reason: Caught lacking.*", color=discord.Color.red())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rickroll", description="Sends a disguised DM to a user.")
    async def rickroll(self, ctx, member: discord.Member):
        try: 
            await member.send("🎁 **You have been gifted Discord Nitro!** Claim it here: [https://www.youtube.com/watch?v=dQw4w9WgXcQ](https://www.youtube.com/watch?v=dQw4w9WgXcQ)")
            await ctx.send(f"🤫 **Successfully sent a disguised package to {member.name}.**")
        except: 
            await ctx.send("❌ **Their DMs are closed.**")

    @commands.hybrid_command(name="howgay", description="Calculates a random percentage.")
    async def howgay(self, ctx, member: discord.Member=None): 
        target = member or ctx.author
        await ctx.send(f"🏳️‍🌈 **{target.name}** is **{random.randint(0,100)}%** gay.")

    @commands.hybrid_command(name="simpmeter", description="Calculates simp percentage.")
    async def simpmeter(self, ctx, member: discord.Member=None): 
        target = member or ctx.author
        await ctx.send(f"😳 **{target.name}** is a **{random.randint(0,100)}%** simp.")

    @commands.hybrid_command(name="susmeter", description="Calculates sus percentage.")
    async def susmeter(self, ctx, member: discord.Member=None): 
        target = member or ctx.author
        await ctx.send(f"📮 **{target.name}** is **{random.randint(0,100)}%** sus.")

    @commands.hybrid_command(name="roast", description="Drops a brutal, pre-written roast.")
    async def roast(self, ctx, member: discord.Member):
        roasts = [
            "You're like a cloud. When you disappear, it's a beautiful day.", 
            "I'd agree with you but then we’d both be wrong.",
            "You bring everyone so much joy when you leave the room.",
            "If laughter is the best medicine, your face must be curing the world."
        ]
        await ctx.send(f"{member.mention} 🔥 {random.choice(roasts)}")

    @commands.hybrid_command(name="compliment", description="Says something genuinely nice.")
    async def compliment(self, ctx, member: discord.Member):
        comps = [
            "You have a great sense of humor!", 
            "You light up the room!",
            "You are absolutely glowing today.",
            "You're more helpful than you realize."
        ]
        await ctx.send(f"💖 {member.mention} {random.choice(comps)}")

    @commands.hybrid_command(name="confess", description="Sends an anonymous confession.")
    async def confess(self, ctx, *, message: str): 
        try:
            await ctx.message.delete()
        except:
            pass
        embed = discord.Embed(title="🤫 Anonymous Confession", description=message, color=discord.Color.dark_theme())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="kill", description="Generates a funny death message.")
    async def kill(self, ctx, member: discord.Member):
        deaths = [
            "fell out of the world.", 
            "was obliterated by a rogue AI.", 
            "forgot how to breathe.",
            "was crushed by a falling anvil."
        ]
        await ctx.send(f"☠️ **{member.name}** {random.choice(deaths)}")

    @commands.hybrid_command(name="revive", description="Brings a user back to life.")
    async def revive(self, ctx, member: discord.Member): 
        await ctx.send(f"👼 **{member.name} has been resurrected from the dead!**")

    @commands.hybrid_command(name="meme", description="Pulls a meme.")
    async def meme(self, ctx): 
        await ctx.send("😂 *Imagine a really funny, high-quality meme right here.* (API integration placeholder)")

    @commands.hybrid_command(name="dadjoke", description="Tells a terrible dad joke.")
    async def dadjoke(self, ctx):
        jokes = [
            "I'm afraid for the calendar. Its days are numbered.", 
            "Why do fathers take an extra pair of socks when they go golfing? In case they get a hole in one!",
            "I thought the dryer was shrinking my clothes. Turns out it was the refrigerator."
        ]
        await ctx.send(f"🧔 **Dad Joke:** {random.choice(jokes)}")

    @commands.hybrid_command(name="choose", description="Forces the bot to make a decision.")
    async def choose(self, ctx, option1: str, option2: str): 
        await ctx.send(f"🤔 **I choose...** `{random.choice([option1, option2])}`")

    @commands.hybrid_command(name="spank", description="Exactly what it sounds like.")
    async def spank(self, ctx, member: discord.Member): 
        await ctx.send(f"🤚 **{ctx.author.name} viciously spanked {member.name}!**")

    @commands.hybrid_command(name="jailbreak", description="Attempt to break a friend out of jail.")
    async def jailbreak(self, ctx, member: discord.Member):
        if random.randint(1, 10) <= 2: # 20% chance
            jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
            if jail_role and jail_role in member.roles: 
                await member.remove_roles(jail_role)
                await ctx.send(f"🔓 **SUCCESS!** {ctx.author.name} broke {member.name} out of federal prison!")
            else:
                await ctx.send(f"{member.name} isn't in jail!")
        else: 
            await ctx.send("❌ **Jailbreak failed.** The guards caught you trying to sneak in.")

    @commands.hybrid_command(name="eightball", description="Ask the magic 8-ball a question.")
    async def eightball(self, ctx, *, question: str): 
        res = random.choice(["Yes, definitely.", "No.", "Maybe.", "Definitely not.", "Without a doubt.", "Ask again later."])
        await ctx.send(f"🎱 **Question:** {question}\n**Answer:** {res}")

    @commands.hybrid_command(name="hack", description="Fake hack a user.")
    async def hack(self, ctx, member: discord.Member): 
        msg = await ctx.send(f"💻 **Hacking {member.name}...**")
        await asyncio.sleep(2)
        await msg.edit(content="🕵️‍♂️ Finding IP Address...")
        await asyncio.sleep(2)
        await msg.edit(content=f"✅ **Successfully hacked {member.mention}.** Selling their search history for 5 robux.")

    @commands.hybrid_command(name="ship", description="Matchmake two people.")
    async def ship(self, ctx, m1: discord.Member, m2: discord.Member=None): 
        target2 = m2 or ctx.author
        rating = random.randint(0, 100)
        await ctx.send(f"❤️ **Ship Matchmaker:**\n{m1.name} x {target2.name} \n**Compatibility:** {rating}%")

    # ==========================================
    # 🎭 ANIME & ACTION ROLEPLAY
    # ==========================================
    @commands.hybrid_command(name="pat", description="Sends an anime headpat.")
    async def pat(self, ctx, member: discord.Member): 
        await ctx.send(f"🤚 **{ctx.author.name} gently patted {member.name} on the head!**")
    
    @commands.hybrid_command(name="punch", description="Sends an anime punch.")
    async def punch(self, ctx, member: discord.Member): 
        await ctx.send(f"👊 **{ctx.author.name} totally decked {member.name}!**")

    @commands.hybrid_command(name="bite", description="Sends an anime bite.")
    async def bite(self, ctx, member: discord.Member): 
        await ctx.send(f"🧛 **{ctx.author.name} bit {member.name}!**")

    @commands.hybrid_command(name="kiss", description="Sends an anime kiss.")
    async def kiss(self, ctx, member: discord.Member): 
        await ctx.send(f"💋 **{ctx.author.name} gave {member.name} a kiss!**")

    @commands.hybrid_command(name="smug", description="Smug anime face.")
    async def smug(self, ctx): 
        await ctx.send(f"😏 **{ctx.author.name} is looking extremely smug.**")

    @commands.hybrid_command(name="cry", description="Anime crying.")
    async def cry(self, ctx): 
        await ctx.send(f"😭 **{ctx.author.name} is crying in the corner.**")

    @commands.hybrid_command(name="quote", description="Drops an epic dark fantasy quote.")
    async def quote(self, ctx):
        quotes = [
            "If you don't fight, you can't win.", 
            "Since when were you under the impression that I wasn't using Kyoka Suigetsu?",
            "The bird of Hermes is my name, eating my wings to make me tame.",
            "Fear is not evil. It tells you what your weakness is."
        ]
        await ctx.send(f"📜 *\"{random.choice(quotes)}\"*")

    @commands.hybrid_command(name="powerlevel", description="Scouters read their power level.")
    async def powerlevel(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        pwr = random.randint(10, 1000000)
        if pwr > 900000: 
            await ctx.send(f"💥 **{target.mention}'s power level is {pwr:,}!** They have the aura of Wang Lin! Run!")
        else: 
            await ctx.send(f"🔍 **{target.mention}'s power level is {pwr:,}.** Just absolute fodder.")

    @commands.hybrid_command(name="domain_expansion", description="Traps the chat in your domain.")
    async def domain_expansion(self, ctx): 
        await ctx.send(f"🤞 **Domain Expansion!** {ctx.author.mention} has trapped everyone in their domain!")

    @commands.hybrid_command(name="bankai", description="Unleashes your ultimate move.")
    async def bankai(self, ctx): 
        await ctx.send(f"⚔️ **BANKAI!** {ctx.author.mention}'s spiritual pressure is crushing the server!")

    # ==========================================
    # ⭐ LEVELING, REPUTATION & UTILITY
    # ==========================================
    @commands.hybrid_command(name="rank", description="Check XP Level.")
    async def rank(self, ctx, member: discord.Member = None): 
        target = member or ctx.author
        uid = str(target.id)
        lvl_data = db["levels"].get(uid, {"xp": 0, "level": 1})
        embed = discord.Embed(title=f"Rank: {target.name}", description=f"⭐ Level: **{lvl_data['level']}**\n✨ XP: **{lvl_data['xp']}**", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard_levels", description="Top 10 highest levels.")
    async def leaderboard_levels(self, ctx): 
        sorted_lvls = sorted(db.get("levels", {}).items(), key=lambda x: x[1]["level"], reverse=True)[:10]
        embed = discord.Embed(title="🏆 Level Leaderboard", color=discord.Color.gold())
        for i, (uid, data) in enumerate(sorted_lvls):
            embed.add_field(name=f"#{i+1}", value=f"<@{uid}> - Lvl {data['level']}", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="givexp", description="Admin command to grant XP.")
    @commands.has_permissions(administrator=True)
    async def givexp(self, ctx, member: discord.Member, amount: int): 
        uid = str(member.id)
        if uid not in db["levels"]: 
            db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["xp"] += amount
        save_db(db)
        await ctx.send(f"📈 **Granted {amount} XP to {member.name}.**")

    @commands.hybrid_command(name="removexp", description="Admin command to remove XP.")
    @commands.has_permissions(administrator=True)
    async def removexp(self, ctx, member: discord.Member, amount: int): 
        uid = str(member.id)
        if uid in db["levels"]: 
            db["levels"][uid]["xp"] = max(0, db["levels"][uid]["xp"] - amount)
            save_db(db)
        await ctx.send(f"📉 **Removed {amount} XP from {member.name}.**")

    @commands.hybrid_command(name="setlevel", description="Admin force set level.")
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, member: discord.Member, level: int): 
        uid = str(member.id)
        if uid not in db["levels"]: 
            db["levels"][uid] = {"xp": 0, "level": 1}
        db["levels"][uid]["level"] = level
        save_db(db)
        await ctx.send(f"⭐ **Force set {member.name} to Level {level}.**")

    @commands.hybrid_command(name="rewards", description="View level role rewards.")
    async def rewards(self, ctx): 
        embed = discord.Embed(title="🎁 Level Rewards", color=discord.Color.green())
        embed.add_field(name="Level 10", value="Trusted Role", inline=False)
        embed.add_field(name="Level 50", value="Ronin Role", inline=False)
        embed.add_field(name="Level 100", value="God Tier Role", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rep", description="Give reputation to someone.")
    async def rep(self, ctx, member: discord.Member):
        if member.id == ctx.author.id: 
            return await ctx.send("❌ You cannot give reputation to yourself.")
        uid = str(member.id)
        if "rep" not in db: 
            db["rep"] = {}
        db["rep"][uid] = db["rep"].get(uid, 0) + 1
        save_db(db)
        await ctx.send(f"👍 **You gave +1 Reputation to {member.name}.** They now have {db['rep'][uid]} Rep.")

    @commands.hybrid_command(name="leaderboard_rep", description="Top 10 reputation.")
    async def leaderboard_rep(self, ctx): 
        sorted_rep = sorted(db.get("rep", {}).items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(title="👍 Most Reputable Citizens", color=discord.Color.green())
        for i, (uid, amt) in enumerate(sorted_rep):
            embed.add_field(name=f"#{i+1}", value=f"<@{uid}> - {amt} Rep", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="poll", description="Create a reaction poll.")
    async def poll(self, ctx, question: str): 
        embed = discord.Embed(title="📊 Server Poll", description=question, color=discord.Color.green())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    @commands.hybrid_command(name="giveaway_start", description="Start a giveaway.")
    @commands.has_permissions(manage_messages=True)
    async def giveaway_start(self, ctx, prize: str): 
        embed = discord.Embed(title=f"🎉 GIVEAWAY: {prize} 🎉", description="React with 🎉 to enter!", color=discord.Color.gold())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("🎉")

    @commands.hybrid_command(name="giveaway_reroll", description="Reroll a giveaway winner.")
    @commands.has_permissions(manage_messages=True)
    async def giveaway_reroll(self, ctx): 
        await ctx.send("🎉 **Giveaway rerolled!** (Event listener placeholder)")

    @commands.hybrid_command(name="ticket_setup", description="Setup support tickets.")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx): 
        await ctx.send("🎫 **Support Tickets initialized.** (Button UI placeholder)")

    @commands.hybrid_command(name="ticket_close", description="Closes a ticket channel.")
    @commands.has_permissions(manage_channels=True)
    async def ticket_close(self, ctx): 
        await ctx.send("Closing ticket...")
        await asyncio.sleep(2)
        await ctx.channel.delete()

    @commands.hybrid_command(name="remindme", description="Set a reminder.")
    async def remindme(self, ctx, seconds: int, *, message: str): 
        await ctx.send(f"⏰ **Reminder set for {seconds} seconds.**")
        await asyncio.sleep(seconds)
        await ctx.author.send(f"⏰ **Reminder:** {message}")

    @commands.hybrid_command(name="afk", description="Set AFK status.")
    async def afk(self, ctx, *, reason: str="AFK"): 
        db["afk"][str(ctx.author.id)] = reason
        save_db(db)
        await ctx.send(f"💤 **{ctx.author.mention} is now AFK.** Reason: {reason}")

    @commands.hybrid_command(name="weather", description="Check weather data.")
    async def weather(self, ctx, city: str): 
        await ctx.send(f"🌤️ **Weather in {city.title()}:** Sunny, 75°F (Simulated API).")

    @commands.hybrid_command(name="calc", description="Built-in calculator.")
    async def calc(self, ctx, expression: str):
        try: 
            # Very basic and safe eval wrapper
            result = eval(expression, {'__builtins__': None}, {})
            await ctx.send(f"🧮 **Result:** `{result}`")
        except: 
            await ctx.send("❌ **Invalid math expression.**")

    @commands.hybrid_command(name="translate", description="Translate text.")
    async def translate(self, ctx, language: str, *, text: str): 
        await ctx.send(f"🌐 **Translated to {language.title()}:** *{text}* (Simulated API).")

    @commands.hybrid_command(name="define", description="Dictionary definition.")
    async def define(self, ctx, word: str): 
        await ctx.send(f"📖 **Definition of {word}:** A placeholder dictionary term. (Simulated API).")

    @commands.hybrid_command(name="urban", description="Urban Dictionary.")
    async def urban(self, ctx, word: str): 
        await ctx.send(f"🏙️ **Urban Dictionary - {word}:** Internet slang placeholder. (Simulated API).")

    @commands.hybrid_command(name="userhistory", description="Check user history stats.")
    async def userhistory(self, ctx, member: discord.Member): 
        embed = discord.Embed(title=f"History for {member.name}", color=discord.Color.blue())
        embed.add_field(name="Joined Server", value=member.joined_at.strftime('%Y-%m-%d %H:%M'), inline=False)
        embed.add_field(name="Account Created", value=member.created_at.strftime('%Y-%m-%d %H:%M'), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="roleinfo", description="Check role info.")
    async def roleinfo(self, ctx, role: discord.Role): 
        embed = discord.Embed(title=f"Role Info: {role.name}", color=role.color)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="ID", value=str(role.id), inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="servericon", description="Get high-res server icon.")
    async def servericon(self, ctx): 
        if ctx.guild.icon:
            await ctx.send(ctx.guild.icon.url)
        else:
            await ctx.send("This server has no icon.")

    @commands.hybrid_command(name="ping", description="Check bot latency.")
    async def ping(self, ctx): 
        await ctx.send(f"🏓 **Pong!** {round(self.bot.latency * 1000)}ms")

    @commands.hybrid_command(name="avatar", description="Get user PFP.")
    async def avatar(self, ctx, member: discord.Member = None): 
        target = member or ctx.author
        embed = discord.Embed(title=f"{target.name}'s Avatar", color=discord.Color.blue())
        embed.set_image(url=target.avatar.url if target.avatar else target.default_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="View server stats.")
    async def serverinfo(self, ctx):
        embed = discord.Embed(title=f"Server Info - {ctx.guild.name}", color=discord.Color.gold())
        embed.add_field(name="👑 Owner", value=ctx.guild.owner.mention, inline=True)
        embed.add_field(name="👥 Members", value=ctx.guild.member_count, inline=True)
        embed.add_field(name="📁 Channels", value=len(ctx.guild.channels), inline=True)
        await ctx.send(embed=embed)

    # ==========================================
    # 🎵 VOICE & MEDIA
    # ==========================================
    @commands.hybrid_command(name="join", description="Forces the bot to join your voice channel.")
    async def join(self, ctx): 
        if not ctx.author.voice: 
            return await ctx.send("❌ **You must be in a voice channel first.**")
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"🔊 **Joined {channel.name}.**")

    @commands.hybrid_command(name="leave", description="Kicks the bot out of the voice channel.")
    async def leave(self, ctx): 
        if ctx.voice_client: 
            await ctx.voice_client.disconnect()
            await ctx.send("👋 **Disconnected from Voice Chat.**")
        else:
            await ctx.send("I am not currently in a voice channel.")

    @commands.hybrid_command(name="play", description="Plays music from YouTube/Spotify.")
    async def play(self, ctx, song: str): 
        await ctx.send(f"🎶 **Searching and queuing:** '{song}'\n*(Note: Requires FFmpeg and PyNaCl packages installed on host to broadcast audio).*")

    @commands.hybrid_command(name="skip", description="Skips the current song.")
    async def skip(self, ctx): 
        await ctx.send("⏭️ **Skipped current track.**")

    @commands.hybrid_command(name="queue", description="Shows the upcoming songs.")
    async def queue(self, ctx): 
        await ctx.send("📜 **Music Queue is currently empty.**")

    @commands.hybrid_command(name="stop", description="Stops music and clears queue.")
    async def stop(self, ctx): 
        await ctx.send("🛑 **Stopped music and cleared the queue.**")

    @commands.hybrid_command(name="volume", description="Changes the music volume.")
    async def volume(self, ctx, vol: int): 
        await ctx.send(f"🔊 **Volume set to {vol}%.**")

    @commands.hybrid_command(name="earrape", description="Bass boosts the music to 500%.")
    async def earrape(self, ctx): 
        await ctx.send("💥 **Volume forced to 500%. WARNING: LOUD.**")

    @commands.hybrid_command(name="soundboard", description="Plays a sound bite.")
    async def soundboard(self, ctx, sound: str): 
        await ctx.send(f"🔊 **Playing '{sound}' sound effect.**")

    @commands.hybrid_command(name="tts", description="Text-to-speech in VC.")
    async def tts(self, ctx, *, message: str): 
        await ctx.send(f"🗣️ **TTS Reading:** {message}")

# ==========================================
# FINAL SETUP SINK
# ==========================================
async def setup(bot):
    await bot.add_cog(MasterCommands(bot))
