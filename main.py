# main.py
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json
import os
import io
import asyncio
from flask import Flask, send_file
from threading import Thread

# --- Configuration ---
TOKEN = os.getenv('DISCORD_TOKEN')

ADMIN_CHANNEL_ID = 1219283442315952148
ANNOUNCEMENT_CHANNEL_ID = 815577373583736845

# --- Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Path Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUEST_DATA_FILE = os.path.join(SCRIPT_DIR, 'quests.json')
BASE_IMAGE_FILE = os.path.join(SCRIPT_DIR, 'questboard.png')

# --- Quest Data and Image Coordinates ---
# Quest names have been updated to match your questboard.png
QUEST_COORDINATES = {
    # Top Row
    "sweetbonanza1k": (13, 108, 461, 326),
    "wanted": (465, 107, 912, 326),
    "bigbass":    (918, 108, 1366, 326),

    # Middle Row
    "vampyparty":       (15, 331, 461, 547),
    "mines":            (464, 331, 912, 547),
    "towers":           (918, 331, 1366, 547),

    # Bottom Row
    "raptord":  (15, 555, 461, 774),
    "crazytime":        (464, 552, 912, 771),
    "outsourced":       (918, 552, 1366, 769),
}

# --- Flask Web Server Setup (Optional) ---
app = Flask('')
@app.route('/')
def home():
    return "Bot is alive and running!"

def run_flask():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)

