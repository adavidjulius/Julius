import yaml
from dataclasses import dataclass

@dataclass
class ModelConfig:
    model_name: str = "mistralai/Mistral-7B-v0.1"
    device: str = "cuda"
    max_new_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.95
    repetition_penalty: float = 1.1

    @classmethod
    def from_yaml(cls, path):
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        return cls(**data)
