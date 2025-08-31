from cryptography.fernet import Fernet
import base64
from core.utils.neo.cypher_query import cypher_query  # Assuming a custom Neo4j helper for querying

# Encryption key (this should be securely managed, not hardcoded in production)
KEY = b"your-encryption-key-here"
cipher_suite = Fernet(KEY)

def encrypt_soulphrase(soulphrase: str) -> str:
    """Encrypt the SoulPhrase before storing it in the database."""
    encrypted = cipher_suite.encrypt(soulphrase.encode())
    return base64.urlsafe_b64encode(encrypted).decode('utf-8')

def decrypt_soulphrase(encrypted_soulphrase: str) -> str:
    """Decrypt the SoulPhrase when retrieving it from the database."""
    encrypted = base64.urlsafe_b64decode(encrypted_soulphrase)
    decrypted = cipher_suite.decrypt(encrypted).decode('utf-8')
    return decrypted

def get_soulphrase_by_session(session_id: str) -> str:
    """Retrieve the SoulPhrase for a given session ID from the database."""
    query = """
    MATCH (u:UserSession {session_id: $session_id})-[:HAS_SOULPHRASE]->(s:SoulPhrase)
    RETURN s.phrase AS soulphrase
    """
    params = {"session_id": session_id}
    result = cypher_query(query, params)

    if result:
        encrypted_soulphrase = result[0]["soulphrase"]
        return decrypt_soulphrase(encrypted_soulphrase)
    return None

def update_soulphrase_for_session(session_id: str, new_soulphrase: str) -> None:
    """Update the SoulPhrase for a given session ID."""
    encrypted_soulphrase = encrypt_soulphrase(new_soulphrase)
    query = """
    MATCH (u:UserSession {session_id: $session_id})-[:HAS_SOULPHRASE]->(s:SoulPhrase)
    SET s.phrase = $encrypted_soulphrase
    """
    params = {"session_id": session_id, "encrypted_soulphrase": encrypted_soulphrase}
    cypher_query(query, params)
