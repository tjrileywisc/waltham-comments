
from . import MODELS_DIR, TEXT

import os
import pickle as pkl
import pandas as pd
import glob

from sentence_transformers import SentenceTransformer

import numpy as np
from numpy.typing import NDArray

def generate_embeddings(sentences: list[str]) -> NDArray[np.float32]:

    os.makedirs(MODELS_DIR, exist_ok=True)

    model = SentenceTransformer('all-MiniLM-L6-v2', cache_folder=MODELS_DIR)

    return model.encode(sentences, precision="float32")

def generate_database():
    """
    Read through all transcription results, generating embedding vectors for each sentence.
    """

    csvs = glob.glob("transcriptions/*.csv")
    
    for csv in csvs:
        df = pd.read_csv(csv)
        sentences = df[TEXT].to_list()
        
        embeddings = generate_embeddings(sentences)
        print(embeddings)

if __name__ == "__main__":
    generate_database()