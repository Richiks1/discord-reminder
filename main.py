# main.py
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import json
import os
import io
import asyncio
from flask import Flask
from threading import Thread

# --- Configuration ---
# IMPORTANT: Create a file named .env in the same directory as this script
# and add your bot token like this:
# DISCORD_TOKEN=YourActualBotTokenGoesHere

try:
    from dotenv import load_dotenv
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
except ImportError:
    print("dotenv library not found. Please install it with 'pip install python-dotenv'")
    TOKEN = None # Set your token here directly if you don't use a .env file

ADMIN_CHANNEL_ID = 1219283442315952148
ANNOUNCEMENT_CHANNEL_ID = 815577373583736845

# --- Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.guilds = True
# FIX: Added Members Intent to allow the bot to find users by ID for tagging.
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Quest Data and Image Coordinates ---
QUEST_COORDINATES = {
    "sweet1": (35, 200, 350, 425),
    "wanted": (360, 200, 675, 425),
    "bigbass": (685, 200, 1000, 425),
    "vampy": (35, 440, 350, 665),
    "mines": (360, 440, 675, 665),
    "towers": (685, 440, 1000, 665),
    "sweet2": (35, 675, 350, 900),
    "sweet3": (360, 675, 675, 900),
    "sweet4": (685, 675, 1000, 900),
}
# NOTE: Without a persistent disk, this file will be reset when the bot restarts.
QUEST_DATA_FILE = 'quests.json'
BASE_IMAGE_FILE = 'questboard.png'

# Quest Statuses: 'unclaimed', 'pending', 'completed'
PENDING_COLOR = (255, 165, 0, 200)  # Orange, semi-transparent
COMPLETED_COLOR = (255, 0, 0, 255) # Red, solid

# --- Flask Web Server Setup ---
# This small web server keeps the bot alive on free hosting platforms.
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_flask():
  app.run(host='0.0.0.0', port=8080)

# --- Bot Logic ---

