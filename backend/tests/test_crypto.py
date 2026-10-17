import base64

import pytest

from app.extensions import db
from app.models import ProtectedRecord, User
from app.security.crypto import Cipher, DecryptionError, KeyConfigurationError, generate_key_b64, parse_key
from app.services.records import create_record, decrypt_record

AAD = {"purpose": "test", "record_id": "r1"}


def test_encrypt_decrypt_roundtrip():
    cipher = Cipher(generate_key_b64(), "k1")
    box = cipher.encrypt(b"synthetic secret", AAD)
    assert b"synthetic secret" not in base64.b64decode(box["ciphertext"])
    assert cipher.decrypt(box["key_id"], box["nonce"], box["ciphertext"], AAD) == b"synthetic secret"


def test_wrong_key_fails():
    box = Cipher(generate_key_b64(), "k1").encrypt(b"data", AAD)
    with pytest.raises(DecryptionError):
        Cipher(generate_key_b64(), "k1").decrypt(box["key_id"], box["nonce"], box["ciphertext"], AAD)


def test_modified_ciphertext_fails():
    cipher = Cipher(generate_key_b64(), "k1")
    box = cipher.encrypt(b"data", AAD)
    raw = bytearray(base64.b64decode(box["ciphertext"]))
    raw[0] ^= 0x01
    with pytest.raises(DecryptionError):
        cipher.decrypt(box["key_id"], box["nonce"], base64.b64encode(bytes(raw)).decode(), AAD)


def test_modified_nonce_or_aad_fails():
    cipher = Cipher(generate_key_b64(), "k1")
    box = cipher.encrypt(b"data", AAD)
    other_nonce = base64.b64encode(b"\x00" * 12).decode()
    with pytest.raises(DecryptionError):
        cipher.decrypt(box["key_id"], other_nonce, box["ciphertext"], AAD)
    with pytest.raises(DecryptionError):
        cipher.decrypt(box["key_id"], box["nonce"], box["ciphertext"], {**AAD, "record_id": "r2"})


def test_key_id_mismatch_fails():
    key = generate_key_b64()
    box = Cipher(key, "k1").encrypt(b"data", AAD)
    with pytest.raises(DecryptionError):
        Cipher(key, "k2").decrypt(box["key_id"], box["nonce"], box["ciphertext"], AAD)


def test_nonce_unique_across_encryptions():
    cipher = Cipher(generate_key_b64(), "k1")
    nonces = {cipher.encrypt(b"same plaintext", AAD)["nonce"] for _ in range(2000)}
    assert len(nonces) == 2000
    a, b = cipher.encrypt(b"same", AAD), cipher.encrypt(b"same", AAD)
    assert a["ciphertext"] != b["ciphertext"]


@pytest.mark.parametrize("value", [None, "", "REPLACE_WITH_GENERATED_BASE64_KEY", "not base64!!",
                                   base64.urlsafe_b64encode(b"short").decode(),
                                   base64.urlsafe_b64encode(b"x" * 64).decode()])
def test_missing_or_invalid_key_rejected(value):
    with pytest.raises(KeyConfigurationError):
        parse_key(value)


def test_valid_key_accepted():
    assert len(parse_key(generate_key_b64())) == 32


def test_record_ciphertext_bound_to_its_metadata(app):
    user = User(username="owner1", display_name="Owner", role="subject", password_hash="x")
    db.session.add(user)
    db.session.commit()
    rec = create_record(user, "health", "Synthetic", {"a": "SYNTHETIC-VALUE"})
    stored = db.session.get(ProtectedRecord, rec.id)
    assert "SYNTHETIC-VALUE" not in stored.ciphertext
    assert decrypt_record(stored) == {"a": "SYNTHETIC-VALUE"}
    # Changing the category metadata (e.g. to slip past a category check) breaks decryption.
    stored.category = "contact"
    with pytest.raises(DecryptionError):
        decrypt_record(stored)


def test_tampered_record_access_fails_safely(api):
    from tests.helpers import read, setup_parties

    alice, _, _, _, record = setup_parties(api)
    stored = db.session.get(ProtectedRecord, record["id"])
    raw = bytearray(base64.b64decode(stored.ciphertext))
    raw[-1] ^= 0xFF
    stored.ciphertext = base64.b64encode(bytes(raw)).decode()
    db.session.commit()
    resp = read(alice, record["id"], purpose=None)
    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "DECRYPTION_FAILED"
    assert "payload" not in resp.get_json()
