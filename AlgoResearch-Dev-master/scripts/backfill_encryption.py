from dashboard.models import Message
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.backends import default_backend
import base64
import os

def backfill_messages():
    messages = Message.objects.filter(iv__isnull=True)
    for message in messages:
        print(f"Encrypting message ID {message.id}...")

        # Generate a key
        salt = f"conversation_{message.conversation.id}".encode()
        secret_key = "your-django-secret-key"  # Replace with your actual Django secret key
        kdf = PBKDF2HMAC(
            algorithm=SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key = kdf.derive(secret_key.encode())

        # Encrypt the message
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(message.content.encode()) + encryptor.finalize()

        # Save the encrypted message
        message.iv = iv
        message.content = base64.b64encode(ciphertext).decode('utf-8')
        message.save()

if __name__ == "__main__":
    backfill_messages()