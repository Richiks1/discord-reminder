import os
import discord
from discord.ext import commands, tasks
import sqlite3
from datetime import datetime, timedelta, timezone
from google.cloud import storage
from threading import Thread
from flask import Flask
import asyncio
from discord.ext.commands import CheckFailure

# === CONFIG ===
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ROLE_ID = int(os.getenv("ROLE_ID", "1375604541726392412"))
TARGET_ROLE_ID = 1362484571509231662
LOG_CHANNEL_ID = 1362484572029190177
REMINDER_CHANNEL_ID = int(os.getenv("REMINDER_CHANNEL_ID", "0"))
DB_PATH = "data.db"
# --- SHARK ROLE WORKFLOW CONFIG ---
SHARK_ROLE_ID = 1383481768618758205
APPROVAL_CHANNEL_ID = 1382357500661207170

# === GCS SETUP ===
bucket = None
def init_google_storage():
    global bucket
    try:
        client = storage.Client()
        bucket_name = os.environ.get("GCS_BUCKET_NAME")
        if not bucket_name:
            print("[Warning] GCS_BUCKET_NAME not set. GCS features will be disabled.")
            return
        bucket = client.bucket(bucket_name)
    except Exception as e:
        print(f"[Error] Failed to initialize Google Cloud Storage: {e}")

def upload_db():
    if not bucket: return
    try:
        blob = bucket.blob(os.environ.get("GCS_DB_OBJECT", "data.db"))
        blob.upload_from_filename(DB_PATH)
        print("[GCS] DB uploaded")
    except Exception as e:
        print(f"[Error] Failed to upload DB to GCS: {e}")

def download_db():
    if not bucket: return
    try:
        blob = bucket.blob(os.environ.get("GCS_DB_OBJECT", "data.db"))
        if blob.exists():
            blob.download_to_filename(DB_PATH)
            print("[GCS] DB downloaded")
        else:
            print("[GCS] No DB found, will create new.")
    except Exception as e:
        print(f"[Error] Failed to download DB from GCS: {e}")

# === DISCORD SETUP ===
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# === SQLITE SETUP ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS role_assignments (user_id INTEGER PRIMARY KEY, timestamp TEXT)""")
    conn.commit()
    conn.close()

def assign_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO role_assignments VALUES (?, ?)", (user_id, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_expired_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cutoff = datetime.utcnow() - timedelta(days=5)
    c.execute("SELECT user_id FROM role_assignments WHERE timestamp <= ?", (cutoff.isoformat(),))
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def remove_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM role_assignments WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

### === TICKET & APPROVAL VIEWS === ###
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Giveaway", style=discord.ButtonStyle.secondary, emoji="🎁", custom_id="ticket:giveaway")
    async def giveaway_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway_text = ("Das Team von Henry wünscht Dir hiermit Herzlichen Glückwunsch zum Gewinn von 50 USDT! 🎉\n\nWir brauchen von Dir folgende Details, um Dir Deinen Gewinn so schnell wie möglich zukommen zu lassen.\n\n✅ Deine Bitunix User ID (Account über Henry's Link)\n✅ Deine USDT Einzahlungs-Adresse (Tron Netzwerk)\n✅ Einen Screenshot auf dem Deine Einzahlungs-Addresse + QR Code klar ersichtlich ist\n\n🎉 Fertig!")
        await interaction.response.send_message(giveaway_text, ephemeral=True)

    @discord.ui.button(label="Bonus", style=discord.ButtonStyle.success, emoji="💰", custom_id="ticket:bonus")
    async def bonus_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bonus_text = ("Hey, vielen Dank für Dein Ticket. Wir versuchen so schnell wie möglich Dein Anliegen zu bearbeiten.\n\nWir brauchen von Dir folgende Details, um Deinen Fall so schnell wie möglich zu bearbeiten:\n\n➡️ Deine Bitunix User ID\n➡️ Wann hast Du Deine Einzahlung getätigt? (Datum, Uhrzeit)\n➡️ Dein genauer Betrag, den Du eingezahlt hast\n\nNach erhalt der Informationen bearbeiten wir umgehend Deinen Fall!")
        await interaction.response.send_message(bonus_text, ephemeral=True)

    @discord.ui.button(label="Shark Rolle", style=discord.ButtonStyle.secondary, emoji="🦈", custom_id="ticket:shark_role")
    async def shark_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid_text = ("Danke, wir werden das schnellstmöglich überprüfen und dir dann die Rolle zuweisen.\n\nWir brauchen von dir folgendes Details, um Deinen Fall so schnell wie möglich zu bearbeiten:\n➡️ Deine Bitunix User ID")
        await interaction.response.send_message(uid_text, ephemeral=True)

    @discord.ui.button(label="Anleitung", style=discord.ButtonStyle.secondary, emoji="📖", custom_id="ticket:instructions")
    async def instructions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        instructions_text = ("➡️ **So siehst Du Deine Bitunix UID**\n✅ Oben Rechts im Layout von Bitunix mit dem Mauszeiger auf Dein Profilbild navigieren. Nun siehst Du deine Bitunix User ID\n\n➡️ **Wo Du Deine Einzahlungsadresse findest**\n1️⃣ Navigiere in Bitunix auf deine Vermögensübersicht, indem Du auf das \"Brieftaschen-Symbol\" klickst, das oben rechts immer zu finden ist.\n2️⃣ Klicke links im Feld auf \"Einzahlen\"\n3️⃣ Wähle nun den USDT Coin aus und das TRON (TRC-20) Netzwerk.\n✅ Jetzt send nur noch ein Screenshot davon und eine Kopie der Einzahlungsadresse als Text.")
        await interaction.response.send_message(instructions_text, ephemeral=True)

    @discord.ui.button(label="Other Issue", style=discord.ButtonStyle.danger, emoji="❓", custom_id="ticket:other")
    async def other_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        other_text = "Bitte beschreibe dein Anliegen detailliert. Ein Teammitglied wird sich in Kürze bei dir melden."
        await interaction.response.send_message(other_text, ephemeral=True)

class ApprovalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def handle_decision(self, interaction: discord.Interaction, decision: str):
        original_embed = interaction.message.embeds[0]
        footer_text = original_embed.footer.text
        parts = {p.split(': ')[0]: p.split(': ')[1] for p in footer_text.split(' | ')}
        member_id = int(parts["Member"])
        ticket_channel_id = int(parts["Ticket"])
        
        guild = interaction.guild
        member = guild.get_member(member_id)
        ticket_channel = guild.get_channel(ticket_channel_id)
        shark_role = guild.get_role(SHARK_ROLE_ID)

        if not member or not ticket_channel or not shark_role:
            await interaction.response.send_message("❌ Error: Could not find user, ticket channel, or Shark Role.", ephemeral=True)
            return

        new_embed = original_embed
        new_embed.color = discord.Color.green() if decision == "Approved" else discord.Color.red()
        new_embed.set_field_at(0, name="Status", value=f"**{decision} by {interaction.user.mention}**", inline=False)
        
        for item in self.children:
            item.disabled = True
        
        await interaction.message.edit(embed=new_embed, view=self)

        if decision == "Approved":
            try:
                await member.add_roles(shark_role, reason=f"Approved by {interaction.user.name}")
                success_embed = discord.Embed(title="✅ Anfrage genehmigt", description=f"Hallo {member.mention}, deine Anfrage für die **{shark_role.name}** wurde genehmigt!\n\nDie Rolle wurde dir soeben zugewiesen.", color=discord.Color.green())
                await ticket_channel.send(embed=success_embed)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Error: I don't have permissions to assign the Shark Role.", ephemeral=True)
                return
        else:
            denial_embed = discord.Embed(title="❌ Anfrage abgelehnt", description=f"Hallo {member.mention}, deine Anfrage für die **{shark_role.name}** wurde leider abgelehnt.\n\nEin Teammitglied wird sich in Kürze im Ticket bei dir melden, um dir die Gründe mitzuteilen.", color=discord.Color.red())
            await ticket_channel.send(embed=denial_embed)
        
        await interaction.response.send_message(f"Decision '{decision}' logged.", ephemeral=True)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅", custom_id="approve_request")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_decision(interaction, "Approved")
        
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="deny_request")
    async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_decision(interaction, "Denied")

# === DISCORD EVENTS ===
@bot.event
async def on_ready():
    bot.add_view(TicketView())
    bot.add_view(ApprovalView())
    print(f"✅ Logged in as {bot.user}")
    print(f'✅ Panel posting for new tickets is active.')
    remove_expired_roles.start()
    autosave_db.start()
    send_reminder_task.start()

@bot.event
async def on_member_join(member):
    role = member.guild.get_role(ROLE_ID)
    if role:
        await member.add_roles(role)
        assign_user(member.id)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            timestamp = int((datetime.utcnow() + timedelta(days=5)).timestamp())
            await log_channel.send(f"✅ Gave {member.mention} the **Newcomer** role. Expires <t:{timestamp}:R>.")

@bot.event
async def on_guild_channel_create(channel):
    if isinstance(channel, discord.TextChannel) and channel.name.startswith("🎫┃"):
        await asyncio.sleep(1.5)
        member = None
        for target, overwrite in channel.overwrites.items():
            if isinstance(target, discord.Member) and overwrite.read_messages:
                member = target
                break
        if not member: return
        embed = discord.Embed(description=f"👋 **Hallo {member.mention}!**\n\nWie können wir dir heute helfen? Bitte wähle eine der folgenden Optionen aus, um loszulegen.", color=0x3498db)
        try:
            await channel.send(embed=embed, view=TicketView())
        except discord.Forbidden:
            print(f"Could not send panel to {channel.name}. Missing permissions.")

