# scripts/seed_soul_phrase.py
# A utility to securely create a custom SoulPhrase node, using the app's existing driver.

import re
from uuid import uuid4
import asyncio
from dotenv import load_dotenv

# --- EcodiaOS Core Imports ---
# We no longer need get_embedding here, as add_node handles it.
from core.security.soul_phrase_service import encrypt_soulphrase
from core.utils.neo.neo_driver import  close_driver, init_driver
from systems.synk.core.tools.neo import add_node
load_dotenv()

def _get_words_from_phrase(phrase: str) -> list[str]:
    """Extracts unique, sorted, lowercase words from a phrase."""
    words = re.findall(r"[a-z']+", phrase.lower())
    return sorted(list(set(words)))

async def seed_custom_soul_phrase(custom_phrase: str):
    """
    Creates a secure SoulPhrase node from a given phrase string.
    """
    if not custom_phrase:
        raise ValueError("Phrase cannot be empty.")

    # CORRECTED: Automatically derive words from the phrase.
    words = _get_words_from_phrase(custom_phrase)
    if not words:
        raise ValueError("Could not extract any valid words from the provided phrase.")

    print(f"\n[INFO] Phrase: '{custom_phrase}'")
    print(f"[INFO] Derived Words: {', '.join(words)}")

    try:
        print("[INFO] Encrypting phrase...")
        encrypted_phrase = encrypt_soulphrase(custom_phrase)
        
        event_id = str(uuid4())

        # CORRECTED: Call add_node with embed_text to correctly trigger the embedding process.
        print(f"[INFO] Writing :SoulPhrase node and generating vector for: {custom_phrase}")
        await add_node(
            labels=["SoulPhrase"],
            properties={
                "event_id": event_id,
                "key_id": event_id,
                "words": words,
                "phrase_encrypted": encrypted_phrase,
            },
            embed_text=custom_phrase
        )
        print("[SUCCESS] Node successfully created in the database.")

    except Exception as e:
        print(f"\n[ERROR] An error occurred during the seeding process: {e}")
        raise

async def run_interactive_seeding():
    """A wrapper to run the seeding process interactively from a CLI."""
    print("--- EcodiaOS SoulPhrase Seeding Utility ---")
    
    custom_phrase = input("\nEnter the exact SoulPhrase you want to use: ").strip()
    if not custom_phrase:
        print("\nOperation cancelled: Phrase cannot be empty.")
        return

    await seed_custom_soul_phrase(custom_phrase)

# This new main block allows the script to be integrated into app.py via Typer
# or run standalone for quick tests, ensuring the driver is always handled.
if __name__ == "__main__":
    async def standalone_run():
        await init_driver()
        try:
            await run_interactive_seeding()
        finally:
            await close_driver()
    
    asyncio.run(standalone_run())