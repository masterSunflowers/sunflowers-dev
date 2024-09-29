import json
import logging
import os
import subprocess
import sys
import time
from typing import Dict, List, Tuple

import requests
from flask import Flask, request
from openai import OpenAI

app = Flask(__name__)

logger = logging.Logger("worker")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

WORK_DIR = os.path.abspath(os.path.dirname(__file__))
SONAR_TOKEN = "squ_4ad3cba8858c0c21feae14a1c619e6855ddbc98c"
SONAR_SOURCES = "/workspace/project/"
SONAR_PROJECT_BASE_DIR = "/workspace/project/"


def generate_code(
    prompt: str,
    context: str,
    base_url: str,
    api_key: str,
    additional_context: str = None,
):
    final_prompt = (
        "**Requirement**: Complete the function\n",
        "\n"
        "**Code**:\n"
        f"{context}\n"
        "\n"
        f"{prompt}\n"
        "\n\n"
        "**Some similar code snippets**:\n"
        f"{additional_context}",
    )
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        messages = [
            {"role": "system", "content": "You are a professional developer."},
            {"role": "user", "content": str(final_prompt)},
            {"role": "assistant", "content": "```python\n", "prefix": True},
        ]
        response = client.chat.completions.create(
            model="deepseek-coder",
            messages=messages,
            stop=["```"],
        )
    except Exception as e:
        raise e
    # return response.choices[0].message.content, messages.append(
    #     response.choices[0].message
    # )
    code = """
def _unix_pattern_to_parameter_names(
    constraints: List[str], all_parameter_names: Set[str]
) -> Union[None, Set[str]]:
    \"\"\"
    Convert Unix-style patterns in constraints to a set of parameter names.

    Args:
        constraints (List[str]): List of Unix-style patterns to match against parameter names.
        all_parameter_names (Set[str]): Set of all available parameter names.

    Returns:
        Union[None, Set[str]]: Set of parameter names that match the constraints, or None if no matches are found.
    \"\"\"
    matchedParameters = set()

    for pattern in constraints:
        for param_name in all_parameter_names:
            if fnmatch.fnmatch(param_name, pattern):
                matchedParameters.add(param_name)

    return matchedParameters if matchedParameters else None"""
    response.choices[0].message.content = code
    messages.append(response.choices[0].message)
    return code, messages


@app.post("/v1/api/normal")
def normal_gen():
    try:
        logger.info("Have received normal generate request!")
        data = json.loads(request.data)
        code, _ = generate_code(
            data["prompt"], data["context"], data["baseUrl"], data["apiKey"]
        )
        logger.info("Generate successfully")
        return {"code": code}, 200
    except Exception as e:
        logger.error(e)
        return {"error": str(e)}, 500


@app.post("/v1/api/advanced")
def advanced_gen():
    try:
        logger.info("Have received advanced generate request!")
        data = json.loads(request.data)
        machine_id = request.args.get("machineId")
        session_id = request.args.get("sessionId")
        logger.info("Start to run pipeline")
        code = run_pipeline(machine_id, session_id, data)
        logger.info("Generate successfully")
        return {"code": code}, 200
    except Exception as e:
        logger.error(str(e))
        return {"error": str(e)}, 500


def run_pipeline(machine_id, session_id, data):
    try:
        logger.debug(f"Machine ID: {machine_id}")
        logger.debug(f"Session ID: {session_id}")
        remove_already_project(f"{machine_id}--{session_id}")
        initial_issues, num_initial_issue = get_issues(
            f"{machine_id}--{session_id}", "0.0"
        )
        logger.debug(f"Num initial issue: {num_initial_issue}")
        with open("initial_issues.json", "w") as f:
            json.dump(initial_issues, f)
    except Exception as e:
        raise e
    retrieved_context = retrieval(data["prompt"])
    code, messages = generate_code(
        data["prompt"],
        data["context"],
        data["baseUrl"],
        data["apiKey"],
        retrieved_context,
    )

    for i in range(1, data["maxIteration"]):
        update_project(data["targetFile"], code)
        logger.debug(f"Version: {i + 1}.0")
        issues, num_issue = get_issues(f"{machine_id}--{session_id}", f"{i}.0")
        logger.debug(f"Num issue at version {i + 1}.0: {num_issue}")
        generated_code_issues = check_code_issue(issues)
        logger.debug(f"Generated code issues: {generated_code_issues}")
        if not generated_code_issues:
            break
        fixed_code, messages = fix_code(
            messages, generated_code_issues, data["apiKey"], data["baseUrl"]
        )
        code = fixed_code
    return code


