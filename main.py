import discord
from discord.ext import commands
import os
import asyncio
from keep_alive import keep_alive

# ==========================================
# 1. CORE SETUP
# ==========================================
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')

if not DISCORD_TOKEN:
    print("CRITICAL: DISCORD_TOKEN is missing! Set it in your Environment Variables.")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ==========================================
# 2. MODULAR COG LOADER
# ==========================================
async def load_extensions():
    # Automatically create the cogs folder if it doesn't exist
    if not os.path.exists('./cogs'):
        os.makedirs('./cogs')
        print("📁 Created 'cogs' folder.")
        
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f"✅ Loaded modular cog: {filename}")
            except Exception as e:
                print(f"❌ Failed to load cog {filename}: {e}")

# ==========================================
# 3. ON READY & COMMAND SYNC
# ==========================================
@bot.event
async def on_ready():
    print(f"🟢 {bot.user} is online and operational.")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands globally!")
    except Exception as e:
        print(f"⚠️ Failed to sync slash commands: {e}")

# ==========================================
# 4. RENDER BOOT SEQUENCE
# ==========================================
async def main():
    async with bot:
        await load_extensions()
        if DISCORD_TOKEN:
            await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
