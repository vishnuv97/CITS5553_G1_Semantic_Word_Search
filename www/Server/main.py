from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bert_model import process_csv_and_get_scores
from keyphrase_transformer import extract_info
from typing import List, Optional
import json
from datetime import datetime

from langchain.embeddings import SentenceTransformerEmbeddings
from langchain.vectorstores import Chroma

app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/python")
def hello_world():
    return {"message": "Hello World"}


class queryJSON(BaseModel):
    query: str


class QueryData(BaseModel):
    reference_number: str
    query: str


class WordsAndScores(BaseModel):
    words: list[str]
    semantic_scores: list[float]


class filterJSON(BaseModel):
    query: str
    start_date: str
    end_date: str


class documentJSON(BaseModel):
    Client_Agency: str = Field(alias="Client Agency")
    Contract_Title: str = Field(alias="Contract Title")
    Description: str
    Procurement_Method: str = Field(alias="Procurement Method")
    Reference_Number: str = Field(alias="Reference Number")
    Revised_Contract_Value: float = Field(alias="Revised Contract Value")
    Supplier_Name: str = Field(alias="Supplier Name")
    Tender_Closing_Date: datetime = Field(alias="Tender Closing Date")
    Tenders_Content: Optional[str] = Field(alias="Tenders Content")
    Type_of_Work: str = Field(alias="Type of Work")
    UNSPSC_Code: int = Field(alias="UNSPSC Code")
    UNSPSC_Title: str = Field(alias="UNSPSC Title")
    similarity_score: float


class documentsJSON(BaseModel):
    documents: list[documentJSON]


class FilterOutput(BaseModel):
    query: str
    startDate: str
    endDate: str
    Range: List[int]
    typeOfWork: str
    UNSPSCcode: List[int]


@app.post("/api/getFilters", response_model=FilterOutput)
def get_filters(query: queryJSON):
    extracted_data = json.loads(extract_info(query.query))

    return FilterOutput(
        query=extracted_data["query"],
        startDate=extracted_data["startDate"],
        endDate=extracted_data["endDate"],
        Range=extracted_data["Range"],
        typeOfWork=extracted_data["typeOfWork"],
        UNSPSCcode=extracted_data["UNSPSCcode"],
    )


@app.post("/api/getDocuments")
def get_documents(filters: filterJSON):
    model = "all-MiniLM-L6-v2"
    embeddings = SentenceTransformerEmbeddings(model_name=model)
    db_disk = Chroma(
        persist_directory="./chroma_db",
        embedding_function=embeddings,
        collection_metadata={"hnsw:space": "cosine"},
    )
    query_embedding = embeddings.embed_query(filters.query)
    matching_docs = db_disk.similarity_search_by_vector_with_relevance_scores(
        query_embedding, k=245000
    )

    result_dict = {}
    for doc, score in matching_docs:
        row_id = doc.metadata["row"]
        if row_id not in result_dict:
            doc.metadata["similarity_score"] = score
            result_dict[row_id] = doc.metadata
            result_dict[row_id].pop("row")
            result_dict[row_id].pop("start_index")
        else:
            result_dict[row_id]["similarity_score"] = min(
                result_dict[row_id]["similarity_score"], score
            )
    values_list = list(result_dict.values())

    documents = [documentJSON(**item) for item in values_list]

    return documentsJSON(documents=documents)


@app.post("/api/getSemanticScores", response_model=WordsAndScores)
def get_semantic_scores(data: QueryData):
    words_list, semantic_scores = process_csv_and_get_scores(
        data.reference_number, data.query
    )
    return {"words": words_list, "semantic_scores": semantic_scores}
