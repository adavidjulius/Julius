from airllm import AutoModel

model = AutoModel.from_pretrained(
    "mistralai/Mistral-7B-Instruct-v0.1"
)

def generate_response(prompt):
    response = model.generate(prompt)
    return response
