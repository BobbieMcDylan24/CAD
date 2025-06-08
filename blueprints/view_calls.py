import datetime
from bson.objectid import ObjectId
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    session,
    current_app,
    flash,
    request
)
import requests
import config
import flask_pymongo
mongodb_client = flask_pymongo.pymongo.MongoClient(config.MONGO_URI)
mydb = mongodb_client['gsrpcad']

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


bp = Blueprint("view_calls", __name__, template_folder="templates")

@bp.route("/view_calls", methods=["GET"])
def view_calls():
    if "access_token" not in session or not session["access_token"]:
        flash("You must be logged in via Discord to view 911 calls.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Discord session expired. Please log in again.", "error")
        return redirect(url_for("main.index"))
    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN

    member = get_guild_member(bot_token, guild_id, discord_user_id)
    required_roles = [
    config.Trooper,
    config.Lieutenant,
    config.Captain,
    config.Commissioner,
    config.Major,
    config.Sergeant,
    ]
    if not member or not any(role in member.get("roles", []) for role in required_roles):
        flash("You do not have permission to view 911 calls.", "error")
        return redirect(url_for("dashboard.dashboard"))

    calls = mydb['calls']
    calls_cursor = calls.find(
        {"claimed_by": {"$exists": False}}
    ).sort("created_at", -1)

    leoCharacters = mydb['leocharacters']
    charactersCursor = leoCharacters.find({'status': 'active'})
    characters = []
    for character in charactersCursor:
        characters.append({
            "first_name": character.get("first_name"),
            "last_name": character.get("last_name"),
            "callsign": character.get('callsign'),
        })
    calls = []
    for c in calls_cursor:
        calls.append({
            "_id": str(c["_id"]),
            "title": c.get("title", ""),
            "description": c.get("description", ""),
            "postal": c.get("postal", ""),
            "call_type": c.get("call_type", ""),
            "created_at": c.get("created_at").strftime("%Y-%m-%d %H:%M") 
                          if c.get("created_at") else ""
        })

    return render_template("view_calls.html", calls=calls)


@bp.route("/911_calls/<call_id>/claim", methods=["POST"])
def claim_call(call_id):
    if "access_token" not in session or not session["access_token"]:
        flash("You must be logged in via Discord to claim a call.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Discord session expired. Please log in again.", "error")
        return redirect(url_for("main.index"))
    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN

    member = get_guild_member(bot_token, guild_id, discord_user_id)
    required_roles = [
    config.Trooper,
    config.Lieutenant,
    config.Captain,
    config.Commissioner,
    config.Major,
    config.Sergeant,
    ]
    if not member or not any(role in member.get("roles", []) for role in required_roles):
        flash("You do not have permission to claim a call.", "error")
        return redirect(url_for("dashboard.dashboard"))
    try:
        obj_id = ObjectId(call_id)
    except Exception:
        flash("Invalid call ID.", "error")
        return redirect(url_for("view_calls.view_calls"))

    calls = mydb['calls']
    result = calls.update_one(
        {"_id": obj_id, "claimed_by": {"$exists": False}},
        {
            "$set": {
                "claimed_by": discord_user_id,
                "claimed_at": datetime.datetime.utcnow(),
                "status": "claimed"
            }
        }
    )

    if result.matched_count == 0:
        flash("Call was already claimed or does not exist.", "error")
    else:
        flash("You have successfully claimed this call.", "success")

    return redirect(url_for("view_calls.view_calls"))


@bp.route("/911_calls/<call_id>/delete", methods=["POST"])
def delete_call(call_id):
    if "access_token" not in session or not session["access_token"]:
        flash("You must be logged in via Discord to delete a call.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Discord session expired. Please log in again.", "error")
        return redirect(url_for("main.index"))
    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN

    member = get_guild_member(bot_token, guild_id, discord_user_id)
    required_roles = [
    config.Trooper,
    config.Lieutenant,
    config.Captain,
    config.Commissioner,
    config.Major,
    config.Sergeant,
    ]
    if not member or not any(role in member.get("roles", []) for role in required_roles):
        flash("You do not have permission to delete a call.", "error")
        return redirect(url_for("dashboard.dashboard"))

    try:
        obj_id = ObjectId(call_id)
    except Exception:
        flash("Invalid call ID.", "error")
        return redirect(url_for("view_calls.view_calls"))

    calls = mydb['calls']
    result = calls.delete_one({"_id": obj_id})

    if result.deleted_count == 0:
        flash("Failed to delete—call not found.", "error")
    else:
        flash("Call deleted successfully.", "success")

    return redirect(url_for("view_calls.view_calls"))