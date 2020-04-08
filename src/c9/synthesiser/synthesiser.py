"""Common synthesisers and utilities"""

import os
from functools import partial

from .synthstate import SynthState

DEFAULT_REGION = "eu-west-2"


class SynthesisException(Exception):
    """General failure"""


class Synthesiser:
    pass


class TextSynth(Synthesiser):
    def __init__(self, filename, text):
        self.filename = filename
        self.text = text

    def generate(self):
        return self.text


def get_region():
    # Would be nice for this to be more easily configurable / obvious
    try:
        return os.environ["AWS_DEFAULT_REGION"]
    except KeyError:
        return DEFAULT_REGION


def bijective_map(resource_type, f_inject, state: SynthState) -> SynthState:
    # f_inject :: SynthState -> resource_type -> IacObject
    resources = state.filter_resources(resource_type)
    if not resources:
        return state

    components = list(map(partial(f_inject, state), resources))

    existing = [c.name for c in state.iac]
    for c in components:
        if c.name in existing:
            raise warnings.warn(f"{resource_type} {c.name} is already synthesised")

    return SynthState(
        # finalise will update the resources and deploy_command
        state.service_name,
        state.resources,
        state.iac + components,
        state.deploy_commands,
        state.code_dir,
    )


def surjective_map(resource_type, f_map, state: SynthState) -> SynthState:
    # f_map :: SynthState -> [resource_type] -> ServerlessComponent
    resources = state.filter_resources(resource_type)
    if not resources:
        return state

    new_component = f_map(state, resources)

    # Each surjective map should only be called once...
    for c in state.iac:
        if c.component_type == new_component.component_type:
            raise warnings.warn(f"{c.component_type} is already synthesised")

    return SynthState(
        state.service_name,
        state.resources,
        state.iac + [new_component],
        state.deploy_commands,
        state.code_dir,
    )