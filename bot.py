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

# Function to fetch all runners for a game (cached)
async def fetch_runners(session, game_id):
    if game_id in RUNNERS_CACHE:
        return RUNNERS_CACHE[game_id]

    url = f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/categories"
    data = await fetch_with_rate_limit(session, url)

    if "data" not in data:
        return None

    categories = data["data"]
    runner_ids = set()

    for category in categories:
        leaderboard_url = f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/category/{category['id']}"
        leaderboard_data = await fetch_with_rate_limit(session, leaderboard_url)

        if "data" in leaderboard_data:
            runs = leaderboard_data["data"]["runs"]
            for run in runs:
                for player in run["run"]["players"]:
                    if player["rel"] == "user":
                        runner_ids.add(player["id"])

    runners = []
    for runner_id in runner_ids:
        user_url = f"{SPEEDRUN_API_URL}/users/{runner_id}"
        user_data = await fetch_with_rate_limit(session, user_url)

        if "data" in user_data:
            runners.append(user_data["data"]["names"]["international"])

    RUNNERS_CACHE[game_id] = runners  # Cache runners
    return runners

# Function to fetch a specific runner's profile
async def fetch_runner_profile(session, runner_name):
    url = f"{SPEEDRUN_API_URL}/users?lookup={runner_name}"
    data = await fetch_with_rate_limit(session, url)

    if not data.get("data"):
        return None

    user_data = data["data"][0]
    user_id = user_data["id"]
    user_url = user_data["weblink"]

    # Fetch the runs for this runner
    runs_url = f"{SPEEDRUN_API_URL}/runs?user={user_id}"
    runs_data = await fetch_with_rate_limit(session, runs_url)

    runs = runs_data.get("data", [])
    run_list = []

    for run in runs:
        game_id = run["game"]
        game_name = next((name for name, gid in GAME_IDS.items() if gid == game_id), "Unknown Game")
        category_id = run["category"]
        category_data = await fetch_with_rate_limit(session, f"{SPEEDRUN_API_URL}/categories/{category_id}")

        category_name = category_data.get("data", {}).get("name", "Unknown Category")
        time = run["times"]["primary_t"]
        video = run.get("videos", {}).get("links", [{"uri": "No video"}])[0]["uri"]

        run_list.append(f"🏁 **{game_name} - {category_name}**\n⏱️ Time: {time}\n🎥 Video: {video}\n")

    return user_data["names"]["international"], user_url, run_list

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

# Command to list all runners for a game
@bot.command()
async def runners(ctx, game: str):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    async with aiohttp.ClientSession() as session:
        runners = await fetch_runners(session, game_id)

    if not runners:
        await ctx.send("❌ No runners found for this game.")
        return

    await ctx.send(f"🏁 **Speedrunners for {game.upper()}**:\n{', '.join(runners)}\n\nTotal Runners: {len(runners)}")

# Command to fetch WR or Top 5 runs
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

# Run the bot
bot.run(TOKEN)