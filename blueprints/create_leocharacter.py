import datetime
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    session
)
import requests
from bson.objectid import ObjectId
import config
import flask_pymongo
mongodb_client = flask_pymongo.pymongo.MongoClient(config.MONGO_URI)
mydb = mongodb_client['gsrpcad']

bp = Blueprint("leocharacter", __name__, template_folder="templates")

def discord_user_logged_in():
    return "access_token" in session and session["access_token"]

def get_discord_user_info(access_token):
    url = f"{config.API_BASE_URL}/users/@me"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return None

def get_user_guilds(access_token):
    url = f"{config.API_BASE_URL}/users/@me/guilds"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return None

def get_guild_member(bot_token, guild_id, user_id):
    url = f"{config.API_BASE_URL}/guilds/{guild_id}/members/{user_id}"
    headers = {
        "Authorization": f"Bot {bot_token}"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return None

@bp.route('/leocharacter/create', methods=["GET", "POST"])
def create_leo():   
    if not discord_user_logged_in():
        return redirect(url_for("oauth.login"))
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
    required_role = str(config.LEORole)

    member = get_guild_member(bot_token, guild_id, discord_user_id)
    if not member or config.Trooper or config.Lieutenant or config.Captain or config.Commissioner or config.Major or config.Sergeant not in member.get("roles", []):
        print(member["roles"])
        return redirect(url_for('main.index'))

    if request.method == "POST":
        leoCharacters = mydb['leocharacters']

        first_name = request.form.get("firstName", "").strip()
        last_name = request.form.get("lastName", "").strip()
        rank = request.form.get("rank", "").strip()
        callsign = request.form.get("callsign", "").strip()
        dob_str = request.form.get("dob", "").strip()

        if not first_name or not last_name or not callsign:
            flash(
                "Please fill in all required fields (First Name, Last Name, Callsign, Badge Number).",
                "error"
            )
            return render_template("create_leocharacter.html", firstName=first_name, lastName=last_name, rank=rank, callsign=callsign, dob=dob_str)
        dob = None
        if dob_str:
            dob = datetime.datetime.strptime(dob_str, "%Y-%m-%d")
            
        new_leo = {
            "first_name": first_name,
            "last_name": last_name,
            "rank": rank,
            "callsign": callsign,
            "date_of_birth": dob,
            "created_at": datetime.datetime.utcnow(),
            "creator_discord_id": discord_user_id
        }

        try:
            result = leoCharacters.insert_one(new_leo)
            flash(f"Successfully created LEO character (ID: {result.inserted_id})!", "success")
            return redirect(url_for("leocharacter.create_leo"))
        except Exception as e:
            current_app.logger.error(f"Error inserting LEO character: {e}")
            flash("An error occurred while creating the character. Please try again.", "error")
            return render_template("create_leocharacter.html", firstName=first_name, lastName=last_name, rank=rank, callsign=callsign, dob=dob_str)
    status = session.pop('status_message', None)
    return render_template("create_leocharacter.html", status=status)