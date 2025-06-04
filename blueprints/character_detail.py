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

bp = Blueprint(
    "character_detail",
    __name__,
    template_folder="templates"  # adjust if your templates folder is elsewhere
)
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

@bp.route("/detail/<character_id>", methods=["GET"])
def character_detail(character_id):

    if not discord_user_logged_in():
        flash("You must be logged in via Discord.", "error")
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
        flash("You must be in our discord.", "error")
        return redirect("https://discord.gg/gsrp2018")

    characters = mydb['characters']
    try:
        obj_id = ObjectId(character_id)
    except Exception:
        flash("Invalid character ID.", "error")
        return redirect(url_for("dashboard.dashboard"))

    char_doc = characters.find_one({"_id": obj_id})
    if not char_doc:
        flash("Character not found.", "error")
        return redirect(url_for("dashboard.dashboard"))

    licenses = mydb['licenses']
    weapons = mydb['weapons']
    vehicles = mydb['vehicles']
    licenses_cursor = licenses.find({"character_id": obj_id})
    weapons_cursor  = weapons.find({"character_id": obj_id})
    vehicles_cursor= vehicles.find({"character_id": obj_id})

    licenses = []
    for lic in licenses_cursor:
        licenses.append({
            "type": lic.get("type", "Unknown"),
            "issued_on": lic.get("issued_on", "").strftime("%Y-%m-%d") if lic.get("issued_on") else "",
            "expires_on": lic.get("expires_on", "").strftime("%Y-%m-%d") if lic.get("expires_on") else "",
            "status": lic.get("status", "UNKNOWN")
        })

    weapons = []
    for w in weapons_cursor:
        weapons.append({
            "model": w.get("model", ""),
            "weapon_type": w.get("weapon_type", ""),
            "serial": w.get("serial", ""),
            "caliber": w.get("caliber", ""),
            "registered_on": w.get("registered_on", "").strftime("%Y-%m-%d") if w.get("registered_on") else "",
            "status": w.get("status", "UNKNOWN")
        })

    vehicles = []
    for v in vehicles_cursor:
        vehicles.append({
            "model": v.get("model", ""),
            "registration": v.get("registration", ""),
            "color": v.get("color", ""),
            "tax_status": v.get("tax_status", ""),
            "insurance_status": v.get("insurance_status", ""),
            "stolen": v.get("stolen", "No"),
            "registered_on": v.get("registered_on", "").strftime("%Y-%m-%d") if v.get("registered_on") else "",
            "status": v.get("status", "UNKNOWN")
        })

    dob_str = ""
    if char_doc.get("date_of_birth"):
        dt = char_doc["date_of_birth"]
        if isinstance(dt, datetime.datetime):
            dob_str = dt.strftime("%Y-%m-%d")
        else:
            dob_str = str(dt)

    address = char_doc.get("address", "")

    return render_template("character_detail.html",
        character={
            "full_name": f"{char_doc.get('first_name','')} {char_doc.get('last_name','')}",
            "dob": dob_str,
            "address": address,
            "occupation": char_doc.get("occupation", ""),
            "status": char_doc.get("status", "ACTIVE")
        },
        licenses=licenses,
        weapons=weapons,
        vehicles=vehicles,
        character_id=character_id 
    )


