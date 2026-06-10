import os
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

MODELS_DIR = os.environ.get("MODELS_DIR", "models")

app = FastAPI()
model = SentenceTransformer("all-MiniLM-L6-v2", cache_folder=MODELS_DIR)


class EmbeddingsRequest(BaseModel):
    sentences: list[str]


class EmbeddingsResponse(BaseModel):
    embeddings: list[list[float]]


@app.post("/embeddings", response_model=EmbeddingsResponse)
def generate_embeddings(request: EmbeddingsRequest):
    embeddings = model.encode(request.sentences, precision="float32")
    return EmbeddingsResponse(embeddings=embeddings.tolist())
