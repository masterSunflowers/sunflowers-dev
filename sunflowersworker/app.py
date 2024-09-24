import json
import logging
import os
import sys

import sonarqube
from flask import Flask, request
from openai import OpenAI

app = Flask(__name__)

logger = logging.Logger("worker")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

WORK_DIR = os.path.abspath(os.path.dirname(__file__))

sonar = sonarqube.SonarCloudClient(
    sonarqube_url="http://localhost:9000",
    token="squ_aaefe98d8c3aa5d713b685b60052be316f281e64",
)


def generate_code(
    prompt: str,
    context: str,
    base_url: str,
    api_key: str,
    additional_context: str = None,
):
    final_prompt = (
        "**Requirement**: Complete the function, return ONLY function body\n",
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
            model="deepseek-chat",
            messages=messages,
            stop=["```"],
        )
    except Exception as e:
        raise e
    return response.choices[0].message.content


@app.post("/v1/api/normal")
def normal_gen():
    try:
        data = json.loads(request.data)
        logger.info(type(data))
        code = generate_code(
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
        workspace_name = request.args.get("workspaceName")
        logger.info("Start to run pipeline")
        code = run_pipeline(machine_id, session_id, workspace_name, data)
        logger.info("Generate successfully")
        return {"code": code}, 200
    except Exception as e:
        logger.error(str(e))
        return {"error": str(e)}, 500



# TODO
def run_pipeline(machine_id, session_id, data):
    initial_scan(machine_id, session_id)
    for _ in range(data["maxIteration"]):
        pass
    return "So far so good" 


# TODO
def check_linting():
    pass


# TODO
def update_project(target_file: str, code: str):
    absolute_path = os.path.join(WORK_DIR, target_file)
    with open(absolute_path, "r", encoding="utf-8", errors="ignore") as f:
        file_content = f.read()
    new_content = file_content + "\n\n" + code
    with open(absolute_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(new_content)


# TODO
def store_result():
    pass


# TODO
def retrieval(prompt: str):
    return ""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=True)
