# main.py
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import json
import os
import io
import asyncio

# --- Configuration ---
# IMPORTANT: Create a file named .env in the same directory as this script
# and add your bot token like this:
# DISCORD_TOKEN=YourActualBotTokenGoesHere
#
# You also need to set the channel IDs for your server.
# To get a channel ID, right-click the channel in Discord and select "Copy Channel ID".
# You must enable Developer Mode in your Discord settings for this option to appear.
# (Settings -> Advanced -> Developer Mode)

try:
    from dotenv import load_dotenv
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
except ImportError:
    print("dotenv library not found. Please install it with 'pip install python-dotenv'")
    TOKEN = None # Set your token here directly if you don't use a .env file

ADMIN_CHANNEL_ID = 1219283442315952148  # <<< CHANGE THIS to your private mod/admin channel ID
ANNOUNCEMENT_CHANNEL_ID = 815577373583736845 # <<< CHANGE THIS to your public announcement channel ID

# --- Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.guilds = True
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
QUEST_DATA_FILE = 'quests.json'
BASE_IMAGE_FILE = 'questboard.png' # Make sure your image file is named this and is in the same folder

# Quest Statuses: 'unclaimed', 'pending', 'completed'
PENDING_COLOR = (255, 165, 0, 180)  # Orange, semi-transparent
COMPLETED_COLOR = (255, 0, 0, 255) # Red, solid

