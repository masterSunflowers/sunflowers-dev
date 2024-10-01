import json
import os

import dotenv
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    Index,
    connections,
    utility,
)

# Connect to Milvus
dotenv.load()
connections.connect(
    "default",
    host=os.environ.get("HOST"),
    port=os.environ.get("PORT"),
    db_name="default",
)

# collection = Collection(name="code_collection")

# partition_name_lst = [f"partition_{idx + 1}" for idx in range(20)]
# collection.load(partition_names=partition_name_lst)
# res = collection.query(
#   expr="",
#   output_fields = ["count(*)"],
# )
# print(res)
# print(res[0])

# Define collection schema
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=256),
    FieldSchema(
        name="prompt",
        dtype=DataType.VARCHAR,
        description="Prompt",
        max_length=65535,
    ),
    FieldSchema(
        name="signature",
        dtype=DataType.VARCHAR,
        description="Signature",
        max_length=65535,
    ),
    FieldSchema(
        name="docstring",
        dtype=DataType.VARCHAR,
        description="Docstring",
        max_length=65535,
    ),
    FieldSchema(
        name="code",
        dtype=DataType.VARCHAR,
        description="Code",
        max_length=65535,
    ),
]

schema = CollectionSchema(fields, description="Code Collection")
collection = Collection(name="code_collection", schema=schema)
# Create an index for the embedding field
index_params = {
    "metric_type": "COSINE",
    "index_type": "IVF_FLAT",
    "params": {"nlist": 128},
}
index = Index(collection, "embedding", index_params)
print("Index created successfully.")

import os

import numpy as np
import pandas as pd
from tqdm import tqdm

WORK_DIR = os.path.abspath(os.path.dirname(__file__))

df = pd.read_parquet(os.path.join(WORK_DIR, "database.parquet"))
df = df[["embedding", "prompt", "signature", "docstring", "code"]]
num_partitions = 20
partitions = np.array_split(df, num_partitions)
for idx in tqdm(range(5, num_partitions), desc="Inserting snippet code"):
    collection.create_partition(partition_name=f"partition_{idx + 1}")
    mr = collection.insert(
        data=partitions[idx], partition_name=f"partition_{idx + 1}"
    )
    print("Inserted:", mr.insert_count)


# Disconnect
connections.disconnect("default")
