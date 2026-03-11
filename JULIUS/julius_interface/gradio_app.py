import gradio as gr
from julius_core.inference import get_model, ask

model = get_model()

def respond(message, history):
    return ask(model, message)

gr.ChatInterface(
    respond,
    title="JULIUS - Scientific Assistant",
    description="Ask me anything about math, physics, chemistry."
).launch()
