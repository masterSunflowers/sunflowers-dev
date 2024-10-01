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
SONAR_TOKEN = "squ_3079d50dd62445c56b43615807376510e8a3f003"
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
        "**Requirement**: Complete the function body\n",
        "\n"
        "**Context**:\n"
        f"{context}\n"
        "\n"
        "**Function**:\n"
        f"{prompt}\n"
        "\n\n"
        "**Some similar code snippets**:\n"
        f"{additional_context}\n"
        "**Body**:",
    )
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        messages = [
            {
                "role": "system",
                "content": "You are a professional developer. You must return ONLY function body",
            },
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
    messages.append(response.choices[0].message)
    return response.choices[0].message.content, messages


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
        try:
            remove_already_project(f"{machine_id}--{session_id}")
        except Exception as e:
            raise e
        logger.debug("Start get initial issues")
        initial_issues, num_initial_issue = get_issues(
            f"{machine_id}--{session_id}", "0.0"
        )
        logger.debug("Got initial issues")
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
        logger.debug(f"Iteration {i}:")
        logger.debug("Start update project")
        update_project(data["targetFile"], code)
        logger.debug("Updated project")
        logger.debug(f"Version: {i}.0")
        issues, num_issue = get_issues(f"{machine_id}--{session_id}", f"{i}.0")
        logger.debug(f"Num issue at version {i}.0: {num_issue}")
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
        else:
            logger.debug(f"Generate report time: {elapsed_time}")
        page = 1
        page_size = 100
        response = requests.get(
            url="http://34.70.219.18:9000/api/issues/search",
            headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
            params={"p": page, "ps": page_size},
        )
        total = response.json()["total"]
        issues = {}
        while page * page_size - 100 < total:
            response = requests.get(
                url="http://34.70.219.18:9000/api/issues/search",
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
    logger.debug("Start scan project")
    start_time = time.time()
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
        end_time = time.time()
        logger.debug("Scanning time: {:.2f}".format((end_time - start_time)))
        output_lines = res.stdout.splitlines()
        pattern = "http://34.70.219.18:9000/api/ce/task?id="
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
    idx = last_func_start_idx - 1
    tab = ""
    while idx >= 0 and file_content[idx] == " ":
        idx -= 1
    tab = " " * (last_func_start_idx - idx - 1)
    loc = code.splitlines()
    for i in range(1, len(loc)):
        loc[i] = tab + loc[i]

    adapted_code = "\n".join(loc)
    new_content = file_content[:last_func_start_idx] + adapted_code
    logger.debug(f"New content of target file:\n\n {new_content}")
    with open(absolute_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(new_content)


# TODO
def retrieval(prompt: str):
    return ""


def remove_already_project(project_key: str):
    logger.debug("Start remove already project")
    response = requests.post(
        url="http://34.70.219.18:9000/api/projects/delete",
        headers={"Authorization": f"Bearer {SONAR_TOKEN}"},
        params={"project": project_key},
    )
    if response.status_code == 204:
        logger.info("Removed already project")
    elif response.status_code == 404:
        logger.info("The project is not exist")
    else:
        raise Exception(
            f"Status code: {response.status_code}\n{response.content}"
        )


def check_code_issue(issues):
    logger.debug("Start check code issue")
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
