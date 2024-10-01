import pandas as pd

check = pd.read_parquet("embedded.parquet")
check.info()

check["len_code"] = check["code"].apply(lambda code: len(code))
check["len_docstring"] = check["docstring"].apply(
    lambda docstring: len(docstring)
)
check["len_signature"] = check["signature"].apply(
    lambda signature: len(signature)
)
check["len_prompt"] = check["prompt"].apply(lambda prompt: len(prompt))

check.describe()

check = check[check["len_code"] <= 65535]
check = check[check["len_docstring"] <= 65535]
check = check[check["len_signature"] <= 65535]
check = check[check["len_prompt"] <= 65535]

check.reset_index(drop=True, inplace=True)
check = check[["embedding", "prompt", "signature", "docstring", "code"]]
check.info()
check.to_parquet("database.parquet")
