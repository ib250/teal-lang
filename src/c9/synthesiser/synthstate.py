"""Hold state in the synthesis pipeline"""

import os
from os.path import dirname, join


class SynthState:
    def __init__(self, name, resources: set, iac, deploy_commands, code_dir):
        self.service_name = name.replace(" ", "-")
        self.resources = set(resources)
        self.iac = iac
        self.deploy_commands = deploy_commands
        self.code_dir = code_dir

    def filter_resources(self, rtype) -> set:
        return [r.infra_spec for r in self.resources if isinstance(r, rtype)]

    def gen_iac(self, path):
        """Write the IAC to files in path"""
        for generator in self.iac:
            the_dir = dirname(generator.filename)
            if the_dir:
                os.makedirs(join(path, the_dir), exist_ok=True)
            with open(join(path, generator.filename), "a") as f:
                f.write(generator.generate())
                f.write("\n")

        with open(join(path, "deploy.sh"), "w") as f:
            f.write("#!/usr/bin/env bash\n")
            f.write("set -xe\n")
            f.write("\n".join(self.deploy_commands))

    def show(self):
        print("Resources:", self.resources)
        print("IAC:", self.iac)
        print("Deploy:", self.deploy_commands)
