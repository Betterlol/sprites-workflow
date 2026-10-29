"""Compatibility projections of the unified resource resolver."""

from sprite_pipeline.domain.models import ActionConfig
from sprite_pipeline.domain.resources import ResourceResolver, resolve_resource, validate_resources


def action_steps(cfg: ActionConfig, name: str, mode: str = "runtime") -> list[dict]:
    return resolve_resource(cfg.data, "action", name, mode)


def review_steps(cfg: ActionConfig, review: dict, *, allow_empty: bool = False) -> list[dict]:
    if not isinstance(review, dict):
        raise ValueError("A sequence must be an object")
    name = next(
        (
            key
            for key, value in cfg.data.get("workbench", {}).get("reviews", {}).items()
            if value == review
        ),
        "review",
    )
    return ResourceResolver(cfg.data, allow_empty=allow_empty).expand(
        "sequence", name, review, review.get("mode", "runtime"), ()
    )


def validate_editor(cfg: ActionConfig) -> None:
    validate_resources(cfg.data)
