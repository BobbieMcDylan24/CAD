from flask import (
    Blueprint, render_template, redirect, url_for,
    session, current_app, flash, request
)
from bson import ObjectId
import config
import flask_pymongo
import requests
# Initialize MongoDB client
mongodb_client = flask_pymongo.pymongo.MongoClient(config.MONGO_URI)
mydb = mongodb_client['gsrpcad']

bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder='templates')


def discord_user_logged_in():
    return 'access_token' in session and session['access_token']


def get_discord_user_info(access_token):
    url = f"{config.API_BASE_URL}/users/@me"
    headers = { 'Authorization': f"Bearer {access_token}" }
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return None


def get_guild_member(bot_token, guild_id, user_id):
    url = f"{config.API_BASE_URL}/guilds/{guild_id}/members/{user_id}"
    headers = { 'Authorization': f"Bot {bot_token}" }
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return None


@bp.before_request
def require_admin_role():
    # All /admin routes require Discord login + Admin role
    if not discord_user_logged_in():
        flash('Please log in via Discord to access admin.', 'error')
        return redirect(url_for('main.index'))
    user_info = get_discord_user_info(session['access_token'])
    if not user_info:
        flash('Session expired. Log in again.', 'error')
        return redirect(url_for('main.index'))
    member = get_guild_member(
        config.TOKEN,
        config.GUILD_ID,
        user_info['id']
    )
    if not member or config.AdminRole not in member.get('roles', []):
        flash('You do not have administrator permissions.', 'error')
        return redirect(url_for('main.index'))


@bp.route('/users')
def list_users():
    """List all LEO characters for admin editing."""
    cursor = mydb['leocharacters'].find()
    users = []
    for doc in cursor:
        users.append({
            '_id': str(doc['_id']),
            'first_name': doc.get('first_name',''),
            'last_name': doc.get('last_name',''),
            'callsign': doc.get('callsign',''),
            'rank': doc.get('rank',''),
            'badge_number': doc.get('badge_number','')
        })
    return render_template('admin_users.html', users=users)


@bp.route('/users/edit/<user_id>', methods=['GET','POST'])
def edit_user(user_id):
    """Edit a specific LEO character."""
    coll = mydb['leocharacters']
    obj_id = ObjectId(user_id)

    if request.method == 'POST':
        update = {
            'first_name': request.form['first_name'].strip(),
            'last_name':  request.form['last_name'].strip(),
            'callsign':   request.form['callsign'].strip(),
            'rank':       request.form['rank'].strip(),
            'badge_number': request.form['badge_number'].strip()
        }
        try:
            coll.update_one({'_id': obj_id}, {'$set': update})
            flash('User updated successfully.', 'success')
            return redirect(url_for('admin.list_users'))
        except Exception as e:
            current_app.logger.error(f"Error updating user: {e}")
            flash('Failed to update user.', 'error')

    # GET: fetch existing data
    user = coll.find_one({'_id': obj_id})
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.list_users'))

    return render_template('edit_user.html', user={
        '_id': user_id,
        'first_name': user.get('first_name',''),
        'last_name': user.get('last_name',''),
        'callsign': user.get('callsign',''),
        'rank': user.get('rank',''),
        'badge_number': user.get('badge_number','')
    })