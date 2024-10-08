import concurrent.futures
import json
import os
from typing import List

from tqdm import tqdm

from coder_humaneval import update_code_completion
from execution_helper import check_correctness, self_test
from tester_humaneval import update_test_completion

CWD = os.path.abspath(os.path.dirname(__file__))


def executor(
    dataset: List[dict], language: str = "python", threshold: float = 0.5
):
    print("==============Start Executing==============")

    def process_item(i):
        if "need_fix" in dataset[i].keys() and dataset[i]["need_fix"] == False:
            return dict(
                completion=dataset[i]["completion"], need_fix=False, bug=None
            )
        problem = dataset[i]
        completion_list = problem["completion_list"]
        test_suite_list = problem["test_case_list"]
        correct_list = []
        bugs = []
        for j in range(len(completion_list)):
            correct = 0
            bug = (
                "## Prompt 3:\n"
                f"```python\n{problem['prompt']}```\n"
                "\n"
                "## Completion 3:"
                f"```python\n{completion_list[j]}```\n"
                "\n"
                "## Bug 3:\n"
                "\n"
            )
            for k in range(len(test_suite_list)):
                result = self_test(
                    problem=problem,
                    completion=completion_list[j],
                    test_suite=test_suite_list[k],
                    timeout=5.0,
                    completion_id=j,
                    test_suite_id=k,
                )
                if result["passed"]:
                    correct += 1
                else:
                    bug += (
                        f"### Test suite {k}:\n"
                        f"```python\n{result['test_suite']}```\n"
                        "\n"
                        f"### Error test suite {k}:\n"
                        f"```bash\n{result['result']}```\n"
                        "\n"
                    )
            correct_list.append(correct)
            bugs.append(bug)

        max_correct = max(correct_list)
        idx = correct_list.index(max_correct)
        return dict(
            completion=completion_list[idx],
            need_fix=(max_correct < threshold * len(test_suite_list)),
            bug=bugs[idx],
        )

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(process_item, i) for i in range(len(dataset))
        ]

        for future in tqdm(
            concurrent.futures.as_completed(futures), total=len(dataset)
        ):
            i = futures.index(future)
            result = future.result()
            dataset[i]["need_fix"] = result["need_fix"]
            dataset[i]["completion"] = result["completion"]
            dataset[i]["bug"] = result["bug"]

    print(
        "Executor pass rate: {:.2f}".format(
            sum([not problem["need_fix"] for problem in dataset])
            / len(dataset)
            * 100
        )
    )
    return dataset


def test_report(
    dataset: List[dict], language: str = "python", iteration: int = 0
):
    print("==============Start Report Testing==============")
    pass_problem = 0
    for problem in tqdm(dataset, total=len(dataset), desc="Testing"):

        test_result = check_correctness(
            problem=problem,
            completion=problem["completion_list"][0],
            timeout=5.0,
            completion_id=0,
        )
        pass_problem += test_result["passed"]
    print("Pass rate: {:.2f}".format(pass_problem / len(dataset) * 100))


if __name__ == "__main__":
    model = "deepseek-coder"
    language = "python"

    path = f"{CWD}/data/{model}_{language}_1.json"
    iteration = 1
    for cur_it in range(1, iteration + 1):
        with open(path, "r") as f:
            dataset = json.load(f)
        dataset = dataset[:1]
        if cur_it == 1:
            print("Result before fixing:")
            test_report(dataset)
        print("\n" + "-" * 100 + "\n")
        print("Fixing iteration", cur_it)
        dataset = executor(dataset)
        dataset = update_code_completion(dataset, model, language)
        dataset = update_test_completion(dataset, model, language)

        print("\n" + "-" * 100 + "\n")
        print(f"Result after fixing {cur_it} times:")
        test_report(dataset, iteration=cur_it)
        path = f"{CWD}/data/{model}_{language}_{cur_it}.json"
        with open(path, "w") as f:
            json.dump(dataset, f, indent=4)
