
import pytest
import numpy as np

from sentence_embeddings import generate_embeddings

def test_sentence_embeddings():

    test_sentence = "what a lovely day"
    
    embeddings = generate_embeddings([test_sentence])
    
    assert embeddings.dtype == np.float32
    assert embeddings.size == 384