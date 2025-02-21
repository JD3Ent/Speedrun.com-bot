import discord
from discord.ext import commands
import requests
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

# Function to handle API rate limits
async def fetch_with_rate_limit(url):
    while True:
        response = requests.get(url)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))  # Default to 5 sec if not provided
            print(f"⚠️ Rate-limited! Retrying in {retry_after} seconds...")
            await asyncio.sleep(retry_after)
        else:
            return response

# Function to fetch categories for a game (cached)
async def fetch_categories(game_id):
    if game_id in CATEGORY_CACHE:
        return CATEGORY_CACHE[game_id]

    response = await fetch_with_rate_limit(f"{SPEEDRUN_API_URL}/games/{game_id}/categories")
    if response.status_code != 200:
        return {}

    categories = response.json().get("data", [])
    CATEGORY_CACHE[game_id] = {cat["name"].lower(): cat["id"] for cat in categories}
    return CATEGORY_CACHE[game_id]

# Command to list available categories for a game
@bot.command()
async def categories(ctx, game: str):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    categories = await fetch_categories(game_id)
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

    categories = await fetch_categories(game_id)
    category_id = categories.get(category.lower())
    if not category_id:
        await ctx.send("❌ Invalid category! Use `/categories [game]` to see valid options.")
        return

    try:
        top_count = 5 if top.lower() == "top5" else 1
        response = await fetch_with_rate_limit(f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/category/{category_id}?top={top_count}")
        
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

    except requests.exceptions.RequestException:
        await ctx.send("❌ Failed to fetch data due to API limits. Try again later.")

# Function to fetch all runners for a game (cached)
async def fetch_runners(game_id):
    if game_id in RUNNERS_CACHE:
        return RUNNERS_CACHE[game_id]

    response = await fetch_with_rate_limit(f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/categories")
    if response.status_code != 200:
        return None

    categories = response.json()["data"]
    runner_ids = set()

    for category in categories:
        leaderboard_url = f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/category/{category['id']}"
        leaderboard_response = await fetch_with_rate_limit(leaderboard_url)
        if leaderboard_response.status_code == 200:
            runs = leaderboard_response.json()["data"]["runs"]
            for run in runs:
                for player in run["run"]["players"]:
                    if player["rel"] == "user":
                        runner_ids.add(player["id"])

    runners = []
    for runner_id in runner_ids:
        user_response = await fetch_with_rate_limit(f"{SPEEDRUN_API_URL}/users/{runner_id}")
        if user_response.status_code == 200:
            user_data = user_response.json()["data"]
            runners.append(user_data["names"]["international"])

    RUNNERS_CACHE[game_id] = runners  # Cache runners
    return runners

# Command to list all runners for a game
@bot.command()
async def runners(ctx, game: str):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    runners = await fetch_runners(game_id)
    if not runners:
        await ctx.send("❌ No runners found for this game.")
        return

    await ctx.send(f"🏁 **Speedrunners for {game.upper()}**:\n{', '.join(runners)}\n\nTotal Runners: {len(runners)}")

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