def get_issues(project_key: str, version: str) -> Tuple[Dict, str]:
    try:
        task_status_url = scan(project_key, project_key, version)
        if not task_status_url:
            raise Exception("Can not find task_id")
    except Exception as e:
        logger.error(e)
        raise Exception(f"Can not scan project {project_key}")
    try:
        logger.debug("Nice try")
        response = requests.get(
            url=task_status_url,
            headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
        )
        logger.debug(response.status_code)
        response = response.json()
        report_processing_status = response["task"]["status"]
        logger.debug(f"Report processing status: {report_processing_status}")
        timeout = 30
        elapsed_time = 0
        stop_time = 1
        while report_processing_status != "SUCCESS" and elapsed_time < timeout:
            time.sleep(stop_time)
            elapsed_time += stop_time
            response = requests.get(
                url=task_status_url,
                headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
            )
            report_processing_status = response.json()["task"]["status"]
            logger.debug(
                f"Report processing status: {report_processing_status}"
            )
        if elapsed_time >= timeout:
            raise TimeoutError("Report processing timeout")
        page = 1
        page_size = 100
        response = requests.get(
            url="https://snipe-related-possibly.ngrok-free.app/api/issues/search",
            headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
            params={"p": page, "ps": page_size},
        )
        total = response.json()["total"]
        issues = {}
        while page * page_size - 100 < total:
            response = requests.get(
                url="https://snipe-related-possibly.ngrok-free.app/api/issues/search",
                headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
                params={"p": page, "ps": page_size},
            )
            issues_in_page = {
                issue["key"]: issue for issue in response.json()["issues"]
            }
            issues.update(issues_in_page)
            page += 1
        return issues, total
    except Exception as e:
        raise e


def scan(project_key: str, project_name: str, version: str):
    cmd = (
        "sonar-scanner -X "
        f'-D"sonar.token={SONAR_TOKEN}" '
        f'-D"sonar.projectKey={project_key}" '
        f'-D"sonar.projectName={project_name}" '
        f'-D"sonar.projectVersion={version}" '
        f'-D"sonar.sources={SONAR_SOURCES}" '
        f'-D"sonar.projectBaseDir={SONAR_PROJECT_BASE_DIR}" '
        '-D"sonar.scm.disabled=True"'
    )
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode == 0:
        logger.info("Scanned project")
        output_lines = res.stdout.splitlines()
        pattern = (
            "https://snipe-related-possibly.ngrok-free.app/api/ce/task?id="
        )
        for line in output_lines:
            if line.find(pattern) >= 0:
                task_status_url = line[line.find(pattern) :]
                logger.debug(task_status_url)
                return task_status_url
        return None
    else:
        raise Exception("\nSTDOUT:\n" + res.stdout + "\nSTDERR\n" + res.stderr)


def update_project(target_file: str, code: str):
    absolute_path = os.path.join(WORK_DIR, "project", target_file)
    with open(absolute_path, "r", encoding="utf-8", errors="ignore") as f:
        file_content = f.read()
    last_func_start_idx = file_content.rfind("def ")
    new_content = file_content[:last_func_start_idx] + code
    logger.debug(f"New content of target file {new_content}")
    with open(absolute_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(new_content)


# TODO
def retrieval(prompt: str):
    return ""


def remove_already_project(project_key: str):
    response = requests.get(
        url="https://snipe-related-possibly.ngrok-free.app/api/projects/delete",
        headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
        params={"project": project_key},
    )
    if response.status_code == 200:
        logger.info("Removed already project")
    elif response.status_code == 404:
        logger.info("The project is not exist")
    else:
        logger.error(f"Encounter error: {response.content}")


def check_code_issue(issues):
    try:
        with open("initial_issues.json", "r") as f:
            initial_issues = json.load(f)

        logger.debug(f"Num initial issues: {len(initial_issues)}")
        logger.debug(f"Num issues: {len(issues)}")
        new_issues = {
            key: issue
            for key, issue in issues.items()
            if key not in initial_issues
        }
        message = "\n".join(
            [new_issues[issue]["message"] for issue in new_issues]
        )
        logger.debug(message)
        return message
    except Exception as e:
        logger.error(f"Check code issue {issues}")
        raise e


def fix_code(
    messages: List, issue: str, api_key: str, base_url: str
) -> Tuple[str, List]:
    prev_answer = messages[-1]
    code = prev_answer.content
    new_command = (
        "The code snippet:\n"
        f"{code}\n"
        "need to fix following these guildlines:\n"
        f"{issue}\n"
        "**Requirement**: Fix the code"
    )
    logger.debug(new_command)
    messages = messages[:-2]
    messages.append(prev_answer)
    messages.append({"role": "user", "content": new_command})
    messages.append(
        {"role": "assistant", "content": "```python\n", "prefix": True}
    )
    logger.debug(messages)
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        response = client.chat.completions.create(
            model="deepseek-coder",
            messages=messages,
            stop=["```"],
        )
        messages.append(response.choices[0].message)
        return response.choices[0].message.content, messages
    except Exception as e:
        raise e


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
