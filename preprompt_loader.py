import os


def load_preprompts(folder, preprompt_names: list[str]) -> dict[str, str]:
    preprompts = {name: "" for name in preprompt_names}
    for name in preprompts:
        with open(os.path.join(folder, name + ".txt"), "r") as f:
            preprompts[name] = f.read()
    return preprompts
