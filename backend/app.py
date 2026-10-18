"""ConsentGuard server. Start it with:  python app.py"""

import os

from flask import Flask, send_from_directory

from config import Config
from encryption import check_key
from models import db
from routes import auth, data, investigator

FRONTEND_BUILD = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")


def create_app(settings=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if settings:
        app.config.update(settings)

    check_key(app.config["ENCRYPTION_KEY"])
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(data.bp)
    app.register_blueprint(investigator.bp)

    with app.app_context():
        db.create_all()

    # After "npm run build", the server also shows the website itself
    @app.get("/")
    @app.get("/<path:path>")
    def website(path=""):
        if path.startswith("api/"):
            return {"error": "Not found."}, 404
        if not os.path.exists(FRONTEND_BUILD):
            return {"message": "ConsentGuard API is running. Start the website with: npm run dev"}
        if path and os.path.isfile(os.path.join(FRONTEND_BUILD, path)):
            return send_from_directory(FRONTEND_BUILD, path)
        return send_from_directory(FRONTEND_BUILD, "index.html")

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000)
