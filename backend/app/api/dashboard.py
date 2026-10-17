from flask import Blueprint, g

from app.security.sessions import deny_investigator_without_mfa, investigator_mfa_satisfied, login_required
from app.services.dashboard import build_dashboard

bp = Blueprint("dashboard", __name__, url_prefix="/api")


@bp.get("/dashboard")
@login_required
def dashboard():
    if not investigator_mfa_satisfied(g.user, g.session):
        deny_investigator_without_mfa()
    return build_dashboard(g.user)
