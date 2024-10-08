import concurrent.futures
import copy
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Literal

from datasets import load_dataset
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

CWD = os.path.abspath(os.path.dirname(__file__))
load_dotenv(override=True)

# Setting API parameters
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_API_BASE"),
)

dataset = load_dataset("openai_humaneval", split="test")
dataset = [entry for entry in dataset]


with open(f"{CWD}/prompts/coder_gen_prompt_humaneval.txt", "r") as f:
    coder_generate_prompt_template = f.read()

with open(f"{CWD}/prompts/coder_fix_prompt_humaneval.txt", "r") as f:
    coder_fix_prompt_template = f.read()


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
    data_entry: dict,
    model: str,
    language: str = "python",
    times: int = 1,
) -> dict:
    """Get code completion response

    Args:
        data_entry (dict): Information about a HumanEval task
        model (str): Model ID
        language (str, optional): Code language. Defaults to "python".
        times (int, optional): Max try times. Defaults to 5.
        mode (str):
    Returns:
        dict: Information about a HumanEval task after update
    """
    prompt = data_entry["prompt"]
    if "need_fix" in data_entry.keys() and data_entry["need_fix"] == False:
        return data_entry
    elif "need_fix" not in data_entry.keys():
        global coder_generate_prompt_template
        complete_prompt = (
            f"{coder_generate_prompt_template}\n\n"
            "## Prompt 3:\n"
            f"```{language}\n"
            f"{prompt}\n"
            "```\n"
            "## Completion 3:\n"
        )
    else:
        global coder_fix_prompt_template
        complete_prompt = (
            f"{coder_fix_prompt_template}\n\n"
            "#Bug info:\n"
            f"{data_entry['bug']}"
        )

    completions_code = []
    for i in range(times):
        while True:
            try:
                completions = client.chat.completions.create(
                    model=model,
                    stream=False,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a software programmer.",
                        },
                        {"role": "user", "content": complete_prompt},
                    ],
                )
                completion = completions.choices[0].message.content
                code_block = extract_code_block(completion)
            except Exception as e:
                print(repr(e))
                time.sleep(10)
                code_block = ""
            if code_block != "":
                break
        completions_code.append(code_block)
    data_entry["completion_list"] = completions_code
    return data_entry


def update_code_completion(dataset: List[dict], model: str, language: str):
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_entry = {
            executor.submit(
                fetch_completion, copy.deepcopy(entry), model, language
            ): entry
            for entry in dataset
        }
        for future in tqdm(
            concurrent.futures.as_completed(future_to_entry),
            desc="Updating code",
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
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_entry = {
            executor.submit(
                fetch_completion, copy.deepcopy(entry), model, language, 1
            ): entry
            for entry in dataset
        }
        for future in tqdm(
            concurrent.futures.as_completed(future_to_entry),
            total=len(future_to_entry),
            desc="Generating code",
        ):
            entry = future_to_entry[future]
            try:
                updated_entry = future.result()
                idx = dataset.index(entry)
                dataset[idx] = updated_entry
            except Exception as e:
                print(repr(e))
    print("Generate code first time done!")
    with open(f"{CWD}/data/{model}_{language}.json", "w") as f:
        json.dump(dataset, f, indent=4)
