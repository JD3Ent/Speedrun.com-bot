import discord
from discord.ext import commands
import requests
import os
import asyncio
import time

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

# Safe send function to prevent Discord rate limit issues
async def safe_send(channel, message):
    """ Sends a message but ensures it follows Discord rate limits. """
    try:
        await channel.send(message)
    except discord.HTTPException as e:
        if e.status == 429:
            retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
            print(f"Rate limited by Discord! Retrying in {retry_after} seconds...")
            await asyncio.sleep(retry_after)
            await channel.send(message)

# Function to handle Speedrun.com rate limits
def fetch_data_with_retry(url):
    for attempt in range(3):  # Retry up to 3 times
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:  # Too many requests
            retry_after = int(response.headers.get("Retry-After", 5))  # Default wait time is 5 sec
            print(f"Rate limited! Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
        else:
            break  # Stop retrying if it's a different error
    return None  # Return None if all attempts fail

# Test command to check if bot is running
@bot.command()
async def ping(ctx):
    await safe_send(ctx, "🏓 Pong! Bot is running!")

# Function to fetch categories for a game
def fetch_categories(game_id):
    url = f"{SPEEDRUN_API_URL}/games/{game_id}/categories"
    data = fetch_data_with_retry(url)
    if not data:
        return {}
    
    categories = data.get("data", [])
    return {cat["name"].lower(): cat["id"] for cat in categories}

# Command to list available categories for a game
@bot.command()
async def categories(ctx, game: str):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await safe_send(ctx, "❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    categories = fetch_categories(game_id)
    if not categories:
        await safe_send(ctx, "❌ No categories found for this game.")
        return

    category_list = "\n".join([f"🔹 {name}" for name in categories.keys()])
    await safe_send(ctx, f"**Available Categories for {game.upper()}**:\n{category_list}")

# Command to fetch WR or Top 5 runs
@bot.command()
async def speedrun(ctx, category: str, game: str, top: str = "1"):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await safe_send(ctx, "❌ Invalid game name! Use `/categories [game]` to see valid options.")
        return

    categories = fetch_categories(game_id)
    category_id = categories.get(category.lower())
    if not category_id:
        await safe_send(ctx, "❌ Invalid category! Use `/categories [game]` to see valid options.")
        return

    top_count = 5 if top.lower() == "top5" else 1
    url = f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/category/{category_id}?top={top_count}"
    data = fetch_data_with_retry(url)

    if not data or "data" not in data:
        await safe_send(ctx, "❌ No runs found for this category.")
        return

    runs = data["data"]["runs"]
    message = f"**Top {top_count} {category.upper()} Runs for {game.upper()}**\n"

    for i, run in enumerate(runs[:top_count]):
        player = run["run"]["players"][0].get("name", "Unknown")
        time = run["run"]["times"]["primary_t"]
        video = run["run"].get("videos", {}).get("links", [{"uri": "No video"}])[0]["uri"]

        message += f"**#{i+1} - {player}**\n🏁 Time: {time}\n🎥 Video: {video}\n\n"

    await safe_send(ctx, message)

# Command to list all runners for a game
@bot.command()
async def runners(ctx, game: str):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await safe_send(ctx, "❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    url = f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/categories"
    data = fetch_data_with_retry(url)

    if not data:
        await safe_send(ctx, "❌ No runners found for this game.")
        return

    categories = data["data"]
    runner_ids = set()

    for category in categories:
        leaderboard_url = f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/category/{category['id']}"
        leaderboard_data = fetch_data_with_retry(leaderboard_url)
        if leaderboard_data:
            runs = leaderboard_data["data"]["runs"]
            for run in runs:
                for player in run["run"]["players"]:
                    if player["rel"] == "user":
                        runner_ids.add(player["id"])

    runners = []
    for runner_id in runner_ids:
        user_url = f"{SPEEDRUN_API_URL}/users/{runner_id}"
        user_data = fetch_data_with_retry(user_url)
        if user_data:
            runners.append(user_data["data"]["names"]["international"])

    if not runners:
        await safe_send(ctx, "❌ No runners found for this game.")
        return

    await safe_send(ctx, f"🏁 **Speedrunners for {game.upper()}**:\n{', '.join(runners)}\n\nTotal Runners: {len(runners)}")

# Command to get details on a specific runner
@bot.command()
async def runner(ctx, runner_name: str):
    url = f"{SPEEDRUN_API_URL}/users?lookup={runner_name}"
    data = fetch_data_with_retry(url)
    
    if not data or not data["data"]:
        await safe_send(ctx, "❌ Runner not found!")
        return

    user_data = data["data"][0]
    user_id = user_data["id"]
    user_url = user_data["weblink"]

    # Fetch the runs for this runner
    runs_url = f"{SPEEDRUN_API_URL}/runs?user={user_id}"
    runs_data = fetch_data_with_retry(runs_url)
    runs = runs_data["data"] if runs_data else []

    run_list = []
    for run in runs:
        game_id = run["game"]
        game_name = next((name for name, gid in GAME_IDS.items() if gid == game_id), "Unknown Game")
        category_id = run["category"]
        category_url = f"{SPEEDRUN_API_URL}/categories/{category_id}"
        category_data = fetch_data_with_retry(category_url)
        category_name = category_data["data"]["name"] if category_data else "Unknown Category"
        time = run["times"]["primary_t"]
        video = run["videos"]["links"][0]["uri"] if "videos" in run else "No video"

        run_list.append(f"🏁 **{game_name} - {category_name}**\n⏱️ Time: {time}\n🎥 Video: {video}\n")

    await safe_send(ctx, f"🏆 **{user_data['names']['international']}'s Profile**: {user_url}\n\n" + "\n".join(run_list))

# Run the bot
bot.run(TOKEN)