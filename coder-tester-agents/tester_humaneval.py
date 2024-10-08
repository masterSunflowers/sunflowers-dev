import concurrent.futures
import copy
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

from datasets import load_dataset
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

CWD = os.path.abspath(os.path.dirname(__file__))
load_dotenv(override=True)

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_API_BASE"),
)

with open(f"{CWD}/prompts/tester_gen_prompt_humaneval.txt", "r") as f:
    tester_gen_prompt_template = f.read()

with open(f"{CWD}/prompts/tester_fix_prompt_humaneval.txt", "r") as f:
    tester_fix_prompt_template = f.read()


def extract_code_block(completion_string: str, language: str = "python") -> str:
    """Get the code block from the LLM answer

    Args:
        completion_string (str): LLM answer

    Returns:
        str: Code block
    """
    if f"```{language}" in completion_string:
        completion_string = completion_string[
            completion_string.find(f"```{language}") + len(f"```{language}") :
        ]
        completion_string = completion_string[: completion_string.find("```")]
    else:
        print("Error: No code block found")
    return completion_string


def fetch_completion(
    data_entry: dict, model: str, language: str, times: int = 2
):
    prompt = data_entry["prompt"]
    if "need_fix" in data_entry.keys() and data_entry["need_fix"] == False:
        return data_entry
    elif "need_fix" not in data_entry.keys():
        global tester_gen_prompt_template
        text = (
            f"{tester_gen_prompt_template}\n\n"
            "## Prompt 3:\n"
            f"```{language}\n"
            f"{prompt}\n"
            "```\n"
            "## Completion 3:\n"
        )
    else:
        global tester_fix_prompt_template
        text = (
            f"{tester_fix_prompt_template}\n\n"
            "#Bug info:\n"
            f"{data_entry['bug']}"
        )
    test_case_list = []
    for _ in tqdm(range(times), total=times, desc="Generating test"):
        while True:
            try:
                completions = client.chat.completions.create(
                    model=model,
                    stream=False,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a code developer assistant.",
                        },
                        {"role": "user", "content": text},
                    ],
                )
                test_case = completions.choices[0].message.content
                test_case = extract_code_block(test_case)
            except Exception as e:
                time.sleep(20)
                print(e)
                test_case = ""
            if test_case != "":
                break
        test_case_list.append(test_case)
    data_entry["test_case_list"] = test_case_list
    return data_entry


def update_test_completion(dataset: List[dict], model: str, language: str):
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_entry = {
            executor.submit(
                fetch_completion, copy.deepcopy(entry), model, language
            ): entry
            for entry in dataset
        }
        for future in tqdm(
            concurrent.futures.as_completed(future_to_entry),
            desc="Updating test",
            total=len(dataset),
        ):
            entry = future_to_entry[future]
            try:
                updated_entry = future.result()
                idx = dataset.index(entry)
                dataset[idx] = updated_entry
            except Exception as e:
                print(repr(e))
    return dataset


if __name__ == "__main__":
    model = "deepseek-coder"
    language = "python"
    with open(f"{CWD}/data/{model}_{language}.json", "r") as f:
        dataset = json.load(f)
    dataset = [entry for entry in dataset]
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_entry = {
            executor.submit(
                fetch_completion, copy.deepcopy(entry), model, language
            ): entry
            for entry in dataset
        }
        for future in tqdm(
            concurrent.futures.as_completed(future_to_entry),
            total=len(future_to_entry),
            desc="Updating test",
        ):
            entry = future_to_entry[future]
            try:
                updated_entry = future.result()
                idx = dataset.index(entry)
                dataset[idx] = updated_entry
            except Exception as e:
                print(repr(e))
    print("Generate test first time done!")
    with open(f"{CWD}/data/{model}_{language}.json", "w") as f:
        json.dump(dataset, f, indent=4)
