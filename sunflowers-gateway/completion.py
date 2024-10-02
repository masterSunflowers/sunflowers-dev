from openai import OpenAI


def normal_complete(data):
    try:
        client = OpenAI(
            api_key=data["apiKey"],
            base_url=data["baseUrl"],
        )
        messages = [
            {
                "role": "system",
                "content": "You are a professional python developer",
            },
            {"role": "user", "content": data["prompt"]},
            {"role": "assistant", "content": "```python\n", "prefix": True},
        ]
        response = client.chat.completions.create(
            model="deepseek-coder",
            messages=messages,
            stop=["```"],
        )
        print(response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        raise e


def advanced_complete(data):
    api_key = data["apiKey"]
    base_url = data["baseUrl"]
    prompt = data["prompt"]

    sig_doc = prompt[prompt.rfind("def ") :]
