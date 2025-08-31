import ast
import asyncio
import csv
import glob
import os

from tqdm import tqdm

from systems.synk.core.tools.neo import cypher_query

# --- Constants ---
EXEMPLAR_DIR = "./finished"  # or wherever your CSVs are stored
EMBEDDED_SUFFIX = "_with_embed.csv"


# --- Helper ---
def parse_embedding(embedding_str):
    try:
        # Safely parse stringified list of floats
        return ast.literal_eval(embedding_str)
    except Exception:
        print(f"[ERROR] Failed to parse embedding: {embedding_str[:100]}")
        return []


# --- Main Uploader ---
async def upload_scorer_exemplars():
    files = glob.glob(os.path.join(EXEMPLAR_DIR, f"*{EMBEDDED_SUFFIX}"))

    for file in files:
        scorer_name = os.path.basename(file).replace(EMBEDDED_SUFFIX, "")
        print(f"\n🧠 Uploading exemplars for: {scorer_name}")

        with open(file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        for row in tqdm(rows, desc=f"Uploading {scorer_name}", unit="entry"):
            text = row.get("text", "").strip()
            category = row.get("category", "").strip()
            rationale = row.get("rationale", "").strip()
            embedding = parse_embedding(row.get("embedding", ""))

            if not text or not embedding:
                print(f"[WARN] Skipping invalid row: {text[:50]}...")
                continue

            await cypher_query(
                """
                MERGE (e:ScorerExemplar {text: $text, scorer: $scorer})
                SET e.category = $category,
                    e.rationale = $rationale,
                    e.embedding = $embedding
            """,
                {
                    "text": text,
                    "scorer": scorer_name,
                    "category": category,
                    "rationale": rationale,
                    "embedding": embedding,
                },
            )


# --- Run ---
if __name__ == "__main__":
    asyncio.run(upload_scorer_exemplars())
