#!/usr/bin/env python3
# coding: utf-8

# This will deploy (and monitor) a job for a MiniCluster.
# It is intended for deployment as a Kubeflow pipeline component
# https://www.kubeflow.org/docs/components/pipelines/v1/sdk/component-development/#design
# although you can also test it locally with a cluster like kind!

# Set logging level first thing!
import logging

logging.basicConfig()

import argparse
import os
import sys

import requests

import kubescaler.utils as utils

# This will allow us to create and interact with our cluster on GKE
# We can customize this for AWS if needed
from kubescaler.scaler import GKECluster

from fluxoperator.client import FluxMiniCluster
from kubernetes import client as kubernetes_client
from kubernetes import utils as k8sutils
from kubernetes.client.api import core_v1_api
from kubernetes import config as k8sconfig

# Save data here
here = os.path.abspath(os.path.dirname(__file__))

# Default flux operator yaml URL
default_flux_operator_yaml = "https://raw.githubusercontent.com/flux-framework/flux-operator/main/examples/dist/flux-operator.yaml"


# Here is our main container
def get_minicluster(
    command,
    size=4,
    tasks=None,  # nodes * cpu per node, where cpu per node is vCPU / 2
    cpu_limit=None,
    memory_limit=None,
    flags=None,
    name=None,
    namespace=None,
    image=None,
    wrap=None,
    log_level=7,
    flux_user=None,
    zeromq=False,
    quiet=False,
    strict=False,
):
    """
    Get a MiniCluster CRD as a dictionary

    Limits should be slightly below actual pod resources. The curve cert and broker config
    are required, since we need this external cluster to connect to ours!
    """
    flags = flags or "-ompi=openmpi@5 -c 1 -o cpu-affinity=per-task"
    image = image or "ghcr.io/flux-framework/flux-restful-api"
    container = {"image": image, "command": command, "resources": {}}

    if cpu_limit is None and memory_limit is None:
        del container["resources"]
    elif cpu_limit is not None or memory_limit is not None:
        container["resources"] = {"limits": {}, "requests": {}}
    if cpu_limit is not None:
        container["resources"]["limits"]["cpu"] = cpu_limit
        container["resources"]["requests"]["cpu"] = cpu_limit
    if memory_limit is not None:
        container["resources"]["limits"]["memory"] = memory_limit
        container["resources"]["requests"]["memory"] = memory_limit

    # Do we have a custom flux user for the container?
    if flux_user:
        container["flux_user"] = {"name": flux_user}

    # The MiniCluster has the added name and namespace
    mc = {
        "size": size,
        "namespace": namespace,
        "name": name,
        "interactive": False,
        "logging": {"zeromq": zeromq, "quiet": quiet, "strict": strict},
        "flux": {
            "option_flags": flags,
            "connect_timeout": "5s",
            "log_level": log_level,
        },
    }

    if tasks is not None:
        mc["tasks"] = tasks

    # eg., this would require strace "strace,-e,network,-tt"
    if wrap is not None:
        mc["flux"]["wrap"] = wrap
    return mc, container


