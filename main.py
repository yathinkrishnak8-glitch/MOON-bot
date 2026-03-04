import discord
from discord.ext import commands
import google.generativeai as genai
import os

# 1. SETUP GEMINI
# This uses the secret GEMINI_TOKEN you will set in Termux or GitHub
genai.configure(api_key=os.environ.get("GEMINI_TOKEN"))
model = genai.GenerativeModel("gemini-1.5-flash")

# 2. SETUP DISCORD BOT
# We enable 'members' intent so admin commands like kick/ban work correctly
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Moon-bot is online as {bot.user}')
    # Sets a "Listening to..." status on Discord
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="your prompts"))

# 3. AI CHAT & DM FEATURE
@bot.event
async def on_message(message):
    # Don't let the bot reply to itself
    if message.author == bot.user:
        return

    # Trigger: If the message is a DM OR if the bot is mentioned in a server
    if message.guild is None or bot.user in message.mentions:
        # Clean the message (remove the @mention tag)
        clean_text = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        # If the message is empty after cleaning, don't do anything
        if not clean_text:
            return

        async with message.channel.typing():
            try:
                # Send the text to Gemini
                response = model.generate_content(clean_text)
                # Reply back to the user
                await message.reply(response.text)
            except Exception as e:
                print(f"Error: {e}")
                await message.reply("⚠️ My AI brain is currently offline. Check your API key!")

    # This line is REQUIRED to make @bot.command() work
    await bot.process_commands(message)

# 4. ADMIN COMMANDS
# Only users with 'Kick Members' permission can use this
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f'👢 {member.display_name} has been kicked. Reason: {reason}')

# Only users with 'Ban Members' permission can use this
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f'🚫 {member.display_name} has been banned. Reason: {reason}')

# Quick message cleanup (e.g., !clear 10)
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f'🧹 Deleted {amount} messages.', delete_after=3)

# 5. RUN THE BOT
# This uses the secret TOKEN you will set in Termux or GitHub
bot.run(os.environ.get("TOKEN"))
