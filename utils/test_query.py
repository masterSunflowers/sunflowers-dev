import os
import time

import torch
from pymilvus import Collection, connections
from transformers import AutoModel, AutoTokenizer

device = "cpu"
start = time.time()
connections.connect(
    "default",
    host=os.environ.get("HOST"),
    port=os.environ.get("PORT"),
    db_name="default",
)


model_name = "Salesforce/codet5p-110m-embedding"
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
model = model.to(device)

query = 'def __call__(self, state_dict: Dict):\n    """\n    Args:\n    state_dict: A dictionary representing the given checkpoint\'s state dict.\n    """'


def encode(code_snippet):
    inputs = tokenizer(
        code_snippet, return_tensors="pt", padding=True, truncation=True
    ).to(device)
    with torch.no_grad():
        embedding = model(**inputs).cpu().numpy().ravel()
        return embedding


num_partitions = 20
partition_name_lst = [f"partition_{i + 1}" for i in range(num_partitions)]
# Load the collection into memory

collection = Collection(name="code_collection")
collection.load(partition_names=partition_name_lst)


# Search for similar code snippets
def search_code_snippets(query_prompt, top_k=10):
    query_embedding = encode(query_prompt)
    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param={"metric_type": "COSINE"},
        limit=top_k,
        output_fields=["code"],
    )
    return [hit.entity.get(field_name="code") for hit in results[0]]


outputs = search_code_snippets(query)
print("Number of output:", len(outputs))
for output in outputs:
    print(output)
    print("-" * 100)
collection.release()


connections.disconnect("default")
end = time.time()
print("Elapsed time:", end - start)
