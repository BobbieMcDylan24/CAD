import datetime
import requests
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    current_app,
    flash
)
import config
import flask_pymongo
bp = Blueprint(
    "create_character",
    __name__,
    template_folder="templates"
)
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

@bp.route("/create_character", methods=["GET", "POST"])
def create_character():
    if not discord_user_logged_in():
        flash("You must be logged in with Discord to create a character.", "error")
        return redirect(url_for("main.index"))

    access_token = session["access_token"]
    user_info = get_discord_user_info(access_token)
    if not user_info:
        flash("Your Discord session has expired. Please log in again.", "error")
        return redirect(url_for("main.index"))

    discord_user_id = user_info.get("id")

    if request.method == "POST":
        first_name = request.form.get("firstName", "").strip()
        last_name  = request.form.get("lastName", "").strip()
        dob_str    = request.form.get("dob", "").strip()
        gender     = request.form.get("gender", "").strip()
        occupation       = request.form.get("occupation", "").strip()
        address    = request.form.get("address", "").strip()

        if not first_name or not last_name or not dob_str or not gender or not occupation:
            flash("Please fill in all required fields (First Name, Last Name, DOB, Gender, Occupation).", "error")
            return render_template(
                "create_character.html",
                firstName=first_name,
                lastName=last_name,
                dob=dob_str,
                gender=gender,
                occupation=occupation,
                address=address
            )

        dob = None
        try:
            dob = datetime.datetime.strptime(dob_str, "%Y-%m-%d")
        except ValueError:
            flash("Date of Birth must be in YYYY-MM-DD format.", "error")
            return render_template(
                "create_character.html",
                firstName=first_name,
                lastName=last_name,
                dob=dob_str,
                gender=gender,
                occupation=occupation,
                address=address
            )

        new_character = {
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": dob,
            "gender": gender,
            "occupation": occupation,
            "address": address,
            "creator_discord_id": discord_user_id,
            "created_at": datetime.datetime.utcnow()
        }

        characters = mydb['characters']
        try:
            result = characters.insert_one(new_character)
            flash(f"Character created successfully! (ID: {result.inserted_id})", "success")
            return redirect(url_for("create_character.create_character"))
        except Exception as e:
            current_app.logger.error(f"Error inserting character: {e}")
            flash("An error occurred while creating the character. Please try again.", "error")
            return render_template(
                "create_character.html",
                firstName=first_name,
                lastName=last_name,
                dob=dob_str,
                gender=gender,
                occupation=occupation,
                address=address
            )

    return render_template("create_character.html")