from .config import ModelConfig
from .model_loader import JuliusModel

def get_model(config_path=None):
    if config_path:
        config = ModelConfig.from_yaml(config_path)
    else:
        config = ModelConfig()
    return JuliusModel(config)

def ask(model, question: str) -> str:
    prompt = f"### Question:\n{question}\n\n### Answer:\n"
    return model.generate(prompt)
