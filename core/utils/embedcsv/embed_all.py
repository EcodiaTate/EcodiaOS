import glob
import os

import pandas as pd

from core.llm.embeddings_gemini import universal_embed

SAL_TYPE_SUFFIX = "_salience_cases.csv"
OUT_SUFFIX = "_with_embed.csv"
TEXT_COL = "text"


def find_salience_csvs(root="."):
    return glob.glob(os.path.join(root, f"*{SAL_TYPE_SUFFIX}"))


async def embed_and_save_csv(infile, outfile, text_col=TEXT_COL):
    df = pd.read_csv(infile, encoding="utf-8-sig")
    print("Loaded columns:", df.columns.tolist())

    # Normalize columns
    df.columns = [col.strip().replace("\ufeff", "") for col in df.columns]
    print("Normalized columns:", df.columns.tolist())

    if text_col not in df.columns:
        print(f"ERROR: '{text_col}' column not found in {infile}. Columns: {df.columns.tolist()}")
        return

    texts = df[text_col].astype(str).fillna("").tolist()

    print(f"Embedding {len(texts)} texts using universal_embed...")

    vectors = []
    for i, text in enumerate(texts):
        try:
            vec = await universal_embed(text)
            vectors.append(vec)
        except Exception as e:
            print(f"[Error] Row {i} failed to embed: {e}")
            vectors.append([0.0] * 1536)  # or handle however you want

    df["embedding"] = [str(vec) for vec in vectors]
    df.to_csv(outfile, index=False)
    print(f"Embedded {infile} → {outfile}")


def main():
    csvs = find_salience_csvs()
    if not csvs:
        print("No salience CSVs found.")
        return
    for infile in csvs:
        outfile = infile.replace(SAL_TYPE_SUFFIX, OUT_SUFFIX)
        embed_and_save_csv(infile, outfile)
    print("All salience CSVs embedded successfully.")


if __name__ == "__main__":
    main()
