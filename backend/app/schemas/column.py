from pydantic import BaseModel


class ColumnCreate(BaseModel):

    dataset_id: str

    name: str

    data_type: str

    nullable: bool

    classification: str = "UNCLASSIFIED"

    sensitivity_score: str = "LOW"