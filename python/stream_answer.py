from __future__ import annotations

import argparse

from shared.rag import stream_answer_events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--collection-name", required=True)
    parser.add_argument("--question", required=True)
    args = parser.parse_args()

    for event in stream_answer_events(
        collection_name=args.collection_name,
        conversation_id=args.conversation_id,
        question=args.question,
    ):
        print(event, flush=True)


if __name__ == "__main__":
    main()
