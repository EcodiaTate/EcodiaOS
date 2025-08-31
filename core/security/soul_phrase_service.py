# core/services/soul_phrase_service.py
# Centralized service for SoulPhrase encryption and decryption.

from cryptography.fernet import Fernet
import os
import base64
import hmac

# IMPORTANT: This key must be securely managed (e.g., via a secrets manager).
# For now, it's loaded from an environment variable.
ENCRYPTION_KEY_STR = os.getenv("SOULPHRASE_ENCRYPTION_KEY")
if not ENCRYPTION_KEY_STR:
    raise ValueError("SOULPHRASE_ENCRYPTION_KEY environment variable not set.")

# Fernet keys must be 32 bytes and URL-safe base64 encoded.
ENCRYPTION_KEY = ENCRYPTION_KEY_STR.encode('utf-8')
cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_soulphrase(soulphrase: str) -> str:
    """Encrypts the SoulPhrase for secure storage."""
    encrypted = cipher_suite.encrypt(soulphrase.encode('utf-8'))
    return base64.urlsafe_b64encode(encrypted).decode('utf-8')

def decrypt_soulphrase(encrypted_soulphrase: str) -> str:
    """Decrypts the SoulPhrase for verification."""
    try:
        encrypted = base64.urlsafe_b64decode(encrypted_soulphrase)
        decrypted = cipher_suite.decrypt(encrypted).decode('utf-8')
        return decrypted
    except Exception as e:
        # Avoid leaking crypto details; log this securely.
        print(f"[SoulPhraseService] Decryption failed: {e}")
        raise ValueError("Decryption failed")

def verify_soulphrase(user_input_phrase: str, stored_encrypted_phrase: str) -> bool:
    """Securely decrypts and compares the user's input with the stored phrase."""
    try:
        decrypted_phrase = decrypt_soulphrase(stored_encrypted_phrase)
        # Use hmac.compare_digest for timing-attack resistance.
        return hmac.compare_digest(user_input_phrase.encode('utf-8'), decrypted_phrase.encode('utf-8'))
    except ValueError:
        return False