# --- Bot Logic ---
def get_quest_data():
    """Loads quest data from the JSON file."""
    if not os.path.exists(QUEST_DATA_FILE):
        data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
        with open(QUEST_DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
        return data
    try:
        with open(QUEST_DATA_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
        with open(QUEST_DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
        return data

def save_quest_data(data):
    """Saves the quest data to the JSON file."""
    with open(QUEST_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def generate_quest_image():
    """Generates the quest board image with current statuses."""
    quest_data = get_quest_data()
    if not os.path.exists(BASE_IMAGE_FILE):
        print(f"ERROR: Base image not found at {BASE_IMAGE_FILE}")
        return None

    with Image.open(BASE_IMAGE_FILE) as base_img:
        img = base_img.copy().convert("RGBA")
        text_draw = ImageDraw.Draw(img)
        
        # Make sure NotoColorEmoji-Regular.ttf is in the same folder!
        try:
            font_path = os.path.join(SCRIPT_DIR, "NotoColorEmoji-Regular.ttf")
            font = ImageFont.truetype(font_path, 30)
        except IOError:
            print("WARNING: NotoColorEmoji-Regular.ttf not found. Emojis may not render.")
            font = ImageFont.load_default()

        for quest_name, coords in QUEST_COORDINATES.items():
            quest_info = quest_data.get(quest_name, {})
            status = quest_info.get('status', 'unclaimed')

            if status == 'unclaimed':
                continue

            x1, y1, x2, y2 = coords
            box_coords = (x1, y1, x2, y2)
            box_width = x2 - x1
            box_height = y2 - y1

            blurred_box = img.crop(box_coords).filter(ImageFilter.GaussianBlur(radius=5))
            img.paste(blurred_box, box_coords)

            claimer_name = quest_info.get('claimer_name', 'Unknown')
            line1, line2 = "", ""

            if status == 'pending':
                line1 = "Requested"
                line2 = f"by {claimer_name}"
            elif status == 'completed':
                line1 = "Completed ✅"
                line2 = f"by {claimer_name}"
            
            line1_bbox = text_draw.textbbox((0, 0), line1, font=font)
            line1_width, line1_height = line1_bbox[2] - line1_bbox[0], line1_bbox[3] - line1_bbox[1]
            line2_bbox = text_draw.textbbox((0, 0), line2, font=font)
            line2_width = line2_bbox[2] - line2_bbox[0]
            
            line_spacing = 10
            total_text_height = line1_height + line_spacing + line1_height

            line1_x = x1 + (box_width - line1_width) // 2
            line2_x = x1 + (box_width - line2_width) // 2
            block_start_y = y1 + (box_height - total_text_height) // 2
            line1_y, line2_y = block_start_y, block_start_y + line1_height + line_spacing

            text_draw.text((line1_x, line1_y), line1, font=font, fill=(255, 255, 255, 230))
            text_draw.text((line2_x, line2_y), line2, font=font, fill=(255, 255, 255, 230))

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

@bot.command(name='list')
async def list_quests(ctx):
    """Displays the quest board and lists all available quests."""
    buffer = generate_quest_image()
    if buffer is None:
        await ctx.send("Sorry, an error occurred while generating the quest board.")
        return

    quest_data = get_quest_data()
    
    embed = discord.Embed(title="Available Quests", color=discord.Color.blue())
    embed.set_footer(text="Use the listed command to claim a quest.")

    available_quests = []
    for quest_name in QUEST_COORDINATES.keys():
        if quest_data.get(quest_name, {}).get('status') == 'unclaimed':
            # Create a more readable display name for the embed
            display_name = ''.join([' ' + char if char.isupper() else char.title() for char in quest_name]).lstrip()
            available_quests.append(f"**{display_name}**\n`!claim {quest_name}`\n")
            
    if available_quests:
        embed.description = "\n".join(available_quests)
    else:
        embed.description = "All quests have been claimed or completed!"

    await ctx.send(embed=embed, file=discord.File(buffer, 'current_quests.png'))

@bot.command(name='claim')
async def claim_quest(ctx, quest_name: str, proof_link: str = None):
    quest_name = quest_name.lower()
    quest_data = get_quest_data()

    if quest_name not in QUEST_COORDINATES:
        await ctx.send(f"'{quest_name}' is not a valid quest name. Use `!list` to see available quests.")
        return
        
    if not ctx.message.attachments and proof_link is None:
        await ctx.send("You must attach proof or provide a replay link.")
        return

    quest_info = quest_data[quest_name]
    if quest_info['status'] != 'unclaimed':
        await ctx.send(f"Sorry, quest '{quest_name}' is already claimed or completed.")
        return

    quest_info['status'] = 'pending'
    quest_info['claimer_id'] = ctx.author.id
    quest_info['claimer_name'] = ctx.author.display_name
    save_quest_data(quest_data)

    buffer = generate_quest_image()
    await ctx.send(f"⏳ {ctx.author.mention} has claimed **{quest_name}**! Your claim is now under review.", file=discord.File(buffer, 'current_quests.png'))
    
    admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
    if not admin_channel: return

    embed = discord.Embed(title="⏳ New Pending Quest Claim!", color=discord.Color.orange())
    embed.add_field(name="Claimer", value=ctx.author.mention, inline=False)
    embed.add_field(name="Quest", value=quest_name, inline=False)
    embed.add_field(name="Original Message", value=f"[Jump to Message]({ctx.message.jump_url})", inline=False)
    embed.set_footer(text=f"Claimer ID: {ctx.author.id}")
    
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith('image/'):
            embed.set_image(url=attachment.url)
    elif proof_link and any(ext in proof_link.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
        embed.set_image(url=proof_link)
    
    try:
        msg = await admin_channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
    except discord.Forbidden:
        print(f"Error: Missing permissions in admin channel {ADMIN_CHANNEL_ID}")

@bot.event
async def on_raw_reaction_add(payload):
    """Handles admin reactions for approving/denying quest claims."""
    if payload.user_id == bot.user.id or payload.channel_id != ADMIN_CHANNEL_ID: return
    
    channel = bot.get_channel(payload.channel_id)
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return

    if not message.embeds or message.author.id != bot.user.id or "Pending" not in message.embeds[0].title:
        return

    reactor = payload.member
    if not reactor or not reactor.guild_permissions.manage_guild: return
    
    embed = message.embeds[0]
    
    quest_name = next((field.value for field in embed.fields if field.name == "Quest"), None)
    claimer_id_str = embed.footer.text.replace("Claimer ID: ", "")

    if not quest_name or not claimer_id_str:
        print("Could not find quest name or claimer ID in embed.")
        return
        
    claimer_id = int(claimer_id_str)
    claimer = payload.member.guild.get_member(claimer_id)
    quest_data = get_quest_data()

    if quest_name not in quest_data: return
    
    announcement_channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    new_embed = embed.copy()
    new_embed.add_field(name="Moderator", value=reactor.mention)

    if str(payload.emoji) == "✅":
        quest_data[quest_name]['status'] = 'completed'
        new_embed.title = "✅ Quest Claim Approved"
        new_embed.color = discord.Color.green()
        if announcement_channel:
            msg_text = f"🎉 Congratulations to {claimer.mention if claimer else f'User ID {claimer_id}'} for completing **{quest_name}**! Approved."
            await announcement_channel.send(msg_text, file=discord.File(generate_quest_image(), 'current_quests.png'))
    
    elif str(payload.emoji) == "❌":
        quest_data[quest_name]['status'] = 'unclaimed'
        quest_data[quest_name]['claimer_id'] = None
        quest_data[quest_name]['claimer_name'] = None
        new_embed.title = "❌ Quest Claim Denied"
        new_embed.color = discord.Color.red()
        if announcement_channel:
            msg_text = f"ℹ️ The claim for **{quest_name}** by {claimer.mention if claimer else f'User ID {claimer_id}'} was denied. The quest is now open!"
            await announcement_channel.send(msg_text, file=discord.File(generate_quest_image(), 'current_quests.png'))
    else:
        return

    save_quest_data(quest_data)
    await message.edit(embed=new_embed)
    await message.clear_reactions()

@bot.command(name='resetquests', hidden=True)
@commands.has_permissions(administrator=True)
async def reset_quests(ctx):
    """Resets all quests to 'unclaimed'."""
    default_data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
    save_quest_data(default_data)
    await ctx.send("✅ All quests have been reset.")
    buffer = generate_quest_image()
    if buffer:
        await ctx.send("The quest board is now clean:", file=discord.File(buffer, 'current_quests.png'))

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('Bot is ready to accept commands.')

def run_bot():
    if TOKEN:
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("FATAL ERROR: Invalid Discord token.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
    else:
        print("FATAL ERROR: DISCORD_TOKEN not found in environment variables.")

if __name__ == "__main__":
    # If you need the web server for uptime monitoring, uncomment the following lines
    # flask_thread = Thread(target=run_flask)
    # flask_thread.daemon = True
    # flask_thread.start()
    run_bot()
