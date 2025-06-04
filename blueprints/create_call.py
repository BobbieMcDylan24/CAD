import datetime
import requests
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
import config
import flask_pymongo
mongodb_client = flask_pymongo.pymongo.MongoClient(config.MONGO_URI)
mydb = mongodb_client['gsrpcad']
bp = Blueprint("create_call", __name__, template_folder="../../templates")

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

@bp.route("/create_call", methods=["GET", "POST"])
def create_call():
    if "access_token" not in session or not session["access_token"]:
        flash("You must be logged in via Discord to create a 911 call.", "error")
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
    if not member:
        flash("You are required to be in our discord.", "error")
        return redirect("https://discord.gg/gsrp2018")

    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        postal      = request.form.get("postal", "").strip()
        call_type   = request.form.get("call_type", "").strip() 

        if not title or not description or not postal or not call_type:
            flash("All fields are required.", "error")
            return render_template(
                "create_call.html",
                title=title,
                description=description,
                postal=postal,
                call_type=call_type
            )


        forbidden = {"nigger", "nigga", "faggot", "fag", "shit", "bitch"} 
        lower_fields = (title.lower(), description.lower(), postal.lower())
        for word in forbidden:
            for fld in lower_fields:
                if word in fld:
                    flash("Your submission contains inappropriate language.", "error")
                    return render_template(
                        "create_call.html",
                        title=title,
                        description=description,
                        postal=postal,
                        call_type=call_type
                    )

        calls = mydb['calls']
        new_call = {
            "title": title,
            "description": description,
            "postal": postal,
            "call_type": call_type,
            "created_by": discord_user_id,
            "created_at": datetime.datetime.utcnow()
        }
        try:
            calls.insert_one(new_call)
            flash("911 call created successfully.", "success")
            return redirect(url_for("dashboard.dashboard"))
        except Exception as e:
            current_app.logger.error(f"Error inserting 911 call: {e}")
            flash("Failed to create 911 call. Please try again.", "error")
            return render_template(
                "create_call.html",
                title=title,
                description=description,
                postal=postal,
                call_type=call_type
            )

    return render_template("create_call.html")
