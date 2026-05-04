import discord
from discord.ext import commands
import os
import traceback
import asyncio
from dotenv import load_dotenv
from keep_alive import keep_alive

# ========================================================================
# ⚙️ CONFIGURATION & ENV LOADING
# ========================================================================
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Define bot intents (Essential for reading messages and managing members)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

class HabibiBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            case_insensitive=True
        )

    # ========================================================================
    # 📦 MODULAR COG LOADER
    # ========================================================================
    async def setup_hook(self):
        """This runs before the bot starts connecting to Discord."""
        print("🚀 [BOOT] Starting Cog Loader...")
        
        # Ensure the cogs directory exists
        if not os.path.exists('./cogs'):
            os.makedirs('./cogs')
            print("📁 [SYSTEM] Created missing 'cogs' directory.")

        success = 0
        failed = 0
        
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    # Loading cogs dynamically
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"  ✅ Loaded Module: {filename}")
                    success += 1
                except Exception as e:
                    print(f"  ❌ Failed to load {filename}: {e}")
                    traceback.print_exc()
                    failed += 1
        
        print(f"🏁 [BOOT] Load Complete: {success} Success | {failed} Failed")
        
        # Syncing Slash Commands
        print("🔄 [SYSTEM] Syncing Slash Commands globally...")
        try:
            synced = await self.tree.sync()
            print(f"✅ [SYSTEM] Successfully synced {len(synced)} commands.")
        except Exception as e:
            print(f"⚠️ [SYSTEM] Slash Sync Error: {e}")

    # ========================================================================
    # 🟢 ON_READY EVENT
    # ========================================================================
    async def on_ready(self):
        print("\n" + "="*50)
        print(f"🟢 HABIBI BOT IS ONLINE")
        print(f"Logged in as: {self.user.name} (ID: {self.user.id})")
        print(f"Connected to {len(self.guilds)} servers")
        print("="*50 + "\n")
        
        # Set Activity Status
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name="over the server | /masterlist"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

# ========================================================================
# 🛠️ GLOBAL ERROR HANDLER
# ========================================================================
bot = HabibiBot()

@bot.event
async def on_command_error(ctx, error):
    """Intercepts and roasts users for making mistakes."""
    
    # Command doesn't exist? Ignore it.
    if isinstance(error, commands.CommandNotFound):
        return

    # Missing arguments (e.g. forgot to mention someone)
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            description=f"❌ **Missing Info!** You forgot to provide the `{error.param.name}` argument.", 
            color=discord.Color.red()
        )
        return await ctx.send(embed=embed, delete_after=10)

    # Cooldown check
    if isinstance(error, commands.CommandOnCooldown):
        m, s = divmod(error.retry_after, 60)
        h, m = divmod(m, 60)
        time_left = f"{int(h)}h {int(m)}m {int(s)}s" if h > 0 else f"{int(m)}m {int(s)}s" if m > 0 else f"{int(s)}s"
        
        embed = discord.Embed(
            description=f"⏳ **Too fast!** Chill for another **{time_left}**.", 
            color=discord.Color.orange()
        )
        return await ctx.send(embed=embed, delete_after=5)

    # Permission check
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            description="🛑 **Unauthorized.** You don't have the rank to do that.", 
            color=discord.Color.dark_red()
        )
        return await ctx.send(embed=embed, delete_after=10)

    # Bot Owner check
    if isinstance(error, commands.NotOwner):
        embed = discord.Embed(
            description="⛔ **Developer Access Only.** This command is restricted.", 
            color=discord.Color.black()
        )
        return await ctx.send(embed=embed, delete_after=10)

    # Print any other errors to the console for you to fix
    print(f"⚠️ [Runtime Error]: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)

# ========================================================================
# 🔥 ENGINE IGNITION
# ========================================================================
async def start_engine():
    async with bot:
        # Check for token
        if not TOKEN:
            print("❌ CRITICAL ERROR: DISCORD_TOKEN not found in .env file!")
            return
            
        # Start the Keep Alive web server for 24/7 hosting
        try:
            keep_alive()
            print("🌐 [SYSTEM] Keep-Alive Web Server started on Port 8080")
        except Exception as e:
            print(f"⚠️ [SYSTEM] Keep-Alive failed: {e}")

        # Ignite Bot
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(start_engine())
    except KeyboardInterrupt:
        print("🛑 [SYSTEM] Bot shutting down manually...")
    except Exception as e:
        print(f"❌ [CRITICAL SHUTDOWN]: {e}")
