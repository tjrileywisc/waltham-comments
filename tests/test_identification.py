import pytest
import numpy as np

from lib.identification import Identifier

def test_identifier_no_matches():
    db_vector = np.zeros((128), np.float64)
    db_vector[0] = 1.0

    test_vector = np.zeros_like(db_vector)
    test_vector[-1] = 1.0
    
    test_embeddings = {
        "SPEAKER_00" : test_vector
    }
    

    identifier = Identifier({"SPEAKER_00": db_vector})
    result = identifier(test_embeddings)

    assert result[0] == Identifier.DEFAULT_SPEAKER

def test_identifier_more_speakers_in_db():
    db_vectors = np.eye(10, dtype=np.float64)
    db = {"DB_0" + str(i) : db_vectors[i] for i in range(len(db_vectors))}

    test_vectors = db_vectors.copy()[:5]
    test_data = {"SPEAKER_0" + str(i) : test_vectors[i] for i in range(len(test_vectors))}

    identifier = Identifier(db)

    result = identifier(test_data)

    assert len(result) == 5

    # they should all match the db perfectly
    for i, speaker in enumerate(result):
        assert speaker == "DB_0" + str(i)

def test_identifier_more_speakers_in_meeting():

    db_vectors = np.eye(10, dtype=np.float64)
    db_vectors = db_vectors[:5]
    db = {"DB_0" + str(i) : db_vectors[i] for i in range(len(db_vectors))}

    test_vectors = np.eye(10, dtype=np.float64)
    test_data = {"SPEAKER_0" + str(i) : test_vectors[i] for i in range(len(test_vectors))}

    identifier = Identifier(db)

    result = identifier(test_data)

    assert len(result) == 10

    # expecting the first few to match perfectly, then the rest to be mapped to the default
    for i, speaker in enumerate(result):
        if i < 5:
            assert speaker == "DB_0" + str(i)
        else:
            assert speaker == Identifier.DEFAULT_SPEAKER
