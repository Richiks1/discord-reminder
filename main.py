import os
import discord
from discord.ext import tasks
from flask import Flask
from threading import Thread

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# Flask web server for UptimeRobot pings
app = Flask('')

@app.route('/')
def home():
    return 'I am alive', 200

def run():
    app.run(host='0.0.0.0', port=8080)

# Start Flask server in a separate thread
Thread(target=run).start()

# Discord bot events
@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')
    send_reminder.start()

@tasks.loop(hours=6)  # Reminder every 6 hours
async def send_reminder():
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        # Send the reminder message with @everyone on its own line
        await channel.send(
            "@everyone\n"
            "Owner and moderators will **never DM you first**.\n"
            "If you need support, please use the #tickets channel.\n"
            "Stay safe and avoid scams!"
        )
        # Send the image attachment (make sure reminder_image.png is in your project folder)
        try:
            with open("zzz.png", "rb") as image:
                file = discord.File(image)
                await channel.send(file=file)
        except FileNotFoundError:
            print("❌ reminder_image.png not found!")
    else:
        print("❌ Channel not found!")

# Run the bot
client.run(TOKEN)
