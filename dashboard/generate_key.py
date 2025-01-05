import os
import uuid
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hashes import SHA256
import base64
from django.conf import settings
from cryptography.hazmat.backends import default_backend
from concurrent.futures import ThreadPoolExecutor
from django.core.cache import cache
from cryptography.fernet import Fernet

import logging

logger = logging.getLogger(__name__)

def generate_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    return kdf.derive(passphrase.encode())


def get_conversation_key(conversation_id):
    salt = f"conversation_{conversation_id}".encode()
    cache_key = f"conversation_key_{conversation_id}"
    derived_key = cache.get(cache_key)
    if isinstance(derived_key, str):
        derived_key = derived_key.encode('utf-8')
    
    if not derived_key:
        kdf = PBKDF2HMAC(
            algorithm=SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        derived_key = kdf.derive(settings.SECRET_KEY.encode())
        cache.set(cache_key, derived_key, timeout=3600)  # Cache for 1 hour

    return derived_key

def encrypt_message(plaintext, key):
    """
    Encrypt a plaintext string using AES encryption and return the IV and ciphertext.
    """
    logger.debug(f"Encrypting plaintext: {plaintext} (Type: {type(plaintext)})")
    logger.debug(f"Encryption key: {key} (Type: {type(key)})")
    
    if not isinstance(plaintext, str):
        raise ValueError(f"Plaintext must be a string. Received type: {type(plaintext)}")
    iv = os.urandom(16)  # Generate random IV (bytes)
    cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext.encode('utf-8')) + encryptor.finalize()  # Convert plaintext to bytes
    logger.debug(f"Generated ciphertext: {ciphertext} (Type: {type(ciphertext)})")
    return iv, ciphertext

cipher_suite = Fernet(settings.FERNET_KEY)

def encrypt_content(content):
    return cipher_suite.encrypt(content.encode()).decode()

def decrypt_content(encrypted_content):
    return cipher_suite.decrypt(encrypted_content.encode()).decode()

# Decrypt an encrypted message

def decrypt_message(key, iv, ciphertext):
    """
    Decrypt a ciphertext using AES decryption and return the plaintext string.
    """
    try:
        if not isinstance(iv, bytes):
            iv = base64.b64decode(iv)  # Ensure IV is bytes
        if not isinstance(ciphertext, bytes):
            ciphertext = base64.b64decode(ciphertext)  # Ensure ciphertext is bytes
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        return plaintext.decode('utf-8')  # Convert bytes to string
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return "[Decryption Error]"
    

# Decrypt multiple messages

def decrypt_messages_bulk(messages, key):
    def decrypt_single_message(message):
        return {
            'id': message.id,
            'content': decrypt_message(key, message.iv, message.content),
            'timestamp': message.timestamp,
            'sender': message.sender,
        }

    with ThreadPoolExecutor() as executor:
        decrypted_messages = list(executor.map(decrypt_single_message, messages))
    
    return decrypted_messages
