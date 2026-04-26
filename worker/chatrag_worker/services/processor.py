from ..utils.logger import log
from ..utils.payloads import Payload, get_payload_value, read_question_from_payload


def process_pdf(payload: Payload) -> str:
    """Simulate PDF processing and return status text."""
    file_name = get_payload_value(payload, "fileName", "unknown.pdf")
    log(f"processing file {file_name} successfull")
    return f"processing file {file_name} successfull"


def process_ask(payload: Payload) -> str:
    """Simulate ask processing and return answer string."""
    question = read_question_from_payload(payload)
    log("processing ask message", question=question)
    return f"/ask response for: {question}"
