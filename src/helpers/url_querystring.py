from dataclasses import is_dataclass, asdict
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl


def build_url_with_model(url: str, model: Any) -> str:
    """
    Combines a base URL with a model's fields as query string parameters.

    Supports:
      - Pydantic models (v1 or v2)
      - dataclasses
      - plain dicts
      - objects with __dict__

    Existing query params on the URL are preserved; model fields are
    merged in (model fields take precedence on key collisions).
    None values are excluded.
    """
    params = _model_to_dict(model)

    parsed = urlparse(url)
    existing_params = dict(parse_qsl(parsed.query, keep_blank_values=True))

    # Merge: model params override existing ones with the same key
    merged = {**existing_params, **{k: v for k, v in params.items() if v is not None}}

    new_query = urlencode(merged, doseq=True)

    return urlunparse(parsed._replace(query=new_query))


def _model_to_dict(model: Any) -> dict:
    # Pydantic v2
    if hasattr(model, "model_dump"):
        return model.model_dump()
    # Pydantic v1
    if hasattr(model, "dict"):
        return model.dict()
    # dataclass
    if is_dataclass(model):
        return asdict(model)
    # plain dict
    if isinstance(model, dict):
        return model
    # fallback: generic object
    if hasattr(model, "__dict__"):
        return vars(model)

    raise TypeError(f"Unsupported model type: {type(model)}")