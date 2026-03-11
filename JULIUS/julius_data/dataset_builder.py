from datasets import load_dataset
import os

def prepare_training_data(output_path="data/train.jsonl"):
    os.makedirs("data", exist_ok=True)
    dataset = load_dataset("camel-ai/physics", split="train")

    def format_conversation(example):
        return {
            "text": f"### Instruction:\n{example['message_1']}\n\n### Response:\n{example['message_2']}"
        }

    formatted = dataset.map(format_conversation)
    formatted.select_columns(["text"]).to_json(output_path, lines=True)
    print(f"Saved {len(formatted)} examples to {output_path}")

if __name__ == "__main__":
    prepare_training_data()