@bp.route("/<character_id>/add_license", methods=["GET", "POST"])
def add_license(character_id):
    if not discord_user_logged_in():
        flash("You must be logged in via Discord.", "error")
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
        flash("You are required to be in our discord server.", "error")
        return redirect("https://discord.gg/gsrp2018")

    try:
        obj_id = ObjectId(character_id)
    except Exception:
        flash("Invalid character ID.", "error")
        return redirect(url_for("characters.dashboard"))

    characters = mydb['characters']
    char_doc = characters.find_one({"_id": obj_id})
    if not char_doc:
        flash("Character not found.", "error")
        return redirect(url_for("characters.dashboard"))

    if request.method == "POST":
        lic_type   = request.form.get("type", "").strip()
        issued_on  = request.form.get("issued_on", "").strip()
        expires_on = request.form.get("expires_on", "").strip()
        status     = request.form.get("status", "").strip().upper()

        if not lic_type or not issued_on or not status:
            flash("Please fill in all required fields (Type, Issued On, Status).", "error")
            return render_template("add_license.html", character_id=character_id,
                                   type=lic_type, issued_on=issued_on,
                                   expires_on=expires_on, status=status)

        issued_dt = None
        expires_dt = None
        try:
            issued_dt = datetime.datetime.strptime(issued_on, "%Y-%m-%d")
        except ValueError:
            flash("Issued On must be YYYY-MM-DD.", "error")
            return render_template("add_license.html", character_id=character_id,
                                   type=lic_type, issued_on=issued_on,
                                   expires_on=expires_on, status=status)
        if expires_on:
            try:
                expires_dt = datetime.datetime.strptime(expires_on, "%Y-%m-%d")
            except ValueError:
                flash("Expires On must be YYYY-MM-DD or left blank.", "error")
                return render_template("add_license.html", character_id=character_id,
                                       type=lic_type, issued_on=issued_on,
                                       expires_on=expires_on, status=status)

        new_license = {
            "character_id": obj_id,
            "type": lic_type,
            "issued_on": issued_dt,
            "expires_on": expires_dt,
            "status": status
        }

        try:
            licenses = mydb['licenses']
            licenses.insert_one(new_license)
            flash("License added successfully.", "success")
            return redirect(url_for("character_detail.character_detail", character_id=character_id))
        except Exception as e:
            current_app.logger.error(f"Error inserting license: {e}")
            flash("Failed to add license. Please try again.", "error")
            return render_template("add_license.html", character_id=character_id,
                                   type=lic_type, issued_on=issued_on,
                                   expires_on=expires_on, status=status)

    return render_template("add_license.html", character_id=character_id)


