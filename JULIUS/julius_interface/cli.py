import click
from julius_core.inference import get_model, ask

@click.command()
@click.option("--config", default=None, help="Path to model config YAML")
@click.argument("question", required=False)
def main(config, question):
    model = get_model(config)
    if question:
        print(ask(model, question))
    else:
        print("JULIUS CLI. Type 'exit' to quit.")
        while True:
            q = input("\nYou: ")
            if q.lower() == "exit":
                break
            print("JULIUS:", ask(model, q))

if __name__ == "__main__":
    main()
