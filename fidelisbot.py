import json
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

import csv
import io
import requests
# ================= CONFIG =================
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN was not loaded. Check your .env file.")

GUILD_ID = 1432717420119720018
WELCOME_CHANNEL_ID = 1482409362248040579

UNVERIFIED_ROLE_NAME = "Peasant"
CLAN_ROLE_NAME = "Fidelis"
GUEST_ROLE_NAME = "Infidels"

SPREADSHEET_ID = "1GKaWcZ26xl0O3cjNbCM_AfyE-Ze9RMWLMrtH5YzPb3o"
WORKSHEET_GID = "0"
# ==========================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ===== Load clan names =====
def load_clan_names():
    try:
        csv_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={WORKSHEET_GID}"
        response = requests.get(csv_url, timeout=10)
        response.raise_for_status()

        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)

        if not rows:
            return {}

        clan_names = {}

        # Skip header row if present
        start_index = 1 if rows and rows[0] else 0

        for row in rows[start_index:]:
            # Column A = index 0
            if len(row) > 0:
                name_a = row[0].strip()
                if name_a:
                    clan_names[name_a.lower()] = name_a

            # Column D = index 3
            if len(row) > 3:
                name_d = row[3].strip()
                if name_d:
                    clan_names[name_d.lower()] = name_d

        return clan_names

    except requests.RequestException as e:
        print(f"Failed to load clan names from Google Sheet: {e}")
        return {}
    except Exception as e:
        print(f"Unexpected error while loading clan names: {e}")
        return {}
#===== Check if name is already verified =====
def is_name_already_verified(guild: discord.Guild, name_to_check: str, current_member_id: int) -> bool:
    clan_role = discord.utils.get(guild.roles, name=CLAN_ROLE_NAME)
    if clan_role is None:
        return False

    target = name_to_check.strip().lower()

    for member in clan_role.members:
        if member.id == current_member_id:
            continue
        
        current_name = (member.nick or member.name).strip().lower()
        if current_name == target:
            return True

    return False


# ===== Modal for IGN input =====
class ClanNameModal(discord.ui.Modal, title="Clan Verification"):
    ign = discord.ui.TextInput(
        label="What is your in-game name?",
        placeholder="Enter your exact in-game name",
        max_length=32
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Error: this must be used inside the server.",
                ephemeral=True
            )
            return

        clan_names = load_clan_names()

        ign_input = str(self.ign).strip()
        ign_lookup = ign_input.lower()

        clan_role = discord.utils.get(guild.roles, name=CLAN_ROLE_NAME)
        guest_role = discord.utils.get(guild.roles, name=GUEST_ROLE_NAME)
        unverified_role = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)

        if ign_lookup not in clan_names:
            await interaction.response.send_message(
                "❌ Name not found in clan list. Contact a moderator if this is a mistake.",
                ephemeral=True
            )
            return

        correct_name = clan_names[ign_lookup]

        if is_name_already_verified(guild, correct_name, member.id):
            await interaction.response.send_message(
                f"❌ The name **{correct_name}** is already being used by another verified **{CLAN_ROLE_NAME}** member. Please contact a moderator.",
                ephemeral=True
            )
            return

        try:
            if guest_role and guest_role in member.roles:
                await member.remove_roles(guest_role, reason="Verified clan member")

            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="Verified clan member")

            if clan_role and clan_role not in member.roles:
                await member.add_roles(clan_role, reason="Verified clan member")

            await member.edit(
                nick=correct_name,
                reason="Set nickname to verified in-game name"
            )

            await interaction.response.send_message(
                f"✅ Verified! You have been given the **{CLAN_ROLE_NAME}** role and your nickname was set to **{correct_name}**.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "✅ Verified role assigned, but I could not change your nickname. Make sure my role is above yours and I have Manage Nicknames.",
                ephemeral=True
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "✅ Verified role assigned, but something went wrong while changing your nickname.",
                ephemeral=True
            )


