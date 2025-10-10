from cryptography.fernet import Fernet

# Generate a new Fernet key
key = Fernet.generate_key()

# Print the generated key (base64-encoded)
print(key.decode())
