FROM ubuntu:noble
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get update
RUN apt-get upgrade -y

# Python

RUN apt-get remove -y python3.12
RUN apt-get install -y software-properties-common
RUN add-apt-repository ppa:deadsnakes/ppa -y
RUN apt-get update -y
RUN apt-get install -y python3.11
RUN python3 --version
RUN apt-get install -y python3-pip

# psutil used to refer to a process by its pid
RUN python3 -m pip install psutil --break-system-packages

# Install python packages (depdendencies for unified planning)

RUN python3 -m pip install pyparser --break-system-packages
RUN python3 -m pip install networkx --break-system-packages
RUN python3 -m pip install ConfigSpace --break-system-packages
RUN python3 -m pip install "numpy<2" --break-system-packages

RUN python3 -m pip install grpcio-tools --break-system-packages

# "Activate" development version of unified planning package
# (copy-pasted / adapted from `beluga/aries-beluga/planning/unified/dev.env`)

ENV DIR="/usr/src/beluga/aries-beluga/planning/unified"
# Allow using the `up_aries` plugin directly from this repository
ENV PYTHONPATH="${DIR}/plugin:"
# Enable automatic recompilation of the server
ENV UP_ARIES_DEV="true"
# Use the python modules of the unified planning library and test cases directly from the git submodules of this repository
ENV PYTHONPATH="${DIR}/deps/unified-planning/up_test_cases:${PYTHONPATH}"
ENV PYTHONPATH="${DIR}/deps/unified-planning:${PYTHONPATH}"

# Curl (needed to install Rust and Node.js)

RUN apt-get install -y curl

# Rust

RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
RUN cargo --version

# Copy beluga repository (w/ submodules)

RUN mkdir -p /usr/src/beluga
COPY . /usr/src/beluga/

# Build the approriate Rust executables

WORKDIR /usr/src/beluga/aries-beluga/
RUN cargo build --bin up-server --ci
RUN cargo build --bin beluga --release