# ===== Verification buttons =====
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Yes, I am a clan member",
        style=discord.ButtonStyle.success,
        custom_id="verify_yes"
    )
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        guild = interaction.guild

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Error occurred.",
                ephemeral=True
            )
            return

        clan_role = discord.utils.get(guild.roles, name=CLAN_ROLE_NAME)
        guest_role = discord.utils.get(guild.roles, name=GUEST_ROLE_NAME)

        if clan_role and clan_role in member.roles:
            await interaction.response.send_message(
                "You are already verified as a clan member.",
                ephemeral=True
            )
            return

        if guest_role and guest_role in member.roles:
            await interaction.response.send_message(
                "You are already verified as a guest.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(ClanNameModal())

    @discord.ui.button(
        label="No, I am not a clan member",
        style=discord.ButtonStyle.secondary,
        custom_id="verify_no"
    )
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Error occurred.",
                ephemeral=True
            )
            return

        clan_role = discord.utils.get(guild.roles, name=CLAN_ROLE_NAME)
        guest_role = discord.utils.get(guild.roles, name=GUEST_ROLE_NAME)
        unverified_role = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)

        if clan_role and clan_role in member.roles:
            await interaction.response.send_message(
                "You are already verified as a clan member.",
                ephemeral=True
            )
            return

        if guest_role and guest_role in member.roles:
            await interaction.response.send_message(
                "You are already verified as a guest.",
                ephemeral=True
            )
            return

        try:
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="Not a clan member")

            if guest_role and guest_role not in member.roles:
                await member.add_roles(guest_role, reason="Guest")

            await interaction.response.send_message(
                f"You’ve been assigned the **{GUEST_ROLE_NAME}** role.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don’t have permission to update your roles. Check my role position and permissions.",
                ephemeral=True
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Something went wrong while assigning your role.",
                ephemeral=True
            )


# ===== Bot Ready =====
@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    print(f"Logged in as {bot.user}")


# ===== On Join =====
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild

    if guild.id != GUILD_ID:
        return

    unverified_role = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)
    if unverified_role:
        try:
            await member.add_roles(unverified_role, reason="New member")
        except discord.Forbidden:
            print("Missing permission to assign unverified role.")
        except discord.HTTPException:
            print("Failed to assign unverified role.")


# ===== Admin command to post permanent verification panel =====
@bot.command()
@commands.has_permissions(administrator=True)
async def setupverify(ctx):
    if ctx.guild is None or ctx.guild.id != GUILD_ID:
        await ctx.send("This command can only be used in the target server.")
        return

    await ctx.send(
        "Are you a member of the clan?",
        view=VerifyView()
    )


# ===== Optional admin command to post panel in welcome channel =====
@bot.command()
@commands.has_permissions(administrator=True)
async def setupverifychannel(ctx):
    if ctx.guild is None or ctx.guild.id != GUILD_ID:
        await ctx.send("This command can only be used in the target server.")
        return

    channel = ctx.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel is None:
        await ctx.send("Welcome channel not found.")
        return

    await channel.send(
        "Are you a member of the clan?",
        view=VerifyView()
    )
    await ctx.send("Verification panel posted.")


# ===== Error handler for missing admin permission ===== 
@setupverify.error
@setupverifychannel.error
async def admin_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need administrator permission to use this command.")

# ===== call points ===== #
def load_clan_points():
    try:
        csv_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={WORKSHEET_GID}"
        response = requests.get(csv_url, timeout=10)
        response.raise_for_status()

        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)

        if not rows:
            return {}

        points_map = {}

        header_values = {cell.strip().lower() for cell in rows[0]} if rows else set()
        start_index = 1 if {"name", "ign", "in-game name", "points"} & header_values else 0

        for row in rows[start_index:]:
            # A/B pair
            if len(row) > 1:
                name_a = row[0].strip()
                points_a = row[1].strip()

                if name_a:
                    points_map[name_a.lower()] = {
                        "name": name_a,
                        "points": points_a if points_a else "0"
                    }

            # D/E pair
            if len(row) > 4:
                name_d = row[3].strip()
                points_d = row[4].strip()

                if name_d:
                    points_map[name_d.lower()] = {
                        "name": name_d,
                        "points": points_d if points_d else "0"
                    }

        return points_map

    except requests.RequestException as e:
        print(f"Failed to load clan points from Google Sheet: {e}")
        return {}
    except Exception as e:
        print(f"Unexpected error while loading clan points: {e}")
        return {}
    
@bot.command()
async def points(ctx, *, name=None):
    points_map = load_clan_points()

    if name is None:
        # fallback to nickname, then username
        target_name = ctx.author.nick if ctx.author.nick else ctx.author.name
    else:
        target_name = name.strip()

    lookup = target_name.lower()

    if lookup not in points_map:
        await ctx.send(f"❌ Could not find points for **{target_name}**.")
        return

    entry = points_map[lookup]
    await ctx.send(f"**{entry['name']}** has **{entry['points']}** points.")
# ===== Run bot =====
bot.run(TOKEN)