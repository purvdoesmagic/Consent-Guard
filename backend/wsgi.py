"""Entry point. Development server: ``python wsgi.py`` (binds to 127.0.0.1 only)."""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
