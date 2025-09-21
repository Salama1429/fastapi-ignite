"""Compat module exposing the FastAPI application factory for tests."""
from main import app, create_application  # noqa: F401

__all__ = ["create_application", "app"]
