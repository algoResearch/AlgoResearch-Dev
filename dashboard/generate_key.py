import os
import uuid
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hashes import SHA256
import base64
from django.conf import settings
from cryptography.hazmat.backends import default_backend
from django.core.cache import cache
from cryptography.fernet import Fernet

def generate_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    return kdf.derive(passphrase.encode())

def encrypt_message(plaintext, key):
    iv = os.urandom(16)  # Generate a random IV
    cipher = Cipher(algorithms.AES(key), modes.CFB(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
    # Log IV and ciphertext
    print(f"Generated IV: {base64.b64encode(iv).decode()}")
    print(f"Generated Ciphertext: {base64.b64encode(ciphertext).decode()}") 
    return base64.b64encode(iv).decode(), base64.b64encode(ciphertext).decode()

cipher_suite = Fernet(settings.FERNET_KEY)

def encrypt_content(content):
    return cipher_suite.encrypt(content.encode()).decode()

def decrypt_content(encrypted_content):
    return cipher_suite.decrypt(encrypted_content.encode()).decode()
def decrypt_message(key: bytes, iv: str, ciphertext: str) -> str:
    if not iv or not ciphertext:
        raise ValueError("Missing IV or ciphertext for decryption")
    # Decode Base64-encoded IV and ciphertext
    iv = base64.b64decode(iv)
    ciphertext = base64.b64decode(ciphertext)
    cipher = Cipher(algorithms.AES(key), modes.CFB(iv))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    return plaintext.decode()
def decrypt_messages_bulk(messages, key):
    decrypted_messages = []
    for message in messages:
        decrypted_content = decrypt_message(key, message.iv, message.ciphertext)
        decrypted_messages.append({
            'id': message.id,
            'content': decrypted_content,
            'timestamp': message.timestamp,
            'sender': message.sender,
        })
    return decrypted_messages
def get_conversation_key(conversation_id):
    salt = f"conversation_{conversation_id}".encode()
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,  # 32 bytes = 256 bits for AES-256
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    derived_key = kdf.derive(settings.SECRET_KEY.encode())
    
    # Log derived key
    print(f"Derived key for conversation {conversation_id}: {derived_key.hex()}")
    
    return derived_key
