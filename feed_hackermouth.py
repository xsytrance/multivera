from __future__ import annotations

import json
import sys

from hackermouth_rag import ingest_docx_files

sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    summary = ingest_docx_files()
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
