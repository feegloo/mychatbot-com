from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared.indexing import index_documents


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--collection-name", required=True)
    parser.add_argument("--file", action="append", required=True)
    args = parser.parse_args()

    result = index_documents(
        conversation_id=args.conversation_id,
        collection_name=args.collection_name,
        file_paths=args.file,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
