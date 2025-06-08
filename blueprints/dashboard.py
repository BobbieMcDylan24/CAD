import datetime
import requests
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    session,
    current_app,
    flash
)
import config
import flask_pymongo
mongodb_client = flask_pymongo.pymongo.MongoClient(config.MONGO_URI)
mydb = mongodb_client['gsrpcad']
bp = Blueprint("dashboard", __name__, template_folder="templates")


def discord_user_logged_in():
    return "access_token" in session and session["access_token"]

def get_discord_user_info(access_token):
    url = f"{config.API_BASE_URL}/users/@me"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return None

def get_guild_member(bot_token, guild_id, user_id):
    url = f"{config.API_BASE_URL}/guilds/{guild_id}/members/{user_id}"
    headers = {"Authorization": f"Bot {bot_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return None

@bp.route("/dashboard/", methods=["GET"])
def dashboard():
    if not discord_user_logged_in():
        flash("You must be logged in via Discord to view the dashboard.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]

    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Your Discord session has expired. Please log in again.", "error")
        return redirect(url_for("main.index"))

    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN

    member = get_guild_member(bot_token, guild_id, discord_user_id)
    if not member:
        flash("You must be a member of the correct Discord guild to view this page.", "error")
        return redirect(url_for("main.index"))
    characters = mydb['characters']
    try:
        cursor = characters.find({'creator_discord_id': discord_user_id})
    except Exception as e:
        current_app.logger.error(f"MongoDB error while fetching characters: {e}")
        flash("Unable to load the character database at the moment.", "error")
        return render_template("dashboard.html", characters=[])

    characters = []
    for doc in cursor:
        characters.append({
            "_id": str(doc['_id']),
            "first_name": doc.get("first_name", ""),
            "last_name": doc.get("last_name", ""),
            "occupation": doc.get("occupation", ""),
            "weapons_count": doc.get("weapons_count", 0),
            "vehicles_count": doc.get("vehicles_count", 0),
        })

    return render_template("dashboard.html", characters=characters)
