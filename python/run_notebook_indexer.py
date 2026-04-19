from __future__ import annotations

import argparse
import json
from pathlib import Path

import papermill as pm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--collection-name", required=True)
    parser.add_argument("--file", action="append", required=True)
    args = parser.parse_args()

    notebook_path = Path(__file__).parent / "LangChain_Project_parameterized.ipynb"
    output_dir = Path(__file__).parent / "executed_notebooks"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / f"{args.conversation_id}.ipynb"

    pm.execute_notebook(
        str(notebook_path),
        str(output_path),
        parameters={
            "conversation_id": args.conversation_id,
            "collection_name": args.collection_name,
            "file_paths": args.file,
        },
        log_output=True,
    )

    print(
        json.dumps(
            {
                "conversation_id": args.conversation_id,
                "collection_name": args.collection_name,
                "executed_notebook": str(output_path),
                "suggested_questions": [],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
