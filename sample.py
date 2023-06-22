#!/usr/bin/env python3

# An example pipeline (that gets compiled) using the Flux Operator component!
import os
import kfp
import kfp.dsl as dsl
from kfp import components


def get_current_namespace():
    """
    Get the current namespace from running node, otherwise default kubeflow
    https://github.com/kubeflow/pipelines/blob/master/components/kubeflow/pytorch-launcher/sample.py
    """
    try:
        current_namespace = open(
            "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        ).read()
    except:
        current_namespace = "kubeflow"
    return current_namespace

def get_project():
    return os.environ.get('GOOGLE_PROJECT')

@dsl.pipeline(
    name="hello-world-flux-operator",
    description="An example to run hello world with the Flux Operator.",
)
def hello_world(
    namespace: str = get_current_namespace(),
    command: str = "echo hello world",
    image: str = "ghcr.io/flux-framework/flux-restful-api:latest",
    nnodes: int = 2,
    project: str = get_project(),
):
    flux_operator_op = components.load_component_from_file("./component.yaml")

    # Launch and monitor the job with the launcher
    # We need a unique Id here, I couldn't get this one to work (I think deprecated)
    #  name=f"name-{kfp.dsl.RUN_ID_PLACEHOLDER}",

    flux_operator_op(
        namespace=namespace,
        name="hello-world-run-123",
        # Assume we can get kubectl on the command line
        local=True,
        command=command,
        nnodes=nnodes,
        image=image,
        project=project,
    )