def get_parser():
    parser = argparse.ArgumentParser(
        description="KubeFlow Bursting",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--project", help="Google Cloud project")
    parser.add_argument("--cluster-name", help="Cluster name", default="flux-cluster")
    parser.add_argument(
        "--machine-type", help="Google machine type", default="c2-standard-8"
    )
    parser.add_argument(
        "--cpu-limit", dest="cpu_limit", help="CPU limit", default=None, type=int
    )
    parser.add_argument("--outfile", help="Save to this output file")
    parser.add_argument("--memory-limit", dest="memory_limit", help="Memory limit")
    parser.add_argument("--image", help="Container image for MiniCluster")
    parser.add_argument("--command", help="Command for the MiniCluster")
    parser.add_argument(
        "--nnodes", help="Number of nodes (each with one pod)", default=None, type=int
    )
    parser.add_argument("--ntasks", help="Number of tasks", default=None, type=int)
    parser.add_argument(
        "--log-level",
        help="Logging level for flux",
        default=7,
        type=int,
    )
    parser.add_argument(
        "--namespace", help="Namespace for external cluster", default="flux-operator"
    )
    parser.add_argument(
        "--local",
        help="Deploy to local cluster (already active with kubectl)",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--debug",
        help="Enable debug (Python) logging",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--zeromq", help="Enable zeromq logging", action="store_true", default=False
    )
    parser.add_argument(
        "--quiet", help="Enable quiet logging", action="store_true", default=False
    )
    parser.add_argument(
        "--strict",
        help="Enable strict mode logging",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--name", help="Name for the MiniCluster", default="flux-sample"
    )
    parser.add_argument("--flux-operator-yaml", dest="flux_operator_yaml")
    parser.add_argument("--flux-user", help="custom flux user (defaults to flux)")
    parser.add_argument(
        "--wrap", help='arguments to flux wrap, e.g., "strace,-e,network,-tt'
    )
    return parser


def get_local_kubectl():
    """
    Get a local core_v1 API to connect to a running cluster.
    """
    k8sconfig.load_kube_config()
    return core_v1_api.CoreV1Api()


def ensure_flux_operator_yaml(args):
    """
    Ensure we are provided with the installation yaml and it exists!
    """
    # Boolean to determine if we should cleanup
    cleanup = False

    # Are we retrieving a remote URL?
    is_remote = args.flux_operator_yaml.startswith("http")

    # If we are given a url address
    if not args.flux_operator_yaml or is_remote:
        download_file = (
            default_flux_operator_yaml if not is_remote else args.flux_operator_yaml
        )
        args.flux_operator_yaml = utils.get_tmpfile(prefix="flux-operator") + ".yaml"
        r = requests.get(download_file, allow_redirects=True)
        utils.write_file(r.content.decode("utf-8"), args.flux_operator_yaml)
        cleanup = True

    # Ensure it really really exists
    args.flux_operator_yaml = os.path.abspath(args.flux_operator_yaml)
    if not os.path.exists(args.flux_operator_yaml):
        sys.exit(f"{args.flux_operator_yaml} does not exist.")
    return cleanup


def write_minicluster_yaml(mc):
    """
    Write the MiniCluster spec to yaml to apply
    """
    # this could be saved for reproducibility, if needed.
    minicluster_yaml = utils.get_tmpfile(prefix="minicluster") + ".yaml"
    utils.write_yaml(mc, minicluster_yaml)
    return minicluster_yaml


def main():
    """
    Create an external cluster we can burst to, and optionally resize.
    """
    parser = get_parser()

    # If an error occurs while parsing the arguments, the interpreter will exit with value 2
    args, _ = parser.parse_known_args()
    if not args.project and not args.local:
        sys.exit(
            "Please define your Google Cloud Project with --project or specify --local for an existing cluster."
        )

    # Enable debug logging?
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Required to specify nodes
    if not args.nnodes:
        sys.exit("You must specify number of nodes with --nnodes")

    # Pull cluster name out of argument
    cluster_name = args.cluster_name
    print(f"📛️ Bursed FluxOperator job cluster name will be {cluster_name}")
    print(f"📦️ We will use {args.nnodes} nodes.")
    cleanup = ensure_flux_operator_yaml(args)

    # Default crd_api will be generated by operator
    crd_api = None

    # Try creating the cluster (this is just the GKE cluster)
    # n2-standard-8 has 4 actual cores, so 4x4 == 16 tasks
    if args.project:
        cli = GKECluster(
            project=args.project,
            name=cluster_name,
            node_count=args.nnodes,
            machine_type=args.machine_type,
            min_nodes=args.nnodes,
            max_nodes=args.nnodes,
        )

        # Create the cluster (this times it)
        try:
            cli.create_cluster()
        # What other cases might be here?
        except:
            print("🥵️ Issue creating GKE cluster, assuming already exists.")

        # Create a client from it
        print(f"📦️ The cluster has {cli.node_count} nodes!")
        kubectl = cli.get_k8s_client()

        # Let's assume there could be bugs applying this differently
        crd_api = kubernetes_client.CustomObjectsApi(kubectl.api_client)

    elif args.local:
        kubectl = get_local_kubectl()

    else:
        sys.exit(
            "Either --project (GCP) or --local (local kind or MiniKube) must be specified."
        )

    # Install the operator!
    try:
        k8sutils.create_from_yaml(kubectl.api_client, args.flux_operator_yaml)
        print("Installed the operator.")
    except Exception as exc:
        print(f"Issue installing the operator: {exc}, assuming already exists")

    # Do we need to cleanup the file?
    if cleanup and os.path.exists(args.flux_operator_yaml):
        os.remove(args.flux_operator_yaml)

    # Create the namespace
    try:
        kubectl.create_namespace(
            kubernetes_client.V1Namespace(
                metadata=kubernetes_client.V1ObjectMeta(name=args.namespace)
            )
        )
    except:
        print(f"🥵️ Issue creating namespace {args.namespace}, assuming already exists.")

    # Assemble the command from the requested job
    print(f"Command is {args.command}")
    minicluster, container = get_minicluster(
        args.command,
        name=args.name,
        memory_limit=args.memory_limit,
        cpu_limit=args.cpu_limit,
        namespace=args.namespace,
        tasks=args.ntasks,
        size=args.nnodes,
        image=args.image,
        wrap=args.wrap,
        log_level=args.log_level,
        flux_user=args.flux_user,
        zeromq=args.zeromq,
        quiet=args.quiet,
        strict=args.strict,
    )

    # Create a handle for controlling the FluxOperator
    operator = FluxMiniCluster(core_v1_api=kubectl)
    # operator.ctrl.core_v1
    # <kubernetes.client.api.core_v1_api.CoreV1Api at 0x7f9efa5e3370>

    # Create the MiniCluster! This also waits for it to be ready
    print(f"⭐️ Creating the minicluster {args.name} in {args.namespace}...")
    operator.create(**minicluster, container=container, crd_api=crd_api)

    # Wait until broker is completed, stream output will finish
    # Note this also returns the lines
    operator.stream_output(args.outfile or "/dev/null")

    # Delete the MiniCluster when we have the logs (and written to file)
    operator.delete()

    # Eventually to clean up...
    if not args.local:
        print("🧿️ Destroying Kubernetes Cluster, we are done!")
        cli.delete_cluster()


if __name__ == "__main__":
    main()
