from __future__ import annotations

import argparse
import json

from shared.rag import answer_with_citations


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
