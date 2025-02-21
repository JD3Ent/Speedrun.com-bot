import discord
from discord.ext import commands
import aiohttp
import os
import asyncio

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

# Bot setup with necessary intents
intents = discord.Intents.default()
intents.message_content = True  # Enables message reading
bot = commands.Bot(command_prefix="/", intents=intents)

# API Caching to avoid excessive requests
CATEGORY_CACHE = {}
RUNNERS_CACHE = {}

# Function to handle API rate limits using aiohttp
async def fetch_with_rate_limit(session, url):
    while True:
        async with session.get(url) as response:
            if response.status == 429:
                retry_after = int(response.headers.get("Retry-After", 5))  # Default to 5 sec if not provided
                print(f"⚠️ Rate-limited! Retrying in {retry_after} seconds...")
                await asyncio.sleep(retry_after)
            else:
                return await response.json()

# Function to fetch categories for a game (cached)
async def fetch_categories(session, game_id):
    if game_id in CATEGORY_CACHE:
        return CATEGORY_CACHE[game_id]

    url = f"{SPEEDRUN_API_URL}/games/{game_id}/categories"
    data = await fetch_with_rate_limit(session, url)
    if "data" not in data:
        return {}

    categories = {cat["name"].lower(): cat["id"] for cat in data["data"]}
    CATEGORY_CACHE[game_id] = categories
    return categories

# Command to list available categories for a game
@bot.command()
async def categories(ctx, game: str):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    async with aiohttp.ClientSession() as session:
        categories = await fetch_categories(session, game_id)

    if not categories:
        await ctx.send("❌ No categories found for this game.")
        return

    category_list = "\n".join([f"🔹 {name}" for name in categories.keys()])
    await ctx.send(f"**Available Categories for {game.upper()}**:\n{category_list}")

# Command to fetch WR or Top 5 runs (Rate-limiting safe)
@bot.command()
async def speedrun(ctx, category: str, game: str, top: str = "1"):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use `/categories [game]` to see valid options.")
        return

    async with aiohttp.ClientSession() as session:
        categories = await fetch_categories(session, game_id)
        category_id = categories.get(category.lower())

        if not category_id:
            await ctx.send("❌ Invalid category! Use `/categories [game]` to see valid options.")
            return

        top_count = 5 if top.lower() == "top5" else 1
        url = f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/category/{category_id}?top={top_count}"
        data = await fetch_with_rate_limit(session, url)

        if "data" not in data or "runs" not in data["data"]:
            await ctx.send("❌ No runs found for this category.")
            return

        runs = data["data"]["runs"]
        message = f"**Top {top_count} {category.upper()} Runs for {game.upper()}**\n"

        for i, run in enumerate(runs[:top_count]):
            player = run["run"]["players"][0].get("name", "Unknown")
            time = run["run"]["times"]["primary_t"]
            video = run["run"].get("videos", {}).get("links", [{"uri": "No video"}])[0]["uri"]

            message += f"**#{i+1} - {player}**\n🏁 Time: {time}\n🎥 Video: {video}\n\n"

        await ctx.send(message)

# Command to test if bot is online
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! Bot is running!")

# Auto-reconnect logic to prevent bot crashes
async def reconnect_bot():
    while True:
        try:
            await bot.start(TOKEN)
        except discord.HTTPException as e:
            if e.status == 429:
                print("Rate limit exceeded. Waiting before retrying...")
                await asyncio.sleep(30)  # Wait before reconnecting
            else:
                raise

# Run bot with auto-reconnect
asyncio.run(reconnect_bot())