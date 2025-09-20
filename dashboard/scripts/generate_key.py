# dashboard/generate_key.py
import os
import base64
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.cache import cache

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# --- Simple Fernet helpers (for your manual test imports) ---------------------
cipher_suite = Fernet(settings.FERNET_KEY)

def encrypt_content(content: str) -> str:
    return cipher_suite.encrypt(content.encode("utf-8")).decode("utf-8")

def decrypt_content(encrypted_content: str) -> str:
    return cipher_suite.decrypt(encrypted_content.encode("utf-8")).decode("utf-8")


# --- AES helpers used by Message model ---------------------------------------
def _derive_key(passphrase: str, salt: bytes, iterations: int = 100_000) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend(),
    )
    return kdf.derive(passphrase.encode("utf-8"))

def get_conversation_key(conversation_id: int) -> bytes:
    cache_key = f"conversation_key_{conversation_id}"
    key = cache.get(cache_key)
    if isinstance(key, str):
        key = key.encode("utf-8")
    if not key:
        salt = f"conversation_{conversation_id}".encode("utf-8")
        kdf = PBKDF2HMAC(
            algorithm=SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
            backend=default_backend(),
        )
        key = kdf.derive(settings.SECRET_KEY.encode("utf-8"))
        cache.set(cache_key, key, timeout=3600)
    return key

def encrypt_message(plaintext: str, key: bytes):
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
    enc = cipher.encryptor()
    ct = enc.update(plaintext.encode("utf-8")) + enc.finalize()
    return iv, ct

def decrypt_message(key: bytes, iv, ciphertext) -> str:
    if not isinstance(iv, bytes):
        iv = base64.b64decode(iv)
    if not isinstance(ciphertext, bytes):
        ciphertext = base64.b64decode(ciphertext)
    cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
    dec = cipher.decryptor()
    return (dec.update(ciphertext) + dec.finalize()).decode("utf-8")

def decrypt_messages_bulk(messages, key: bytes):
    def _one(msg):
        return {
            "id": msg.id,
            "content": decrypt_message(key, msg.iv, msg.content),
            "timestamp": msg.timestamp,
            "sender": msg.sender,
        }
    with ThreadPoolExecutor() as ex:
        return list(ex.map(_one, messages))
