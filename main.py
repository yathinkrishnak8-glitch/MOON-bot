import discord
from discord.ext import commands
import os
import traceback

# ========================================================================
# ENVIRONMENT SETUP
# ========================================================================
# Grab the token from environment variables (Required for Keep_alive / Hosting)
# If you are running locally without env variables, you can paste it here, 
# but NEVER share this file if your token is hardcoded!
TOKEN = os.environ.get('DISCORD_TOKEN') 

# Setup intents (This allows the bot to read message content and see member lists)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Initialize the Bot Engine
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ========================================================================
# BOOT SEQUENCE & SYNCING
# ========================================================================
@bot.event
async def on_ready():
    print("==================================================")
    print(f"✅ SYSTEM ONLINE: Logged in successfully as {bot.user.name}")
    print("==================================================")
    
    # Set the bot's rich presence status
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="over the server | /masterlist"
    ))
    
    # Sync Slash Commands to Discord globally
    try:
        print("🔄 Syncing slash commands...")
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands globally.")
    except Exception as e:
        print(f"⚠️ Failed to sync slash commands: {e}")


# ========================================================================
# GLOBAL ERROR HANDLER
# Description: Intercepts all errors so the bot doesn't fail silently.
# ========================================================================
@bot.event
async def on_command_error(ctx, error):
    # Ignore commands that don't exist
    if isinstance(error, commands.CommandNotFound):
        return

    # User forgot an argument (e.g. typing /pay without the amount)
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(description=f"❌ **Bro, you missed something!**\nYou are missing the `{error.param.name}` argument.", color=discord.Color.red())
        return await ctx.send(embed=embed, ephemeral=True)

    # User is on a cooldown
    if isinstance(error, commands.CommandOnCooldown):
        minutes, seconds = divmod(error.retry_after, 60)
        hours, minutes = divmod(minutes, 60)
        
        time_str = ""
        if hours > 0: time_str += f"**{int(hours)}h** "
        if minutes > 0: time_str += f"**{int(minutes)}m** "
        time_str += f"**{int(seconds)}s**"
        
        embed = discord.Embed(description=f"⏳ **Chill bro!** This command is on cooldown. Try again in {time_str}.", color=discord.Color.orange())
        return await ctx.send(embed=embed, ephemeral=True)

    # User lacks permissions
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(description="🛑 **Access Denied.** You do not have the required permissions to do this.", color=discord.Color.dark_red())
        return await ctx.send(embed=embed, ephemeral=True)

    # Developer ONLY commands
    if isinstance(error, commands.NotOwner):
        embed = discord.Embed(description="⛔ **Security Block:** Only the bot owner can use this command.", color=discord.Color.dark_red())
        return await ctx.send(embed=embed, ephemeral=True)

    # If it's something else, print it to the console so you can debug it
    print(f"⚠️ [Error in {ctx.command}]: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)


# ========================================================================
# THE COG LOADER
# Description: Scans the 'cogs' folder and loads every Python file.
# ========================================================================
async def load_all_cogs():
    print("⏳ Loading modular cogs...")
    success_count = 0
    fail_count = 0
    
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f"  📦 Loaded: {filename}")
                success_count += 1
            except Exception as e:
                print(f"  ❌ Failed to load {filename}: {e}")
                fail_count += 1
                
    print(f"🏁 Modules Loaded: {success_count} Success, {fail_count} Failed.")


# ========================================================================
# ASYNC MAIN RUNNER
# ========================================================================
async def main():
    async with bot:
        # Load all the cogs before starting the bot
        await load_all_cogs()
        
        if not TOKEN:
            print("\n❌ CRITICAL ERROR: DISCORD_TOKEN is missing!")
            print("Please set your bot token in the environment variables.")
            return
            
        # Start the bot connection
        await bot.start(TOKEN)

# Trigger the event loop
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
