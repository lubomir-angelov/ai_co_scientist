"""
Domain ontology passed to Graphiti for entity extraction (see ARCHITECTURE.md, section 1).

Field names must not collide with Graphiti's EntityNode fields (name, summary, labels, ...).
Graphiti uses the class docstrings as type descriptions in its extraction prompts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Paper(BaseModel):
    """A scientific publication (journal article, conference paper or preprint)."""

    paper_id: str | None = Field(default=None, description="arXiv id or DOI")
    venue: str | None = Field(default=None, description="Journal or conference")
    publication_year: int | None = Field(default=None, description="Year of publication")


class Author(BaseModel):
    """A person who authored a paper."""

    affiliation: str | None = Field(default=None, description="Institution of the author")


class Concept(BaseModel):
    """
    A scientific concept, physical effect, technique or figure of merit, e.g.
    'microring resonator', 'thermo-optic effect', 'Q factor', 'boson sampling'.
    """


class Device(BaseModel):
    """
    A concrete device, component, circuit or system architecture, e.g.
    'thermo-optic microring modulator' or 'silicon-nitride waveguide lattice'.
    """

    material_platform: str | None = Field(
        default=None, description="Material platform, e.g. SOI, SiN, LiNbO3, InP"
    )


class Result(BaseModel):
    """
    A reported, preferably quantitative, result or claim, e.g.
    'Q = 1.2e6 at 1550 nm' or 'energy per bit of 5 fJ'.
    """

    metric: str | None = Field(default=None, description="Measured quantity, e.g. 'Q factor'")
    value: str | None = Field(default=None, description="Reported value as written")
    unit: str | None = Field(default=None, description="Unit of the value")
    conditions: str | None = Field(
        default=None, description="Experimental conditions, e.g. wavelength or temperature"
    )


class Dataset(BaseModel):
    """A dataset, benchmark or standard task used for evaluation, e.g. 'MNIST', 'VQE on H2'."""


class Hypothesis(BaseModel):
    """A research hypothesis proposed by the user or the agent (not an established result)."""

    hypothesis_status: str | None = Field(
        default=None, description="proposed, supported, refuted or superseded"
    )


ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Paper": Paper,
    "Author": Author,
    "Concept": Concept,
    "Device": Device,
    "Result": Result,
    "Dataset": Dataset,
    "Hypothesis": Hypothesis,
}

EXTRACTION_INSTRUCTIONS = """\
The text comes from research on silicon photonics, optical processing, semiconductor
systems and quantum computing.
- Keep numeric results together with their value, unit and conditions.
- Prefer relation names such as MENTIONS, USES_DEVICE, REPORTS_RESULT, ABOUT, CITES,
  IMPROVES_ON, TESTED, SUPPORTS and CONTRADICTS.
- Treat user notes and agent hypotheses as opinions or questions, never as established results.
"""
