from typing import List, Optional, Literal
from pydantic import BaseModel, Field

# --- 1. The Output from the LLM (Probabilistic) ---

class ExtractedEntity(BaseModel):
    """
    Represents a specific object mentioned in the text (e.g., 'Redis', 'Memory Leak').
    """
    name: str = Field(
        ..., 
        description="The precise name of the entity. Use Title Case (e.g., 'Redis Vector Store')."
    )
    type: Literal["Technology", "Problem", "Feature", "Organization"] = Field(
        ...,
        description="The category of the entity. 'Technology' for tools/libs, 'Problem' for bugs/errors, 'Feature' for capabilities."
    )
    description: str = Field(
        ...,
        description="A brief summary of what this entity is in the context of the text."
    )

class ExtractedRelation(BaseModel):
    """
    Represents a connection between the Ticket and an Entity, or between two Entities.
    """
    source: str = Field(..., description="The name of the source entity.")
    target: str = Field(..., description="The name of the target entity.")
    label: Literal["AFFECTS", "USES", "CAUSES", "RELATED_TO"] = Field(
        ...,
        description="The type of relationship. AFFECTS: Bug affects Tech. USES: Feature uses Tech."
    )
    evidence: str = Field(
        ...,
        description="The exact quote from the text that proves this relationship exists."
    )
    # --- NEW FIELDS FOR OFFSETS ---
    evidence_start: Optional[int] = Field(
        default=None, 
        description="DO NOT POPULATE. Internal system use only."
    )
    evidence_end: Optional[int] = Field(
        default=None, 
        description="DO NOT POPULATE. Internal system use only."
    )

class ExtractionResult(BaseModel):
    """
    The container for all data extracted by the LLM from a single text.
    """
    entities: List[ExtractedEntity]
    relations: List[ExtractedRelation]
    summary: str = Field(..., description="A 1-sentence technical summary of the issue.")

# --- 2. The Final Graph Node (Deterministic + Probabilistic) ---

class TicketNode(BaseModel):
    """
    The 'Anchor' node in our graph. This comes directly from GitHub JSON.
    """
    id: int
    title: str
    status: str  # open/closed
    created_at: str
    author_name: str
    url: str
    body_text: str 

    extracted_data: Optional[ExtractionResult] = None
    
    extraction_version: Optional[str] = Field(
        default=None, 
        description="Tracks the schema/prompt/model version used for extraction."
    )
    
    # ---ARTIFACT DEDUP TRACKING ---
    duplicate_of: Optional[int] = Field(
        default=None,
        description="If this ticket is a semantic duplicate, stores the ID of the original ticket."
    )