def get_quest_data():
    """Loads quest completion status from the JSON file."""
    if not os.path.exists(QUEST_DATA_FILE):
        # Create a default file if it doesn't exist
        data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
        with open(QUEST_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return data
    with open(QUEST_DATA_FILE, 'r') as f:
        return json.load(f)

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
            status = data['status']
            coords = QUEST_COORDINATES.get(name)
            if not coords:
                continue

            color = None
            if status == 'pending':
                color = PENDING_COLOR
            elif status == 'completed':
                color = COMPLETED_COLOR

            if color:
                x1, y1, x2, y2 = coords
                # Draw a big 'X'
                draw.line([(x1 + 10, y1 + 10), (x2 - 10, y2 - 10)], fill=color, width=15)
                draw.line([(x2 - 10, y1 + 10), (x1 + 10, y2 - 10)], fill=color, width=15)
        
        # Composite the overlay with the 'X's onto the base image
        img = Image.alpha_composite(img, overlay)

        buffer = io.BytesIO()
        img.convert("RGB").save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

@bot.event
async def on_ready():
    """Event that runs when the bot is connected and ready."""
    print(f'Logged in as {bot.user.name}')
    print('Bot is ready to accept commands.')
    if ADMIN_CHANNEL_ID == 123456789012345678 or ANNOUNCEMENT_CHANNEL_ID == 123456789012345678:
        print("\n" + "="*50 + "\n!!! IMPORTANT !!!\nPlease change the ADMIN_CHANNEL_ID and ANNOUNCEMENT_CHANNEL_ID in the script.\n" + "="*50 + "\n")
    if not os.path.exists(BASE_IMAGE_FILE):
         print(f"Error: Base image '{BASE_IMAGE_FILE}' not found. Please place it in the same directory.")

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
        await ctx.send(f"'{quest_name}' is not a valid quest name. Please check the `!list` and try again.")
        return

    if not ctx.message.attachments:
        await ctx.send("You must attach proof (an image or video) to your claim!")
        return
    
    quest_info = quest_data[quest_name]
    if quest_info['status'] != 'unclaimed':
        claimer_name = quest_info.get("claimer_name", "Someone")
        await ctx.send(f"Sorry, quest '{quest_name}' is already '{quest_info['status']}' by {claimer_name}.")
        return

    # --- Update state to PENDING ---
    quest_info['status'] = 'pending'
    quest_info['claimer_id'] = ctx.author.id
    quest_info['claimer_name'] = ctx.author.display_name
    save_quest_data(quest_data)

    # --- Send Immediate Update ---
    await ctx.send(f"⏳ {ctx.author.mention} has tentatively claimed **{quest_name}**! Your claim is now under review.")
    buffer = generate_quest_image()
    await ctx.send(file=discord.File(buffer, 'current_quests.png'))
    
    # --- Send to Admin Channel for Review ---
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
        await msg.add_reaction("✅") # Approve
        await msg.add_reaction("❌") # Deny
    except discord.Forbidden:
        print(f"Error: Missing permissions in admin channel {ADMIN_CHANNEL_ID}")

@bot.command(name='resetquests', hidden=True)
@commands.has_permissions(administrator=True)
async def reset_quests(ctx):
    """(Admin Only) Resets all quests to 'unclaimed'."""
    default_data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
    save_quest_data(default_data)
    await ctx.send("✅ All quests have been reset to 'unclaimed'.")
    buffer = generate_quest_image()
    await ctx.send("The quest board is now clean:", file=discord.File(buffer, 'current_quests.png'))

# --- Event Handling for Reactions ---

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id or payload.channel_id != ADMIN_CHANNEL_ID:
        return

    channel = bot.get_channel(payload.channel_id)
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return

    if not message.embeds or message.author.id != bot.user.id or not ( "Pending" in message.embeds[0].title ):
        return

    guild = bot.get_guild(payload.guild_id)
    reactor = guild.get_member(payload.user_id)
    if not reactor.guild_permissions.administrator:
        return

    embed = message.embeds[0]
    quest_name = next((field.value for field in embed.fields if field.name == "Quest"), None)
    claimer_id = int(embed.footer.text.replace("Claimer ID: ", ""))
    claimer = guild.get_member(claimer_id)
    quest_data = get_quest_data()

    if quest_name not in quest_data:
        return
        
    announcement_channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)

    if str(payload.emoji) == "✅":
        quest_data[quest_name]['status'] = 'completed'
        save_quest_data(quest_data)

        if announcement_channel:
            congrats_msg = f"🎉 Congratulations to {claimer.mention} for completing the **{quest_name}** quest! Their claim has been approved."
            new_image_buffer = generate_quest_image()
            await announcement_channel.send(congrats_msg, file=discord.File(new_image_buffer, 'current_quests.png'))
        
        new_embed = embed.copy()
        new_embed.title = "✅ Quest Claim Approved"
        new_embed.color = discord.Color.green()
        new_embed.add_field(name="Moderator", value=reactor.mention)
        await message.edit(embed=new_embed)
        await message.clear_reactions()

    elif str(payload.emoji) == "❌":
        quest_data[quest_name]['status'] = 'unclaimed'
        quest_data[quest_name]['claimer_id'] = None
        quest_data[quest_name]['claimer_name'] = None
        save_quest_data(quest_data)

        if claimer:
            await claimer.send(f"Sorry, your claim for the quest '{quest_name}' was denied. The quest is now available again.")

        if announcement_channel:
            denial_msg = f"ℹ️ The claim for **{quest_name}** by {claimer.mention} was denied. The quest is now open again!"
            new_image_buffer = generate_quest_image()
            await announcement_channel.send(denial_msg, file=discord.File(new_image_buffer, 'current_quests.png'))

        new_embed = embed.copy()
        new_embed.title = "❌ Quest Claim Denied"
        new_embed.color = discord.Color.red()
        new_embed.add_field(name="Moderator", value=reactor.mention)
        await message.edit(embed=new_embed)
        await message.clear_reactions()


# --- Error Handling & Run ---
@claim_quest.error
async def claim_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("You need to specify which quest you're claiming! Usage: `!claim <quest_name>`")

if TOKEN is None:
    print("FATAL ERROR: Bot token is not configured. Please set DISCORD_TOKEN in your .env file.")
else:
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"An error occurred while running the bot: {e}")
