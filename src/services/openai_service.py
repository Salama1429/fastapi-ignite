"""Utilities for interacting with the OpenAI Responses + File Search APIs."""
from typing import Iterable, List, Optional, Sequence, Tuple

from openai import OpenAI

from src.core.config import settings

FileTuple = Tuple[str, bytes, Optional[str]]

_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    """Create (or reuse) an OpenAI client configured with the project API key."""

    global _client

    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def create_vector_store(name: str) -> str:
    client = get_openai_client()
    vector_store = client.vector_stores.create(name=name)
    return vector_store.id


def upload_files_to_openai(file_tuples: Sequence[FileTuple]) -> List[str]:
    """Upload files to OpenAI and return their IDs."""

    client = get_openai_client()
    uploaded_ids: List[str] = []
    for filename, data, mime in file_tuples:
        file_obj = client.files.create(
            file=(filename, data, mime or "application/octet-stream"),
            purpose="assistants",
        )
        uploaded_ids.append(file_obj.id)
    return uploaded_ids


def attach_files_batch(vector_store_id: str, file_ids: Iterable[str]):
    client = get_openai_client()
    return client.vector_stores.file_batches.create_and_poll(
        vector_store_id=vector_store_id,
        file_ids=list(file_ids),
    )


def list_vector_store_files(vector_store_id: str):
    client = get_openai_client()
    response = client.vector_stores.files.list(
        vector_store_id=vector_store_id, limit=100
    )
    return response.data


def remove_file_from_store(
    vector_store_id: str, file_id: str, delete_raw: bool = False
) -> None:
    client = get_openai_client()
    client.vector_stores.files.delete(
        vector_store_id=vector_store_id, file_id=file_id
    )
    if delete_raw:
        client.files.delete(file_id=file_id)


def responses_file_search(
    vector_store_ids: Sequence[str],
    question: str,
    model: Optional[str] = None,
):
    client = get_openai_client()
    response = client.responses.create(
        model=model or settings.OPENAI_MODEL_DEFAULT,
        input=question,
        tools=[{"type": "file_search", "vector_store_ids": list(vector_store_ids)}],
    )

    try:
        output_text = response.output[0].content[0].text  # type: ignore[index]
    except Exception:  # pragma: no cover - defensive fallback
        output_text = str(response)
    return output_text, response
