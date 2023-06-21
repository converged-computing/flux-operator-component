ARG tag=latest
FROM ubuntu:${tag}

# docker build -t ghcr.io/converged-computing/flux-operator-component .

RUN apt-get update && apt-get install -y python3-pip
COPY ./requirements.txt /requirements.txt
RUN python3 -m pip install -r requirements.txt
COPY ./src /pipelines/component/src
ENTRYPOINT python3 /pipelines/component/src/deploy.py
