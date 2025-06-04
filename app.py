from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, blueprints, Response
from datetime import timedelta, datetime
import os
import importlib
import schedule
import time
import flask_pymongo
import config
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRETKEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=120)
blueprint_folder = "blueprints"
blueprint_files = [f for f in os.listdir(blueprint_folder) if f.endswith('.py') and not f.startswith("__")]
mongodb_client = flask_pymongo.pymongo.MongoClient(config.MONGO_URI)
mydb = mongodb_client['gsrpcad']

for blueprint_file in blueprint_files:
    module_name = f"{blueprint_folder}.{blueprint_file[:-3]}"
    blueprint_module = importlib.import_module(module_name)

    if hasattr(blueprint_module, 'bp'):
        app.register_blueprint(blueprint_module.bp)
        print(f"Loaded blueprint {module_name}")


@app.errorhandler(404)
def not_found(error):
    return render_template('404.html')

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html')

if __name__ == "__main__":
    app.run(port=5000)