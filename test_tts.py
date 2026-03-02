from TTS.api import TTS

tts = TTS("tts_models/en/ljspeech/vits")
tts.tts_to_file(
    text="This is Julius speaking.",
    file_path="output.wav"
)
