# Flux Operator Component

We will be following the [guide here](https://www.kubeflow.org/docs/components/pipelines/v1/sdk/component-development/)
to create a custom component for Kubeflow to "burst" off a job (a Flux MiniCluster)
from a KubeFlow pipeline. This isn't traditional bursting as we've imagined with Flux
(extending a running cluster) but rather creating a scoped job to handle one specific
task in a workflow (and then go away).

## Setup

Create your environment with the Kubeflow Pipelines sdk:

```bash
python -m venv env
source env/bin/activate
pip install kfp --upgrade
```

**under development**

## Development

### Local

The basis of this component is to launch a job to a cluster, and then
monitor it until it finishes, and get output to return. Since local development
typically means we have a cluster already running (e.g., kind) we can
test this out with an argument to indicate existing. In this case, you don't need to
build the container, but you will need the dependencies installed locally:

```bash
pip install -r requirements.txt
```

Then, create a local kind cluster. 

```bash
kind create cluster
```

At this point we can emulate (manually) submitting a workflow, running the job, monitoring it, and then cleaning up.
We will tell the script that the cluster already exists and is local (meaning the kubectl will hit it!)

```bash
python ./src/deploy.py --local --image ghcr.io/flux-framework/flux-restful-api:latest \
       --command "echo hello world" \
       --nnodes 4 \
       --ntasks 4 \
       --outfile hello-world.out \
       --quiet
```

You'll see the Flux Operator install, create the MiniCluster, wait and see the pods running, and get the output!

```bash
⭐️ Creating the minicluster flux-sample in flux-operator...
flux-sample-0-fjb9p is in phase Pending
flux-sample-1-g2sjv is in phase Pending
flux-sample-2-tmb45 is in phase Pending
flux-sample-0-fjb9p is in phase Running
flux-sample-1-g2sjv is in phase Running
flux-sample-2-tmb45 is in phase Running
flux-sample-3-zgsv6 is in phase Running
All pods are in states "Running" or "Succeeded" or "Completed"
hello world
hello world
hello world
hello world
All pods are terminated.
```

The output will be saved to the output file you specified:

```bash
$ cat hello-world.out 
hello world
hello world
hello world
hello world
```

When you are done, you can delete the cluster:

```bash
$ kind delete cluster
```

### Google Cloud 

Now we can try doing the same, but via Google Cloud! This will emulate already running from
a container (in KubeFlow) and create the Google Cloud one. 

```bash
GOOGLE_PROJECT=llnl-flux
python ./src/deploy.py --project ${GOOGLE_PROJECT} --image ghcr.io/flux-framework/flux-restful-api:latest \
       --command "echo hello world" \
       --nnodes 4 \
       --ntasks 4 \
       --outfile hello-world.out \
       --quiet
```

You'll see a similar interaction - running the jobs, getting output, but (since we are bursting to Google Cloud)
you'll create the cluster beforehand, and destroy it after!

```console
Command is echo hello world
⭐️ Creating the minicluster flux-sample in flux-operator...
flux-sample-0-htkh7 is in phase Pending
flux-sample-0-htkh7 is in phase Pending
flux-sample-1-wwzj7 is in phase Running
flux-sample-2-gkhrq is in phase Running
flux-sample-3-nf2vl is in phase Pending
flux-sample-0-htkh7 is in phase Running
flux-sample-1-wwzj7 is in phase Running
flux-sample-2-gkhrq is in phase Running
flux-sample-3-nf2vl is in phase Running
All pods are in states "Running" or "Succeeded" or "Completed"
hello world
hello world
hello world
hello world
All pods are terminated.
🧿️ Destroying Kubernetes Cluster, we are done!
```

### KubeFlow on GKE

Now let's test fully in KubeFlow! First, build the container:

```bash
$ docker build -t ghcr.io/converged-computing/flux-operator-component .
```

**under development**

## License

HPCIC DevTools is distributed under the terms of the MIT license.
All new contributions must be made under this license.

See [LICENSE](https://github.com/converged-computing/cloud-select/blob/main/LICENSE),
[COPYRIGHT](https://github.com/converged-computing/cloud-select/blob/main/COPYRIGHT), and
[NOTICE](https://github.com/converged-computing/cloud-select/blob/main/NOTICE) for details.

SPDX-License-Identifier: (MIT)

LLNL-CODE- 842614
