# leo_dashboard.py

import flask_pymongo
from bson import ObjectId
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    current_app
)
import requests
import config

# Existing Mongo client
mongodb_client = flask_pymongo.pymongo.MongoClient(config.MONGO_URI)
mydb = mongodb_client['gsrpcad']

bp = Blueprint("leo", __name__, template_folder="templates")


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


@bp.route("/leo/database_lookup", methods=["GET", "POST"])
def database_lookup():
    """
    If GET: show the search form.
    If POST: look up character by first+last name, then fetch:
      - licenses (create default if missing)
      - vehicles
      - weapons
      - arrests
    and pass all four lists into the template.
    """
    if not discord_user_logged_in():
        flash("You must be logged in via Discord to view this page.", "error")
        return redirect(url_for("index.main"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Your Discord session has expired. Please log in again.", "error")
        return redirect(url_for("index.main"))
    discord_user_id = user_info["id"]

    guild_id  = config.GUILD_ID
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
        flash("You must be a member of the correct Discord guild to view this page.", "error")
        return redirect(url_for("index.main"))

    characters_col = mydb['characters']
    licenses_col  = mydb['licenses']
    vehicles_col  = mydb['vehicles']
    weapons_col   = mydb['weapons']
    arrests_col   = mydb['arrests']     # <-- New collection for arrests

    ctx = {
        "searched": False,
        "character": None,
        "licenses": None,
        "vehicles": [],
        "weapons": [],
        "arrests": []
    }

    if request.method == "POST":
        fname = request.form.get("first_name", "").strip()
        lname = request.form.get("last_name", "").strip()

        if not fname or not lname:
            flash("Please enter both first and last name.", "error")
            return render_template("database_lookup.html", **ctx)

        try:
            char_doc = characters_col.find_one({
                "first_name": fname,
                "last_name":  lname
            })
        except Exception as e:
            current_app.logger.error(f"MongoDB error fetching character: {e}")
            flash("Error querying the database. Please try again later.", "error")
            return render_template("database_lookup.html", **ctx)

        if not char_doc:
            flash("No character found with that name.", "error")
            return render_template("database_lookup.html", **ctx)

        ctx["searched"]  = True
        ctx["character"] = {
            "_id":        str(char_doc["_id"]),
            "first_name": char_doc.get("first_name", ""),
            "last_name":  char_doc.get("last_name", ""),
            "occupation": char_doc.get("occupation", "")
        }
        char_id = char_doc["_id"]

        # --- Licenses ---
        licenses_doc = licenses_col.find_one({"character_id": char_id})
        if not licenses_doc:
            licenses_doc = {
                "character_id": char_id,
                "drivers":  "None",
                "pilots":   "None",
                "boats":    "None",
                "fishing":  "None",
                "firearms": "None"
            }
            try:
                licenses_col.insert_one(licenses_doc)
            except Exception as e:
                current_app.logger.error(f"Error inserting default licenses: {e}")
        ctx["licenses"] = licenses_doc

        # --- Vehicles ---
        try:
            veh_cursor = vehicles_col.find({"character_id": char_id})
            for v in veh_cursor:
                ctx["vehicles"].append({
                    "_id":            str(v["_id"]),
                    "model":          v.get("model", ""),
                    "registration":   v.get("registration", ""),
                    "color":          v.get("color", ""),
                    "tax_status":     v.get("tax_status", ""),
                    "insurance_status": v.get("insurance_status", ""),
                    "stolen":         v.get("stolen", "")
                })
        except Exception as e:
            current_app.logger.error(f"Error fetching vehicles: {e}")

        # --- Weapons ---
        try:
            weap_cursor = weapons_col.find({"character_id": char_id})
            for w in weap_cursor:
                ctx["weapons"].append({
                    "_id":    str(w["_id"]),
                    "model":  w.get("model", ""),
                    "serial": w.get("serial", ""),
                    "color":  w.get("color", ""),
                    "mods":   w.get("modifications", ""),
                    "stolen": w.get("stolen", "")
                })
        except Exception as e:
            current_app.logger.error(f"Error fetching weapons: {e}")

        # --- Arrests (New Section) ---
        try:
            arr_cursor = arrests_col.find({"character_id": char_id})
            for a in arr_cursor:
                ctx["arrests"].append({
                    "_id":         str(a["_id"]),
                    "date":        a.get("date", ""),
                    "charge":      a.get("charge", ""),
                    "description": a.get("description", ""),
                    "officer":     a.get("officer", "")
                })
        except Exception as e:
            current_app.logger.error(f"Error fetching arrests: {e}")

    return render_template("database_lookup.html", **ctx)


@bp.route("/leo/database_lookup/update_licenses/<character_id>", methods=["POST"])
def update_licenses(character_id):
    if not discord_user_logged_in():
        flash("You must be logged in via Discord to do that.", "error")
        return redirect(url_for("index.main"))

    drivers  = request.form.get("drivers",  "None")
    pilots   = request.form.get("pilots",   "None")
    boats    = request.form.get("boats",    "None")
    fishing  = request.form.get("fishing",  "None")
    firearms = request.form.get("firearms", "None")

    licenses_col = mydb['licenses']
    try:
        licenses_col.update_one(
            {"character_id": ObjectId(character_id)},
            {"$set": {
                "drivers":  drivers,
                "pilots":   pilots,
                "boats":    boats,
                "fishing":  fishing,
                "firearms": firearms
            }},
            upsert=True
        )
        flash("Licenses updated successfully.", "success")
    except Exception as e:
        current_app.logger.error(f"Error updating licenses: {e}")
        flash("Failed to update licenses. Try again.", "error")

    # Preserve the search query in the redirect so the same character displays again
    fname = request.args.get("first_name", "")
    lname = request.args.get("last_name", "")
    return redirect(
        url_for("leo.database_lookup") +
        f"?first_name={fname}&last_name={lname}"
    )
