from airllm import AutoModel
from TTS.api import TTS

# Load LLM
llm = AutoModel.from_pretrained("mistralai/Mistral-7B-Instruct-v0.1")

# Load TTS
tts = TTS("tts_models/en/ljspeech/vits")

# User prompt
prompt = "Explain Newton's first law simply."

# Generate text
response = llm.generate(prompt)
print("LLM:", response)

# Convert to speech
tts.tts_to_file(text=response, file_path="julius_output.wav")

print("Voice file created: julius_output.wav")
