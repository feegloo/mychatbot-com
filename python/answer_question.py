from __future__ import annotations

import argparse
import json
import logging

from shared.rag import answer_with_citations

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--collection-name", required=True)
    parser.add_argument("--question", required=True)
    args = parser.parse_args()

    result = answer_with_citations(
        collection_name=args.collection_name,
        conversation_id=args.conversation_id,
        question=args.question,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
