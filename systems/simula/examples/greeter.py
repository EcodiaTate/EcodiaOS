# greeter.py


def greet(name: str) -> str:
    """Returns a greeting message for the given name."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Greet a person.")
    parser.add_argument("--name", type=str, required=True, help="Name of the person to greet")
    args = parser.parse_args()
    print(greet(args.name))