def get_quest_data():
    """Loads quest completion status from the JSON file."""
    if not os.path.exists(QUEST_DATA_FILE):
        data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
        with open(QUEST_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return data
    try:
        with open(QUEST_DATA_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        # If file is corrupt or gone, create a new one
        data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
        with open(QUEST_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return data


def save_quest_data(data):
    """Saves quest completion status to the JSON file."""
    with open(QUEST_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def generate_quest_image():
    """Generates the quest board image with markers for pending/completed quests."""
    quest_data = get_quest_data()
    
    if not os.path.exists(BASE_IMAGE_FILE):
        print(f"Error: Base image '{BASE_IMAGE_FILE}' not found.")
        return None

    with Image.open(BASE_IMAGE_FILE) as img:
        img = img.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        for name, data in quest_data.items():
            status = data.get('status', 'unclaimed')
            coords = QUEST_COORDINATES.get(name)
            if not coords: continue

            color = None
            # FIX: Adjust margin to make the completed 'X' larger
            margin = 15 # Default margin for smaller pending 'X'
            
            if status == 'pending': 
                color = PENDING_COLOR
            elif status == 'completed': 
                color = COMPLETED_COLOR
                margin = 2 # Smaller margin for larger completed 'X'

            if color:
                x1, y1, x2, y2 = coords
                draw.line([(x1 + margin, y1 + margin), (x2 - margin, y2 - margin)], fill=color, width=15)
                draw.line([(x2 - margin, y1 + margin), (x1 + margin, y2 - margin)], fill=color, width=15)
        
        # Composite the overlay with the 'X's onto the base image
        img = Image.alpha_composite(img, overlay)

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

@bot.event
async def on_ready():
    """Event that runs when the bot is connected and ready."""
    print(f'Logged in as {bot.user.name}')
    print('Bot is ready to accept commands.')
    if not os.path.exists(BASE_IMAGE_FILE):
         print(f"Error: Base image '{BASE_IMAGE_FILE}' not found. Please place it in the same directory.")
         return

    announcement_channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if announcement_channel:
        try:
            # FIX: Added a 20-second delay before posting
            print("Waiting 20 seconds before posting initial quest board...")
            await asyncio.sleep(20)
            
            print(f"Sending initial quest board to channel: {announcement_channel.name}")
            buffer = generate_quest_image()
            if buffer:
                await announcement_channel.send("The weekly quest board is here! Use `!list` to see the latest version at any time.", file=discord.File(buffer, 'current_quests.png'))
            else:
                print("Failed to generate quest image on startup.")
        except discord.Forbidden:
            print(f"Error: Bot does not have permission to send messages in the announcement channel (ID: {ANNOUNCEMENT_CHANNEL_ID}).")
        except Exception as e:
            print(f"An error occurred when trying to post initial quest board: {e}")
    else:
        print(f"Error: Could not find announcement channel with ID {ANNOUNCEMENT_CHANNEL_ID} on startup.")


# --- Bot Commands ---

@bot.command(name='list')
async def list_quests(ctx):
    """Displays the current quest board."""
    buffer = generate_quest_image()
    if buffer is None:
        await ctx.send(f"Sorry, the quest board image (`{BASE_IMAGE_FILE}`) is missing.")
        return
    await ctx.send(file=discord.File(buffer, 'current_quests.png'))

@bot.command(name='claim')
async def claim_quest(ctx, quest_name: str):
    """
    Claims a quest, marking it as 'pending'. Attach your proof (image/video).
    Usage: !claim <quest_name>
    """
    quest_name = quest_name.lower()
    quest_data = get_quest_data()

    if quest_name not in quest_data:
        await ctx.send(f"'{quest_name}' is not a valid quest name. Please check `!list` and try again.")
        return

    if not ctx.message.attachments:
        await ctx.send("You must attach proof (an image or video) to your claim!")
        return
    
    quest_info = quest_data[quest_name]
    if quest_info['status'] != 'unclaimed':
        claimer_name = quest_info.get("claimer_name", "Someone")
        await ctx.send(f"Sorry, quest '{quest_name}' is already '{quest_info['status']}' by {claimer_name}.")
        return

    quest_info['status'] = 'pending'
    quest_info['claimer_id'] = ctx.author.id
    quest_info['claimer_name'] = ctx.author.display_name
    save_quest_data(quest_data)

    await ctx.send(f"⏳ {ctx.author.mention} has claimed **{quest_name}**! Your claim is now under review.")
    buffer = generate_quest_image()
    await ctx.send(file=discord.File(buffer, 'current_quests.png'))
    
    admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
    if not admin_channel:
        print(f"Error: Could not find admin channel with ID {ADMIN_CHANNEL_ID}")
        return

    embed = discord.Embed(title="⏳ New Pending Quest Claim!", color=discord.Color.orange())
    embed.add_field(name="Claimer", value=ctx.author.mention, inline=False)
    embed.add_field(name="Quest", value=quest_name, inline=False)
    embed.add_field(name="Original Message", value=f"[Jump to Message]({ctx.message.jump_url})", inline=False)
    embed.set_image(url=ctx.message.attachments[0].url)
    embed.set_footer(text=f"Claimer ID: {ctx.author.id}")

    try:
        msg = await admin_channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
    except discord.Forbidden:
        print(f"Error: Missing permissions in admin channel {ADMIN_CHANNEL_ID}")

@bot.command(name='resetquests', hidden=True)
@commands.has_permissions(administrator=True)
async def reset_quests(ctx):
    """(Admin Only) Resets all quests to 'unclaimed'."""
    default_data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
    save_quest_data(default_data)
    await ctx.send("✅ All quests have been reset.")
    buffer = generate_quest_image()
    await ctx.send("The quest board is now clean:", file=discord.File(buffer, 'current_quests.png'))

# --- Event Handling for Reactions ---

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    
    print(f"DEBUG: Reaction '{payload.emoji}' by {payload.member.display_name if payload.member else payload.user_id} in channel {payload.channel_id}")

    if payload.channel_id != ADMIN_CHANNEL_ID: return

    print("DEBUG: Reaction is in the correct admin channel.")
    
    channel = bot.get_channel(payload.channel_id)
    try: 
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound: 
        print("DEBUG: Reaction was on a message not found in cache.")
        return

    if not message.embeds or message.author.id != bot.user.id or not ( "Pending" in message.embeds[0].title ):
        print("DEBUG: Reaction was on a message that is not a pending claim. Ignoring.")
        return

    print("DEBUG: Reaction is on a valid pending claim message.")

    reactor = payload.member 
    if not reactor:
        print(f"DEBUG: Could not identify the member who reacted.")
        return

    if not reactor.guild_permissions.manage_guild:
        print(f"DEBUG: User {reactor.display_name} lacks 'Manage Server' permission to approve/deny.")
        return
    
    print(f"DEBUG: User {reactor.display_name} has permissions. Processing action.")

    embed = message.embeds[0]
    quest_name = next((field.value for field in embed.fields if field.name == "Quest"), None)
    claimer_id = int(embed.footer.text.replace("Claimer ID: ", ""))
    # FIX: Fetch the guild to reliably get the member object for tagging
    guild = bot.get_guild(payload.guild_id)
    claimer = None
    if guild:
        claimer = guild.get_member(claimer_id)

    quest_data = get_quest_data()

    if not quest_name or quest_name not in quest_data: return
    announcement_channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)

    if str(payload.emoji) == "✅":
        quest_data[quest_name]['status'] = 'completed'
        save_quest_data(quest_data)

        if announcement_channel:
            congrats_msg = f"🎉 Congratulations to {claimer.mention if claimer else f'User ID {claimer_id}'} for completing **{quest_name}**! Approved."
            new_image_buffer = generate_quest_image()
            await announcement_channel.send(congrats_msg, file=discord.File(new_image_buffer, 'current_quests.png'))
        
        new_embed = embed.copy(); new_embed.title = "✅ Quest Claim Approved"; new_embed.color = discord.Color.green()
        new_embed.add_field(name="Moderator", value=reactor.mention)
        await message.edit(embed=new_embed); await message.clear_reactions()
        print(f"INFO: Claim for '{quest_name}' was APPROVED by {reactor.display_name}.")


    elif str(payload.emoji) == "❌":
        quest_data[quest_name]['status'] = 'unclaimed'
        quest_data[quest_name]['claimer_id'] = None
        quest_data[quest_name]['claimer_name'] = None
        save_quest_data(quest_data)

        if claimer: await claimer.send(f"Sorry, your claim for '{quest_name}' was denied. The quest is now available again.")
        if announcement_channel:
            denial_msg = f"ℹ️ The claim for **{quest_name}** by {claimer.mention if claimer else f'User ID {claimer_id}'} was denied. The quest is now open!"
            new_image_buffer = generate_quest_image()
            await announcement_channel.send(denial_msg, file=discord.File(new_image_buffer, 'current_quests.png'))

        new_embed = embed.copy(); new_embed.title = "❌ Quest Claim Denied"; new_embed.color = discord.Color.red()
        new_embed.add_field(name="Moderator", value=reactor.mention)
        await message.edit(embed=new_embed); await message.clear_reactions()
        print(f"INFO: Claim for '{quest_name}' was DENIED by {reactor.display_name}.")

# --- Error Handling & Run ---
@claim_quest.error
async def claim_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!claim <quest_name>`")

def run_bot():
    if TOKEN is None:
        print("FATAL ERROR: Bot token not configured. Please set DISCORD_TOKEN in your .env file or as an environment variable.")
        return
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("FATAL ERROR: Invalid Discord token.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Start the Flask server in a new thread
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Run the Discord bot in the main thread
    run_bot()
