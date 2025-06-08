import datetime
import requests
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    current_app
)
import config
import flask_pymongo
mongodb_client = flask_pymongo.pymongo.MongoClient(config.MONGO_URI)
mydb = mongodb_client['gsrpcad']

bp = Blueprint("yourcharacter", __name__, template_folder="templates")

def discord_user_logged_in():
    return "access_token" in session and session["access_token"]

def get_discord_user_info(access_token):
    url = f"{config.API_BASE_URL}/users/@me"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return None

def get_user_guilds(access_token):
    url = f"{config.API_BASE_URL}/users/@me/guilds"
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

@bp.route("/your_character", methods=["GET"])
def your_character():
    if not discord_user_logged_in():
        return redirect(url_for('oauth.login'))
    
    access_token = session["access_token"]

    user_info = get_discord_user_info(access_token)
    if not user_info:
        return redirect(url_for("oauth.login"))
    
    discord_user_id = user_info["id"]

    user_guilds = get_user_guilds(access_token)
    if not user_guilds:
        return redirect(url_for("oauth.login"))
    
    guild_id = config.GUILD_ID
    
    bot_token = config.TOKEN

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
        return redirect(url_for("main.index"))
    
    leocharacters = mydb['leocharacters']
    character = leocharacters.find_one({"creator_discord_id": discord_user_id})

    if not character:
        return redirect(url_for("leocharacter.create_leo"))
    
    dob_str = ""
    if character.get("date_of_birth"):
        dob_dt = character["date_of_birth"]
        if isinstance(dob_dt, datetime.datetime):
            dob_str = dob_dt.strftime("%Y-%m-%d")
        else:
            dob_str = str(dob_dt)

    return render_template("your_character.html",
        character={
            "first_name": character.get("first_name", ""),
            "last_name": character.get("last_name", ""),
            "rank": character.get("rank", ""),
            "callsign": character.get("callsign", ""),
            "date_of_birth": dob_str,
            "phone": character.get("phone", ""),
            "status": character.get("status", "Active")
        }
    )