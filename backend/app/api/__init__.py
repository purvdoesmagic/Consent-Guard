def register_blueprints(app):
    from app.api import audit, auth, cases, consents, dashboard, health, meta, records

    for module in (health, auth, meta, dashboard, consents, records, audit, cases):
        app.register_blueprint(module.bp)
