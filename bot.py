import discord
from discord.ext import commands
import requests
import subprocess
import sys
import os

# Auto-install dependencies from requirements.txt
def install_requirements():
    if os.path.exists("requirements.txt"):
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    else:
        print("No requirements.txt found. Skipping dependency installation.")

install_requirements()

# Speedrun.com API Base URL
SPEEDRUN_API_URL = "https://www.speedrun.com/api/v1"

# Midnight Club Game IDs from Speedrun.com API
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

# Function to fetch categories for a game
def fetch_categories(game_id):
    response = requests.get(f"{SPEEDRUN_API_URL}/games/{game_id}/categories")
    if response.status_code == 200:
        categories = response.json()["data"]
        return {cat["name"].lower(): cat["id"] for cat in categories}
    return {}

# Function to fetch all runners for a game
def fetch_runners(game_id):
    response = requests.get(f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/categories")
    if response.status_code != 200:
        return None

    categories = response.json()["data"]
    runner_ids = set()

    for category in categories:
        leaderboard_url = f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/category/{category['id']}"
        leaderboard_response = requests.get(leaderboard_url)
        if leaderboard_response.status_code == 200:
            runs = leaderboard_response.json()["data"]["runs"]
            for run in runs:
                for player in run["run"]["players"]:
                    if player["rel"] == "user":
                        runner_ids.add(player["id"])

    runners = []
    for runner_id in runner_ids:
        user_response = requests.get(f"{SPEEDRUN_API_URL}/users/{runner_id}")
        if user_response.status_code == 200:
            user_data = user_response.json()["data"]
            runners.append(user_data["names"]["international"])

    return runners

# Function to fetch runner profile
def fetch_runner_profile(runner_name):
    response = requests.get(f"{SPEEDRUN_API_URL}/users?lookup={runner_name}")
    if response.status_code != 200 or not response.json()["data"]:
        return None

    user_data = response.json()["data"][0]
    user_id = user_data["id"]
    user_url = user_data["weblink"]

    # Fetch the runs for this runner
    runs_response = requests.get(f"{SPEEDRUN_API_URL}/runs?user={user_id}")
    runs = runs_response.json()["data"] if runs_response.status_code == 200 else []

    run_list = []
    for run in runs:
        game_id = run["game"]
        game_name = next((name for name, gid in GAME_IDS.items() if gid == game_id), "Unknown Game")
        category_id = run["category"]
        category_response = requests.get(f"{SPEEDRUN_API_URL}/categories/{category_id}")
        category_name = category_response.json()["data"]["name"] if category_response.status_code == 200 else "Unknown Category"
        time = run["times"]["primary_t"]
        video = run["videos"]["links"][0]["uri"] if "videos" in run else "No video"

        run_list.append(f"🏁 **{game_name} - {category_name}**\n⏱️ Time: {time}\n🎥 Video: {video}\n")

    return user_data["names"]["international"], user_url, run_list

# Command to list categories for a game
@bot.command()
async def categories(ctx, game: str):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    categories = fetch_categories(game_id)
    if not categories:
        await ctx.send("❌ No categories found for this game.")
        return

    category_list = "\n".join([f"🔹 {name}" for name in categories.keys()])
    await ctx.send(f"**Available Categories for {game.upper()}**:\n{category_list}")

# Command to get WR or Top 5 runs
@bot.command()
async def speedrun(ctx, category: str, game: str, top: str = "1"):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    categories = fetch_categories(game_id)
    category_id = categories.get(category.lower())
    if not category_id:
        await ctx.send("❌ Invalid category! Use `/categories [game]` to see valid options.")
        return

    top = 5 if top.lower() == "top5" else 1
    response = requests.get(f"{SPEEDRUN_API_URL}/leaderboards/{game_id}/category/{category_id}?top={top}")
    
    if response.status_code != 200 or "data" not in response.json():
        await ctx.send("❌ No runs found for this category.")
        return

    runs = response.json()["data"]["runs"]
    message = f"**Top {top} {category.upper()} Runs for {game.upper()}**\n"
    
    for i, run in enumerate(runs[:top]):
        player = run["run"]["players"][0]["name"] if "name" in run["run"]["players"][0] else "Unknown"
        time = run["run"]["times"]["primary_t"]
        video = run["run"]["videos"]["links"][0]["uri"] if "videos" in run else "No video"

        message += f"**#{i+1} - {player}**\n🏁 Time: {time}\n🎥 Video: {video}\n\n"

    await ctx.send(message)

# Command to list all runners for a game
@bot.command()
async def runners(ctx, game: str):
    game_id = GAME_IDS.get(game.lower())
    if not game_id:
        await ctx.send("❌ Invalid game name! Use: mc3remix, mc3dub, mc2, mc1, mcla, or mcla_remix")
        return

    runners = fetch_runners(game_id)
    if not runners:
        await ctx.send("❌ No runners found for this game.")
        return

    await ctx.send(f"🏁 **Speedrunners for {game.upper()}**:\n{', '.join(runners)}\n\nTotal Runners: {len(runners)}")

# Command to get details on a specific runner
@bot.command()
async def runner(ctx, runner_name: str):
    profile_data = fetch_runner_profile(runner_name)
    if not profile_data:
        await ctx.send("❌ Runner not found!")
        return

    name, url, runs = profile_data
    run_details = "\n".join(runs) if runs else "No runs found."

    await ctx.send(f"🏆 **{name}'s Profile**: {url}\n\n{run_details}")

# Run the bot
bot.run("YOUR_DISCORD_BOT_TOKEN")
