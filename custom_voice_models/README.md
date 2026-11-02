# Custom Voice Models for Julius

Place your custom TTS voice model files in this directory.

## How to Add a Custom Voice

1. **Create an adapter class** — Subclass `CustomVoiceAdapter` from `src/voice/tts_engine.py`:

```python
# custom_voice_models/my_voice.py
from src.voice.tts_engine import CustomVoiceAdapter

class MyVoiceAdapter(CustomVoiceAdapter):
    def load(self, model_path: str) -> None:
        # Load your model from the given path
        self.model = load_my_model(model_path)

    def synthesise(self, text: str) -> bytes:
        # Convert text to WAV audio bytes
        return self.model.generate_wav(text)
```

2. **Set environment variables** in `.env`:

```env
JULIUS_VOICE_ADAPTER=custom_voice_models.my_voice.MyVoiceAdapter
JULIUS_VOICE_MODEL_PATH=custom_voice_models/my_model.bin
```

3. **Restart the server** — Julius will automatically load your custom voice.

## Supported Formats

- The `synthesise()` method must return **WAV audio bytes** (16-bit PCM, mono, 16kHz recommended).
- Model files can be in any format your adapter can read.

## Built-in Voice

By default, Julius uses the macOS **Samantha** voice via the `say` command.
You can change the voice by setting `JULIUS_VOICE_NAME` in `.env` to any
available system voice (run `say --voice "?"` to list all).
