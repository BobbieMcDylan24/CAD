from flask import Blueprint, redirect, request, session, url_for, render_template
import requests 
import os
import config
import flask_pymongo
mongodb_client = flask_pymongo.pymongo.MongoClient(config.MONGO_URI)
mydb = mongodb_client['gsrpcad']
bp = Blueprint('oauth', __name__, url_prefix='/oauth')

@bp.route('/login')
def login():
    discord_login_url = (
        f"{config.OAUTH_AUTHORIZE_URL}"
        f"?client_id={config.CLIENT_ID}"
        f"&redirect_uri={config.REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds"
    )
    return redirect(discord_login_url)


@bp.route('/callback')
def callback():
    code = request.args.get("code")
    if not code:
        return "Missing code from Discord", 400

    data = {
        "client_id": config.CLIENT_ID,
        "client_secret": config.CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.REDIRECT_URI,
        "scope": "identify guilds"
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    token_response = requests.post(config.OAUTH_TOKEN_URL, data=data, headers=headers)
    token_json = token_response.json()

    if "access_token" not in token_json:
        return f"OAuth Error: {token_json}", 400

    access_token = token_json["access_token"]
    session["access_token"] = access_token  # For reference

    auth_headers = {"Authorization": f"Bearer {access_token}"}

    # Fetch user info
    user_response = requests.get(config.USER_ENDPOINT, headers=auth_headers)
    if user_response.status_code != 200:
        return "Error fetching user info", 400
    user_data = user_response.json()
    user_id = user_data["id"]

    # Fetch user's guilds
    guilds_response = requests.get(config.GUILDS_ENDPOINT, headers=auth_headers)
    if guilds_response.status_code != 200:
        return "Error fetching guilds", 400
    guilds_data = guilds_response.json()
    users = mydb["users"]
    existing_user = users.find_one({"_id": user_id})

    if existing_user:
        users.update_one(
            {"_id": user_id},
            {"$set": {
                "user": user_data,
                "guilds": guilds_data
            }}
        )
    else:
        users.insert_one({
            "_id": user_id,
            "user": user_data,
            "guilds": guilds_data
        })

    session["user_id"] = user_id
    return redirect(url_for("dashboard.dashboard"))

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("main.index"))