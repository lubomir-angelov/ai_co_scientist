from __future__ import annotations

from graphiti_core.utils.ontology_utils.entity_types_utils import validate_entity_types

from memory_service.ontology import ENTITY_TYPES


def test_entity_types_do_not_collide_with_graphiti_fields() -> None:
    assert validate_entity_types(ENTITY_TYPES)


def test_all_entity_types_are_documented() -> None:
    # Graphiti uses docstrings as type descriptions in extraction prompts.
    assert all(model.__doc__ for model in ENTITY_TYPES.values())