@bp.route("/<character_id>/register_weapon", methods=["GET", "POST"])
def register_weapon(character_id):
    if not discord_user_logged_in():
        flash("You must be logged in via Discord.", "error")
        return redirect(url_for("index.main"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Discord session expired. Please log in again.", "error")
        return redirect(url_for("landing"))
    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN
    member = get_guild_member(bot_token, guild_id, discord_user_id)
    if not member:
        flash("You are required to join our discord server.", "error")
        return redirect("https://discord.com/gsrp2018")

    try:
        obj_id = ObjectId(character_id)
    except Exception:
        flash("Invalid character ID.", "error")
        return redirect(url_for("dashboard.dashboard"))

    characters = mydb['characters']
    char_doc = characters.find_one({"_id": obj_id})
    if not char_doc:
        flash("Character not found.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        model       = request.form.get("model", "").strip()
        wpn_type    = request.form.get("weapon_type", "").strip()
        serial      = request.form.get("serial", "").strip()
        caliber     = request.form.get("caliber", "").strip()
        reg_on      = request.form.get("registered_on", "").strip()
        status      = request.form.get("status", "").strip().upper()

        if not model or not wpn_type or not serial or not caliber or not reg_on or not status:
            flash("All fields are required.", "error")
            return render_template("register_weapon.html", character_id=character_id,
                                   model=model, weapon_type=wpn_type,
                                   serial=serial, caliber=caliber,
                                   registered_on=reg_on, status=status)

        try:
            reg_dt = datetime.datetime.strptime(reg_on, "%Y-%m-%d")
        except ValueError:
            flash("Registered On must be YYYY-MM-DD.", "error")
            return render_template("register_weapon.html", character_id=character_id,
                                   model=model, weapon_type=wpn_type,
                                   serial=serial, caliber=caliber,
                                   registered_on=reg_on, status=status)

        new_weapon = {
            "character_id": obj_id,
            "model": model,
            "weapon_type": wpn_type,
            "serial": serial,
            "caliber": caliber,
            "registered_on": reg_dt,
            "status": status
        }

        try:
            weapons = mydb['weapons']
            weapons.insert_one(new_weapon)
            characters.update_one({"_id": obj_id}, {"$inc": {"weapons_count": 1}})
            flash("Weapon registered successfully.", "success")
            return redirect(url_for("character_detail.character_detail", character_id=character_id))
        except Exception as e:
            current_app.logger.error(f"Error inserting weapon: {e}")
            flash("Failed to register weapon. Please try again.", "error")
            return render_template("register_weapon.html", character_id=character_id,
                                   model=model, weapon_type=wpn_type,
                                   serial=serial, caliber=caliber,
                                   registered_on=reg_on, status=status)

    return render_template("register_weapon.html", character_id=character_id)

@bp.route("/<character_id>/register_vehicle", methods=["GET", "POST"])
def register_vehicle(character_id):
    if not discord_user_logged_in():
        flash("You must be logged in via Discord.", "error")
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
        flash("You are requied to join your discord.", "error")
        return redirect("https://discord.com/gsrp2018")

    try:
        obj_id = ObjectId(character_id)
    except Exception:
        flash("Invalid character ID.", "error")
        return redirect(url_for("dashboard.dashboard"))

    characters = mydb['characters']
    char_doc = characters.find_one({"_id": obj_id})
    if not char_doc:
        flash("Character not found.", "error")
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        model          = request.form.get("model", "").strip()
        registration   = request.form.get("registration", "").strip()
        color          = request.form.get("color", "").strip()
        tax_status     = request.form.get("tax_status", "").strip()
        insurance_status = request.form.get("insurance_status", "").strip()
        stolen         = request.form.get("stolen", "").strip()
        reg_on         = request.form.get("registered_on", "").strip()
        status         = request.form.get("status", "").strip().upper()

        required_fields = [model, registration, color, tax_status, insurance_status, stolen, reg_on, status]
        if any(not f for f in required_fields):
            flash("All fields are required.", "error")
            return render_template("register_vehicle.html", character_id=character_id,
                                   model=model, registration=registration,
                                   color=color, tax_status=tax_status,
                                   insurance_status=insurance_status,
                                   stolen=stolen, registered_on=reg_on,
                                   status=status)

        try:
            reg_dt = datetime.datetime.strptime(reg_on, "%Y-%m-%d")
        except ValueError:
            flash("Registered On must be YYYY-MM-DD.", "error")
            return render_template("register_vehicle.html", character_id=character_id,
                                   model=model, registration=registration,
                                   color=color, tax_status=tax_status,
                                   insurance_status=insurance_status,
                                   stolen=stolen, registered_on=reg_on,
                                   status=status)

        new_vehicle = {
            "character_id": obj_id,
            "model": model,
            "registration": registration,
            "color": color,
            "tax_status": tax_status,
            "insurance_status": insurance_status,
            "stolen": stolen,
            "registered_on": reg_dt,
            "status": status
        }

        try:
            vehicles = mydb['vehicles']
            vehicles.insert_one(new_vehicle)
            characters.update_one({"_id": obj_id}, {"$inc": {"vehicles_count": 1}})
            flash("Vehicle registered successfully.", "success")
            return redirect(url_for("character_detail.character_detail", character_id=character_id))
        except Exception as e:
            current_app.logger.error(f"Error inserting vehicle: {e}")
            flash("Failed to register vehicle. Please try again.", "error")
            return render_template("register_vehicle.html", character_id=character_id,
                                   model=model, registration=registration,
                                   color=color, tax_status=tax_status,
                                   insurance_status=insurance_status,
                                   stolen=stolen, registered_on=reg_on,
                                   status=status)

    return render_template("register_vehicle.html", character_id=character_id)