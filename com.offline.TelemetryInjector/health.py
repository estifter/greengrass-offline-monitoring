import subprocess as sp
import re
import json
from typing import List, Dict


def list_components() -> str:
    cmd = "/greengrass/v2/bin/greengrass-cli component list"
    try:
        proc = sp.run(cmd, capture_output=True, shell=True, check=True)
        return proc.stdout.decode()
    except sp.CalledProcessError as e:
        raise ValueError(f"list_components() failed: {e.stderr.decode()}")


def get_all_components() -> List[Dict[str, str]]:
    list_component_output = list_components()
    pattern = (
        rf"^Component Name: (.*)$\n"
        r"    Version: (.*)$\n    State: (.*)$\n"
        r"    Configuration: (.*)$"
    )
    matches = re.findall(pattern, list_component_output, re.M)
    components = []
    for m in matches:
        if m and m[0] and m[1] and m[2] and m[3]:
            components.append(
                {
                    "name": m[0],
                    "version": m[1],
                    "state": m[2],
                    "configuration": json.loads(m[3]),
                }
            )
    if len(components) > 0:
        return components
    raise ValueError(f"could not find any components: {list_component_output}")


def get_all_components_states() -> List[Dict[str, str]]:
    all_components = get_all_components()
    return [{"name": c["name"], "state": c["state"]} for c in all_components]
