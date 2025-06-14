import os
import discord
from discord.ext import commands
import asyncio
from discord.ext.commands import CheckFailure
from flask import Flask
from threading import Thread

# === CONFIG (IDs are hardcoded as requested) ===
TOKEN = "YOUR_BOT_TOKEN_HERE" # <--- IMPORTANT: PASTE YOUR BOT TOKEN HERE
SHARK_ROLE_ID = 1383481768618758205
APPROVAL_CHANNEL_ID = 1382357500661207170

# === DISCORD SETUP ===
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


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
    await approval_channel.send(embed=embed, view=ApprovalView())

    confirmation_embed = discord.Embed(title="✅ Anfrage zur Überprüfung eingereicht", description=f"Die Anfrage für die **Shark Rolle** für den Benutzer {member.mention} wurde erfolgreich an das Team weitergeleitet.", color=discord.Color.green())
    confirmation_embed.add_field(name="Eingereichte Bitunix UID", value=f"`{bitunix_uid}`", inline=False)
    confirmation_embed.add_field(name="Eingereicht von", value=ctx.author.mention, inline=False)
    confirmation_embed.set_footer(text="Das Team wird dies in Kürze überprüfen.")
    
    await ctx.send(embed=confirmation_embed)
    await ctx.message.delete()


# === FLASK SERVER ===
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running.", 200

def run_webserver():
    # Use the PORT environment variable provided by the hosting service.
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# === MAIN ENTRY ===
if __name__ == "__main__":
    # Start Flask in a separate thread
    web_thread = Thread(target=run_webserver, daemon=True)
    web_thread.start()

    # Run the bot
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("!!! FATAL ERROR: Please paste your bot token into the script. !!!")
    else:
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("!!! FATAL ERROR: Login failed. Make sure your bot token is correct. !!!")
