from flask import Blueprint, request, jsonify, session
from models.db import get_collections
from services.beneficiaries import list_beneficiaries, add_beneficiary, delete_beneficiary
from utils.helpers import (
    api_error,
    api_success,
    login_required,
)
from utils.logging_config import setup_logging

logger = setup_logging()
beneficiaries_bp = Blueprint("beneficiaries", __name__)
cols = get_collections()
beneficiaries_col = cols["beneficiaries"]

@beneficiaries_bp.route("/api/beneficiaries", methods=["GET", "POST"])
@login_required
def beneficiaries_api():
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")

    if request.method == "GET":
        results = list_beneficiaries(beneficiaries_col, user_id)
        return jsonify({"beneficiaries": results})

    # POST - add beneficiary
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or request.form.get("name") or "").strip()
    email = (data.get("email") or request.form.get("email") or "").strip().lower()
    nickname = (data.get("nickname") or request.form.get("nickname") or "").strip()

    if not name or not email:
        return api_error("Name and email are required.", 400, endpoint="main.beneficiaries_page", category="warning")

    # Prevent adding own account as beneficiary
    session_email = (session.get("user_email") or "").strip().lower()
    if email == session_email:
        return api_error("Cannot add your own account as a beneficiary.", 400, endpoint="main.beneficiaries_page")

    beneficiary, err = add_beneficiary(beneficiaries_col, user_id, name, email, nickname)
    if err:
        return api_error(err, 400, endpoint="main.beneficiaries_page")

    return api_success("Beneficiary added.", payload={"beneficiary": {"id": str(beneficiary.get("_id")), "name": beneficiary.get("name"), "email": beneficiary.get("email"), "nickname": beneficiary.get("nickname")}}, endpoint="main.beneficiaries_page")

@beneficiaries_bp.route("/api/beneficiaries/<beneficiary_id>", methods=["DELETE"])
@login_required
def beneficiaries_delete_api(beneficiary_id):
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")

    ok, err = delete_beneficiary(beneficiaries_col, user_id, beneficiary_id)
    if not ok:
        return api_error(err or "Unable to delete beneficiary.", 400, endpoint="main.beneficiaries_page")
    return api_success("Beneficiary removed.", endpoint="main.beneficiaries_page")
