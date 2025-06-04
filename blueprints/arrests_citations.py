import csv
import io
import datetime
from bson.objectid import ObjectId
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    current_app
)

import config
import flask_pymongo
import requests
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

bp = Blueprint(
    "arrests_citations",
    __name__,
    template_folder="templates"  
)

@bp.route("/api/character_names", methods=["GET"])
def api_character_names():
    if "access_token" not in session or not session["access_token"]:
        return jsonify([]), 401

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        return jsonify([]), 401

    discord_user_id = user_info["id"]
    guild_id        = config.GUILD_ID
    bot_token       = config.TOKEN
    required_role   = config.LEORole
    member = get_guild_member(bot_token, guild_id, discord_user_id)
    if not member or required_role not in member.get("roles", []):
        return jsonify([]), 403

    characters = mydb['characters']
    cursor = characters.find({}, {"first_name": 1, "last_name": 1})
    names = []
    for doc in cursor:
        first = doc.get("first_name", "").strip()
        last  = doc.get("last_name", "").strip()
        if first or last:
            names.append(f"{first} {last}".strip())
    return jsonify(names), 200


@bp.route("/arrests_citations", methods=["GET"])
def view_arrests_citations():
    if "access_token" not in session or not session["access_token"]:
        flash("You must be logged in via Discord to view this page.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("main.index"))
    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN
    member = get_guild_member(bot_token, guild_id, discord_user_id)
    if not member or config.Trooper or config.Lieutenant or config.Captain or config.Commissioner or config.Major or config.Sergeant not in member.get("roles", []):
        flash("You do not have permission to view arrests & citations.", "error")
        return redirect("https://discord.gg/gsrp2018")

    arrests = mydb['arrests']
    citations = mydb['citations']

    arrests_cursor   = arrests.find({"created_by": discord_user_id}).sort("created_at", -1)
    citations_cursor = citations.find({"created_by": discord_user_id}).sort("created_at", -1)

    arrests   = []
    for a in arrests_cursor:
        arrests.append({
            "_id": str(a["_id"]),
            "full_name": a.get("full_name", ""),
            "charge": a.get("charge", ""),
            "description": a.get("description", ""),
            "created_at": a.get("created_at").strftime("%Y-%m-%d %H:%M")
        })

    citations = []
    for c in citations_cursor:
        citations.append({
            "_id": str(c["_id"]),
            "full_name": c.get("full_name", ""),
            "charge": c.get("charge", ""),
            "description": c.get("description", ""),
            "created_at": c.get("created_at").strftime("%Y-%m-%d %H:%M")
        })

    return render_template(
        "arrests_citations.html",
        arrests=arrests,
        citations=citations
    )


@bp.route("/arrests/new", methods=["GET", "POST"])
def new_arrest():
    # 1) Permission checks
    if not discord_user_logged_in():
        flash("You must be logged in via Discord to create an arrest.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("main.index"))
    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN
    member = get_guild_member(bot_token, guild_id, discord_user_id)
    if not member or config.Trooper or config.Lieutenant or config.Captain or config.Commissioner or config.Major or config.Sergeant not in member.get("roles", []):
        flash("You do not have permission to create an arrest report.", "error")
        return redirect(url_for("main.index"))

    # 2) Load character names for autocomplete
    characters = mydb['characters']
    try:
        chars_cursor = characters.find({}, {"first_name": 1, "last_name": 1})
        character_names = []
        for doc in chars_cursor:
            first = doc.get("first_name", "").strip()
            last  = doc.get("last_name", "").strip()
            if first or last:
                character_names.append(f"{first} {last}".strip())
    except Exception as e:
        current_app.logger.error(f"Error fetching characters for autocomplete: {e}")
        character_names = []

    # 3) Load charges list from published CSV
    published_csv_url = current_app.config.get(
        "CHARGES_CSV_URL",
        "https://docs.google.com/spreadsheets/d/e/2PACX-1vRAdjAeCeOtBKz_IzYFcXac-EM6wD1ZTFC7Q570vzMLyn_miaphW_NYmsJOh6XLUcQInuAYM8nQZplN/pub?output=csv"
    )
    charges_list = []
    try:
        resp = requests.get(published_csv_url, timeout=5)
        resp.raise_for_status()
        f = io.StringIO(resp.text)
        reader = csv.reader(f)
        # Skip header if present; assume first column is the charge
        headers = next(reader, None)
        for row in reader:
            if row and row[0].strip():
                charges_list.append(row[0].strip())
        # Remove duplicates while preserving order
        charges_list = list(dict.fromkeys(charges_list))
    except Exception as e:
        current_app.logger.error(f"Error fetching charges CSV: {e}")
        flash("Could not load charges list. Please try again later.", "error")

    # 4) Handle POST (form submission)
    if request.method == "POST":
        full_name   = request.form.get("full_name", "").strip()
        description = request.form.get("description", "").strip()
        charge      = request.form.get("charge", "").strip()

        # Basic validation
        if not full_name or not description or not charge:
            flash("All fields are required.", "error")
        else:
            # Profanity check
            forbidden = {"nigger", "nigga", "faggot", "fag", "shit", "bitch"}
            lower_values = (full_name.lower(), description.lower(), charge.lower())
            if any(w in v for w in forbidden for v in lower_values):
                flash("Your submission contains inappropriate language.", "error")
            else:
                # 4a) Split full_name into first and last
                parts = full_name.split(" ", 1)
                if len(parts) < 2:
                    flash("Please enter both first and last name of the character.", "error")
                else:
                    first_name, last_name = parts[0].strip(), parts[1].strip()
                    # 4b) Look up character_id by name
                    try:
                        char_doc = characters.find_one({
                            "first_name": first_name,
                            "last_name":  last_name
                        })
                    except Exception as e:
                        current_app.logger.error(f"Error querying character by name: {e}")
                        char_doc = None

                    if not char_doc:
                        flash("No character found with that exact name. Please select from the list.", "error")
                    else:
                        char_obj_id = char_doc["_id"]
                        # 4c) Build arrest document
                        arrests = mydb['arrests']
                        doc = {
                            "created_by":   discord_user_id,
                            "created_at":   datetime.datetime.utcnow(),
                            "character_id": char_obj_id,
                            "full_name":    full_name,
                            "description":  description,
                            "charge":       charge,
                        }
                        try:
                            arrests.insert_one(doc)
                            flash("Arrest record created successfully.", "success")
                            return redirect(url_for("arrests_citations.view_arrests_citations"))
                        except Exception as e:
                            current_app.logger.error(f"Error saving arrest: {e}")
                            flash("Failed to create arrest record.", "error")

    # 5) Render template (on GET, or if POST failed)
    return render_template(
        "new_arrest.html",
        character_names=character_names,
        charges_list=charges_list,
        full_name=request.form.get("full_name", ""),
        description=request.form.get("description", ""),
        charge=request.form.get("charge", "")
    )


@bp.route("/citations/new", methods=["GET", "POST"])
def new_citation():
    if "access_token" not in session or not session["access_token"]:
        flash("You must be logged in via Discord to create a citation.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("main.index"))
    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN
    member = get_guild_member(bot_token, guild_id, discord_user_id)
    if not member or config.Trooper or config.Lieutenant or config.Captain or config.Commissioner or config.Major or config.Sergeant not in member.get("roles", []):
        flash("You do not have permission to create a citation.", "error")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        full_name   = request.form.get("full_name", "").strip()
        description = request.form.get("description", "").strip()
        charge      = request.form.get("charge", "").strip()

        if not full_name or not description or not charge:
            flash("All fields are required.", "error")
            return render_template(
                "new_citation.html",
                full_name=full_name,
                description=description,
                charge=charge
            )

        forbidden = {"nigger", "nigga", "faggot", "fag", "shit", "bitch"}
        lower_values = (full_name.lower(), description.lower(), charge.lower())
        for w in forbidden:
            for v in lower_values:
                if w in v:
                    flash("Your submission contains inappropriate language.", "error")
                    return render_template(
                        "new_citation.html",
                        full_name=full_name,
                        description=description,
                        charge=charge
                    )

        citations = mydb['citations']
        doc = {
            "created_by": discord_user_id,
            "created_at": datetime.datetime.utcnow(),
            "full_name": full_name,
            "description": description,
            "charge": charge
        }
        try:
            citations.insert_one(doc)
            flash("Citation created successfully.", "success")
            return redirect(url_for("characters.view_arrests_citations"))
        except Exception as e:
            current_app.logger.error(f"Error saving citation: {e}")
            flash("Failed to create citation.", "error")
            return render_template(
                "new_citation.html",
                full_name=full_name,
                description=description,
                charge=charge
            )

    return render_template("new_citation.html")


def load_helpers():
    # 1) Character names for autocomplete
    try:
        chars_cursor = mydb['characters'].find({}, {"first_name": 1, "last_name": 1})
        character_names = []
        for doc in chars_cursor:
            first = doc.get("first_name", "").strip()
            last  = doc.get("last_name", "").strip()
            if first or last:
                character_names.append(f"{first} {last}".strip())
    except Exception as e:
        current_app.logger.error(f"Error fetching character names: {e}")
        character_names = []

    # 2) Charges from Google Sheets CSV
    published_csv_url = current_app.config.get(
        "CHARGES_CSV_URL",
        "https://docs.google.com/spreadsheets/d/e/2PACX-1vRAdjAeCeOtBKz_IzYFcXac-EM6wD1ZTFC7Q570vzMLyn_miaphW_NYmsJOh6XLUcQInuAYM8nQZplN/pub?output=csv"
    )
    charges_list = []
    try:
        resp = requests.get(published_csv_url, timeout=5)
        resp.raise_for_status()
        f = io.StringIO(resp.text)
        reader = csv.reader(f)
        _ = next(reader, None)  # skip header if any
        for row in reader:
            if row and row[0].strip():
                charges_list.append(row[0].strip())
        charges_list = list(dict.fromkeys(charges_list))
    except Exception as e:
        current_app.logger.error(f"Error fetching charges CSV: {e}")
        flash("Could not load charges list. Please try again later.", "error")

    return character_names, charges_list


# ---------- Create Warrant Route ----------
@bp.route("/warrants/new", methods=["GET", "POST"])
def new_warrant():
    # Permission check
    if not discord_user_logged_in():
        flash("You must be logged in via Discord to create a warrant.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("main.index"))
    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN
    member = get_guild_member(bot_token, guild_id, discord_user_id)
    if not member or config.Trooper or config.Lieutenant or config.Captain or config.Commissioner or config.Major or config.Sergeant not in member.get("roles", []):
        flash("You do not have permission to create a warrant.", "error")
        return redirect(url_for("main.index"))

    # Load helpers
    character_names, charges_list = load_helpers()

    # On POST: process form
    if request.method == "POST":
        full_name       = request.form.get("full_name", "").strip()
        charge          = request.form.get("charge", "").strip()
        description     = request.form.get("description", "").strip()
        expiration_date = request.form.get("expiration_date", "").strip()

        # Validate fields
        if not full_name or not charge or not description or not expiration_date:
            flash("All fields are required.", "error")
        else:
            # Profanity check
            forbidden = {"nigger", "nigga", "faggot", "fag", "shit", "bitch"}
            lower_values = (
                full_name.lower(),
                charge.lower(),
                description.lower()
            )
            if any(w in v for w in forbidden for v in lower_values):
                flash("Your submission contains inappropriate language.", "error")
            else:
                # Split full_name into first/last
                parts = full_name.split(" ", 1)
                if len(parts) < 2:
                    flash("Please enter both first and last name of the character.", "error")
                else:
                    fname, lname = parts[0].strip(), parts[1].strip()
                    # Look up character_id
                    char_doc = mydb['characters'].find_one({
                        "first_name": fname,
                        "last_name":  lname
                    })
                    if not char_doc:
                        flash("No character found with that exact name. Please select from the list.", "error")
                    else:
                        char_obj_id = char_doc["_id"]
                        # Insert warrant
                        warrants = mydb['warrants']
                        doc = {
                            "created_by":     discord_user_id,
                            "created_at":     datetime.datetime.utcnow(),
                            "character_id":   char_obj_id,
                            "full_name":      full_name,
                            "charge":         charge,
                            "description":    description,
                            "expiration_date": expiration_date
                        }
                        try:
                            warrants.insert_one(doc)
                            flash("Warrant created successfully.", "success")
                            return redirect(url_for("arrests_citations.view_arrests_citations"))
                        except Exception as e:
                            current_app.logger.error(f"Error saving warrant: {e}")
                            flash("Failed to create warrant. Try again.", "error")

    # On GET or POST‐failure: render form
    return render_template(
        "new_warrant.html",
        character_names=character_names,
        charges_list=charges_list,
        full_name=request.form.get("full_name", ""),
        charge=request.form.get("charge", ""),
        description=request.form.get("description", ""),
        expiration_date=request.form.get("expiration_date", "")
    )


# ---------- Create BOLO Route ----------
@bp.route("/bolos/new", methods=["GET", "POST"])
def new_bolo():
    # Permission check
    if not discord_user_logged_in():
        flash("You must be logged in via Discord to create a BOLO.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("main.index"))
    discord_user_id = user_info["id"]

    guild_id      = config.GUILD_ID
    bot_token     = config.TOKEN
    member = get_guild_member(bot_token, guild_id, discord_user_id)
    if not member or config.Trooper or config.Lieutenant or config.Captain or config.Commissioner or config.Major or config.Sergeant not in member.get("roles", []):
        flash("You do not have permission to create a BOLO.", "error")
        return redirect(url_for("main.index"))

    # Load character names (BOLO relies on suspect being a character)
    try:
        chars_cursor = mydb['characters'].find({}, {"first_name": 1, "last_name": 1})
        character_names = []
        for doc in chars_cursor:
            first = doc.get("first_name", "").strip()
            last  = doc.get("last_name", "").strip()
            if first or last:
                character_names.append(f"{first} {last}".strip())
    except Exception as e:
        current_app.logger.error(f"Error fetching characters for autocomplete: {e}")
        character_names = []

    # BOLO categories can be hardcoded (you may adjust as needed)
    bolo_categories = ["Felony", "Misdemeanor", "Missing Person", "Traffic Violation"]

    if request.method == "POST":
        full_name          = request.form.get("full_name", "").strip()
        category           = request.form.get("category", "").strip()
        last_seen_location = request.form.get("last_seen_location", "").strip()
        description        = request.form.get("description", "").strip()

        # Validate
        if not full_name or not category or not last_seen_location or not description:
            flash("All fields are required.", "error")
        else:
            # Profanity check
            forbidden = {"nigger", "nigga", "faggot", "fag", "shit", "bitch"}
            lower_values = (
                full_name.lower(),
                category.lower(),
                last_seen_location.lower(),
                description.lower()
            )
            if any(w in v for w in forbidden for v in lower_values):
                flash("Your submission contains inappropriate language.", "error")
            else:
                # Split full_name into first/last
                parts = full_name.split(" ", 1)
                if len(parts) < 2:
                    flash("Please enter both first and last name of the suspect.", "error")
                else:
                    fname, lname = parts[0].strip(), parts[1].strip()
                    # Look up character_id
                    char_doc = mydb['characters'].find_one({
                        "first_name": fname,
                        "last_name":  lname
                    })
                    if not char_doc:
                        flash("No character found with that exact name. Please select from the list.", "error")
                    else:
                        char_obj_id = char_doc["_id"]
                        # Insert BOLO
                        bolos = mydb['bolos']
                        doc = {
                            "created_by":        discord_user_id,
                            "created_at":        datetime.datetime.utcnow(),
                            "character_id":      char_obj_id,
                            "full_name":         full_name,
                            "category":          category,
                            "last_seen_location": last_seen_location,
                            "description":       description
                        }
                        try:
                            bolos.insert_one(doc)
                            flash("BOLO created successfully.", "success")
                            return redirect(url_for("arrests_citations.view_arrests_citations"))
                        except Exception as e:
                            current_app.logger.error(f"Error saving BOLO: {e}")
                            flash("Failed to create BOLO. Try again.", "error")

    # On GET or POST‐failure: render form
    return render_template(
        "new_bolo.html",
        character_names=character_names,
        bolo_categories=bolo_categories,
        full_name=request.form.get("full_name", ""),
        category=request.form.get("category", ""),
        last_seen_location=request.form.get("last_seen_location", ""),
        description=request.form.get("description", "")
    )