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

# --- Path Configuration (Robust Version) ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUEST_DATA_FILE = os.path.join(SCRIPT_DIR, 'quests.json')
BASE_IMAGE_FILE = os.path.join(SCRIPT_DIR, 'questboard.png')

# --- Quest Data and Image Coordinates (UPDATED) ---
QUEST_COORDINATES = {
    "sweet1": (13, 108, 461, 326),
    "wanted":   (465, 107, 912, 326),
    "bigbass":  (918, 108, 1366, 326),
    "vampy":    (15, 331, 461, 547),
    "mines":    (464, 331, 912, 547),
    "towers":   (918, 331, 1366, 547),
    "sweet2":   (15, 555, 461, 774),
    "sweet3":   (464, 552, 912, 771),
    "sweet4":   (918, 552, 1366, 769),
}


# Quest Statuses Color
LEGACY_COMPLETED_COLOR = (255, 0, 0, 255)

# --- Flask Web Server Setup ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

@app.route('/questboard.png')
def serve_questboard_image():
    image_buffer = generate_quest_image()
    if image_buffer is None:
        return "Error generating image. Check logs.", 500
    return send_file(image_buffer, mimetype='image/png', as_attachment=False)

def run_flask():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)

# --- Bot Logic ---
def get_quest_data():
    if not os.path.exists(QUEST_DATA_FILE):
        data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
        with open(QUEST_DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
        return data
    try:
        with open(QUEST_DATA_FILE, 'r') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
        with open(QUEST_DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
        return data

def save_quest_data(data):
    with open(QUEST_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def generate_quest_image():
    quest_data = get_quest_data()
    if quest_data is None: return None
    if not os.path.exists(BASE_IMAGE_FILE):
        print(f"Error: Base image not found at path: {BASE_IMAGE_FILE}")
        return None

    with Image.open(BASE_IMAGE_FILE) as base_img:
        img = base_img.copy().convert("RGBA")
        text_draw = ImageDraw.Draw(img)
        font_path = os.path.join(SCRIPT_DIR, "arial.ttf")
        try:
            # Increased font size for better visibility
            font = ImageFont.truetype(font_path, 30)
        except IOError:
            print(f"WARNING: Font not found at {font_path}. Using default font.")
            font = ImageFont.load_default()

        x_overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw_x = ImageDraw.Draw(x_overlay)

        for name, data in quest_data.items():
            status = data.get('status', 'unclaimed')
            coords = QUEST_COORDINATES.get(name)
            if not coords: continue

            # --- MODIFIED SECTION ---
            text_to_draw = None
            if status == 'pending':
                claimer_name = data.get('claimer_name', 'Unknown')
                text_to_draw = f"Requested and under by {claimer_name}"
            elif status == 'completed':
                text_to_draw = "Completed ✅"

            if text_to_draw:
                # Define coordinates and dimensions of the quest box
                x1, y1, x2, y2 = coords
                box_coords = (x1, y1, x2, y2)
                box_width = x2 - x1
                box_height = y2 - y1

                # Apply blur and a darkening layer to the area
                blurred_box = img.crop(box_coords).filter(ImageFilter.GaussianBlur(radius=5))
                img.paste(blurred_box, box_coords)
                darken_layer = Image.new('RGBA', (box_width, box_height), (0, 0, 0, 96))
                img.paste(darken_layer, box_coords, darken_layer)

                # Calculate text size and position to center it
                text_bbox = text_draw.textbbox((0, 0), text_to_draw, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                text_x = x1 + (box_width - text_width) // 2
                text_y = y1 + (box_height - text_height) // 2

                # Draw the text in white
                text_draw.text((text_x, text_y), text_to_draw, font=font, fill=(255, 255, 255, 230))

            elif status == 'completed_legacy':
                x1, y1, x2, y2 = coords
                draw_x.line([(x1 + 30, y1 + 30), (x2 - 30, y2 - 30)], fill=LEGACY_COMPLETED_COLOR, width=25)
                draw_x.line([(x2 - 30, y1 + 30), (x1 + 30, y2 - 30)], fill=LEGACY_COMPLETED_COLOR, width=25)

        img = Image.alpha_composite(img, x_overlay)
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('Bot is ready to accept commands.')
    announcement_channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if announcement_channel:
        try:
            print("Waiting 5 seconds before posting initial quest board...")
            await asyncio.sleep(5)
            print(f"Sending initial quest board to channel: {announcement_channel.name}")
            buffer = generate_quest_image()
            if buffer:
                await announcement_channel.send("The weekly quest board is here! Use `!list` to see the latest version at any time.", file=discord.File(buffer, 'current_quests.png'))
            else:
                print("Failed to generate quest image on startup. Check logs for errors.")
        except Exception as e:
            print(f"An error occurred when trying to post initial quest board: {e}")
    else:
        print(f"Error: Could not find announcement channel with ID {ANNOUNCEMENT_CHANNEL_ID} on startup.")

@bot.command(name='list')
async def list_quests(ctx):
    buffer = generate_quest_image()
    if buffer is None:
        await ctx.send("Sorry, an error occurred while generating the quest board.")
        return
    await ctx.send(file=discord.File(buffer, 'current_quests.png'))

@bot.command(name='claim')
async def claim_quest(ctx, quest_name: str, proof_link: str = None):
    quest_name = quest_name.lower()
    quest_data = get_quest_data()
    if quest_name not in quest_data:
        valid_quests = ", ".join(QUEST_COORDINATES.keys())
        await ctx.send(f"'{quest_name}' is not a valid quest name. Valid quests are: {valid_quests}")
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
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith('image/'):
            embed.set_image(url=attachment.url)
        else:
            embed.add_field(name="Proof Attachment", value=f"[{attachment.filename}]({attachment.url})", inline=False)
    elif proof_link:
        embed.add_field(name="Proof Link", value=proof_link, inline=False)
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
        if any(ext in proof_link.lower() for ext in image_extensions):
            embed.set_image(url=proof_link)
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
    default_data = {name: {"status": "unclaimed", "claimer_id": None, "claimer_name": None} for name in QUEST_COORDINATES.keys()}
    save_quest_data(default_data)
    await ctx.send("✅ All quests have been reset.")
    buffer = generate_quest_image()
    await ctx.send("The quest board is now clean:", file=discord.File(buffer, 'current_quests.png'))

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id or payload.channel_id != ADMIN_CHANNEL_ID: return
    channel = bot.get_channel(payload.channel_id)
    try: message = await channel.fetch_message(payload.message_id)
    except discord.NotFound: return
    if not message.embeds or message.author.id != bot.user.id or "Pending" not in message.embeds[0].title: return
    reactor = payload.member
    if not reactor or not reactor.guild_permissions.manage_guild: return
    embed = message.embeds[0]
    quest_name = next((field.value for field in embed.fields if field.name == "Quest"), None)
    claimer_id = int(embed.footer.text.replace("Claimer ID: ", ""))
    claimer = payload.member.guild.get_member(claimer_id)
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
    elif str(payload.emoji) == "❌":
        quest_data[quest_name]['status'] = 'unclaimed'
        quest_data[quest_name]['claimer_id'] = None
        quest_data[quest_name]['claimer_name'] = None
        save_quest_data(quest_data)
        if announcement_channel:
            denial_msg = f"ℹ️ The claim for **{quest_name}** by {claimer.mention if claimer else f'User ID {claimer_id}'} was denied. The quest is now open!"
            new_image_buffer = generate_quest_image()
            await announcement_channel.send(denial_msg, file=discord.File(new_image_buffer, 'current_quests.png'))
        new_embed = embed.copy(); new_embed.title = "❌ Quest Claim Denied"; new_embed.color = discord.Color.red()
        new_embed.add_field(name="Moderator", value=reactor.mention)
        await message.edit(embed=new_embed); await message.clear_reactions()

@claim_quest.error
async def claim_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!claim <quest_name> [replay_link]`")

def run_bot():
    if TOKEN:
        try: bot.run(TOKEN)
        except discord.errors.LoginFailure: print("FATAL ERROR: Invalid Discord token.")
        except Exception as e: print(f"An unexpected error occurred: {e}")
    else:
        print("FATAL ERROR: DISCORD_TOKEN not found in environment variables.")

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    run_bot()