@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        added_roles = [r for r in after.roles if r not in before.roles]
        for role in added_roles:
            if role.id == TARGET_ROLE_ID:
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    await asyncio.sleep(2)
                    async for entry in after.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_role_update):
                        if (entry.target.id == after.id and (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 10 and role in entry.after.roles):
                            giver = entry.user
                            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                            await log_channel.send(f"📌 <@{after.id}> was given the **{role.name}** role by `{giver}` on `{timestamp}`.")
                            return
                    await log_channel.send(f"📌 <@{after.id}> was given the **{role.name}** role *(could not identify who assigned it)*.")

@bot.event
async def on_disconnect():
    print("[Bot] Disconnected. Uploading DB to GCS...")
    upload_db()

# === TASKS ===
@tasks.loop(hours=1)
async def remove_expired_roles():
    guild = bot.guilds[0] if bot.guilds else None
    if not guild: return
    expired_ids = get_expired_users()
    for user_id in expired_ids:
        member = guild.get_member(user_id)
        if member:
            role = guild.get_role(ROLE_ID)
            if role and role in member.roles:
                await member.remove_roles(role)
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel: await log_channel.send(f"❌ Removed **Newcomer** role from {member.mention} (5 days passed)")
        remove_user(user_id)

@tasks.loop(hours=1)
async def autosave_db():
    print("[AutoSave] Uploading DB...")
    upload_db()

@tasks.loop(hours=6)
async def send_reminder_task():
    channel = bot.get_channel(REMINDER_CHANNEL_ID)
    if channel:
        await channel.send("⚠️ **VORSICHT VOR BETRÜGERN** ⚠️\n\nEs kann sein das ihr von einem „Henry Frempong“ hier auf Discord eine Freundschaftsanfrage erhaltet. **Das bin nicht ich!!!** \n\nIch schicke euch niemals eine Anfrage oder eine DM!\n\nVielen Dank 🫡\n\n")
    else:
        print(f"❌ Reminder channel with ID {REMINDER_CHANNEL_ID} not found!")

@send_reminder_task.before_loop
async def before_reminder():
    await bot.wait_until_ready()

# === COMMANDS & PERMISSIONS ===
def is_mod_or_owner():
    async def predicate(ctx):
        # Using manage_guild as a proxy for "moderator" permissions
        return ctx.author.guild_permissions.manage_guild or await bot.is_owner(ctx.author)
    return commands.check(predicate)

@bot.command(name="uid")
@is_mod_or_owner()
async def uid(ctx, member: discord.Member, bitunix_uid: str):
    """Submits a user's Bitunix UID for role approval."""
    approval_channel = bot.get_channel(APPROVAL_CHANNEL_ID)
    if not approval_channel:
        await ctx.send(f"❌ Error: The approval channel with ID `{APPROVAL_CHANNEL_ID}` was not found.", ephemeral=True)
        return

    approval_embed = discord.Embed(title="🦈 Shark Rolle Anfrage", color=discord.Color.blue())
    approval_embed.add_field(name="Status", value="**Pending Review**", inline=False)
    approval_embed.add_field(name="Benutzer", value=f"{member.mention} `({member.id})`", inline=True)
    approval_embed.add_field(name="Bitunix UID", value=f"`{bitunix_uid}`", inline=True)
    approval_embed.add_field(name="Anfrage von", value=ctx.author.mention, inline=False)
    approval_embed.set_footer(text=f"Member: {member.id} | Ticket: {ctx.channel.id} | UID: {bitunix_uid}")
    await approval_channel.send(embed=approval_embed, view=ApprovalView())

    confirmation_embed = discord.Embed(title="✅ Anfrage zur Überprüfung eingereicht", description=f"Die Anfrage für die **Shark Rolle** für den Benutzer {member.mention} wurde erfolgreich an das Team weitergeleitet.", color=discord.Color.green())
    confirmation_embed.add_field(name="Eingereichte Bitunix UID", value=f"`{bitunix_uid}`", inline=False)
    confirmation_embed.add_field(name="Eingereicht von", value=ctx.author.mention, inline=False)
    confirmation_embed.set_footer(text="Das Team wird dies in Kürze überprüfen.")
    
    await ctx.send(embed=confirmation_embed)
    await ctx.message.delete()

# Keep old commands for manual mod use, if desired.
# ... (giveaway, bonus, role, info commands and their error handlers) ...

# === FLASK SERVER & MAIN ENTRY ===
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running.", 200

def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("!!! FATAL ERROR: Please replace 'YOUR_BOT_TOKEN_HERE' in the script with your actual bot token. !!!")
    else:
        init_google_storage()
        download_db()
        init_db()
        web_thread = Thread(target=run_webserver, daemon=True)
        web_thread.start()
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("!!! FATAL ERROR: Login failed. Make sure your bot token is correct. !!!")
        finally:
            print("[Bot] Shutting down. Uploading DB to GCS one last time...")
            upload_db()
