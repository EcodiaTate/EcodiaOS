# scripts/collate_gates.py
# FINAL VERSION - Generates a command reference file for all gates.
import re
from datetime import datetime
from pathlib import Path

# --- CONFIGURATION ---
ROOT_DIRECTORY = Path(__file__).parent.parent
OUTPUT_FILE = ROOT_DIRECTORY / "scripts" / "gets" / "switchboard_gates.txt"
SWITCHBOARD_URL = "http://localhost:8000/synk/switchboard/flags"


# --- SCRIPT LOGIC ---
def find_gate_keys() -> set[str]:
    """Scans all .py files in the root directory for switchboard gate keys."""
    gate_keys: set[str] = set()
    patterns = [
        re.compile(r"""(?:gate|route_gate|gated_async|gated_sync)\(\s*["']([^"']+)["']"""),
        re.compile(r"""(?:enabled_key|interval_key)\s*=\s*["']([^"']+)["']"""),
        re.compile(r"""sb\.\w+\(\s*["']([^"']+)["']"""),
    ]
    for filepath in ROOT_DIRECTORY.rglob("*.py"):
        if any(part in str(filepath) for part in [".venv", "venv", "__pycache__", "node_modules"]):
            continue
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
                for pattern in patterns:
                    matches = pattern.findall(content)
                    for key in matches:
                        gate_keys.add(key)
        except Exception:
            pass
    return gate_keys


def main():
    """Main function to run the collation and save the results."""
    found_keys = sorted(list(find_gate_keys()))

    if not found_keys:
        print("\n❌ No gate keys found.")
        return

    # --- NEW: Build the command reference content ---
    header = f"# EcodiaOS Switchboard Gate Command Reference\n"
    header += f"# Generated on: {datetime.now().isoformat()}\n"
    header += "# Use these curl commands to manage feature flags.\n"

    command_blocks = []
    for key in found_keys:
        # Command to DISABLE the flag
        disable_cmd = f"""curl -X PUT '{SWITCHBOARD_URL}' -H "Content-Type: application/json" --data-binary '{{"key":"{key}","type":"boolean","value":"false","reason":"Manual dev override"}}'"""

        # Command to ENABLE the flag
        enable_cmd = f"""curl -X PUT '{SWITCHBOARD_URL}' -H "Content-Type: application/json" --data-binary '{{"key":"{key}","type":"boolean","value":"true","reason":"Manual dev override"}}'"""

        # Command to VIEW the flag's status (assumes a GET endpoint)
        # NOTE: The exact URL for GET may vary based on your API design.
        view_cmd = f"curl -X GET {SWITCHBOARD_URL}/{key}"

        block = f"""
#-------------------------------------------------
# Key: {key}
#-------------------------------------------------

# DISABLE:
{disable_cmd}

# ENABLE:
{enable_cmd}

# VIEW STATUS (assumes GET /flags/{{key}} endpoint):
{view_cmd}
"""
        command_blocks.append(block)

    output_content = header + "".join(command_blocks)
    # --- END NEW LOGIC ---

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(output_content)
        print(
            f"\n✅ Success! Found {len(found_keys)} keys. Command reference saved to: {OUTPUT_FILE}",
        )
    except Exception as e:
        print(f"\n❌ Error saving to file: {e}")

    print(
        f"\n🗒️  A command reference for all {len(found_keys)} flags has been generated in {OUTPUT_FILE}",
    )


if __name__ == "__main__":
    main()
