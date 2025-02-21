import discord
from discord.ext import commands
import requests
import os

# Load Bot Token from Render environment variables
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Speedrun.com API Base URL
SPEEDRUN_API_URL = "https://www.speedrun.com/api/v1"

# Midnight Club Game IDs
GAME_IDS = {
    "mc3remix": "midnight_club_3_dub_edition_remix",
    "mc3dub": "midnight_club_3_dub_edition",
    "mc2": "mc2",
    "mc1": "midnight_club_street_racing",
    "mcla": "midnight_club_los_angeles",
    "mcla_remix": "midnight_club_los_angeles_remix"
}

# Bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# Command to test if the bot is running
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! Bot is running!")

# Command to list available categories for a game
@bot.command()
async def categories(ctx, game: str):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    response = requests.get(f"{SPEEDRUN_API_URL}/games/{game_id}/categories")
    if response.status_code != 200:
        await ctx.send("❌ Failed to fetch categories.")
        return

    categories = response.json().get("data", [])
    if not categories:
        await ctx.send("❌ No categories found for this game.")
        return

    category_list = "\n".join([f"🔹 {cat['name']}" for cat in categories])
    await ctx.send(f"**Available Categories for {game.upper()}**:\n{category_list}")

# Command to fetch WR or Top 5 runs
@bot.command()
async def speedrun(ctx, category: str, game: str, top: str = "1"):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use `/categories [game]` to see valid options.")
        return

    response = requests.get(f"{SPEEDRUN_API_URL}/games/{game_id}/categories")
    if response.status_code != 200:
        await ctx.send("❌ Failed to fetch categories.")
        return

    categories = {cat["name"].lower(): cat["id"] for cat in response.json().get("data", [])}
    category_id = categories.get(category.lower())
    if not category_id:
        await ctx.send("❌ Invalid category! Use `/categories [game]` to see valid options.")
        return

    top_count = 5 if top.lower() == "top5" else 1
    response = requests.get(f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/category/{category_id}?top={top_count}")

    if response.status_code != 200 or "data" not in response.json():
        await ctx.send("❌ No runs found for this category.")
        return

    runs = response.json()["data"]["runs"]
    message = f"**Top {top_count} {category.upper()} Runs for {game.upper()}**\n"

    for i, run in enumerate(runs[:top_count]):
        player = run["run"]["players"][0].get("name", "Unknown")
        time = run["run"]["times"]["primary_t"]
        video = run["run"].get("videos", {}).get("links", [{"uri": "No video"}])[0]["uri"]

        message += f"**#{i+1} - {player}**\n🏁 Time: {time}\n🎥 Video: {video}\n\n"

    await ctx.send(message)

# Run the bot
bot.run(TOKEN)
