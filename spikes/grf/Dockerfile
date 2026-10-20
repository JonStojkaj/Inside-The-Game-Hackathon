# Google Research Football with build fixes (gym 0.21 needs old setuptools/wheel).
# Build from spikes/grf:  docker build --platform linux/amd64 -t gfootball:spike -f Dockerfile vendor
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get --no-install-recommends install -yq git cmake build-essential \
  libgl1-mesa-dev libsdl2-dev \
  libsdl2-image-dev libsdl2-ttf-dev libsdl2-gfx-dev libboost-all-dev \
  libdirectfb-dev libst-dev mesa-utils xvfb x11vnc \
  python3-pip python3-dev

RUN python3 -m pip install --retries 10 "pip<24.1" "setuptools==65.5.0" "wheel==0.38.4" \
 && python3 -m pip install --retries 10 psutil six "numpy<1.25" \
 && python3 -m pip install --retries 10 --no-build-isolation "gym==0.21.0"

COPY . /gfootball
RUN cd /gfootball && python3 -m pip install --retries 10 --no-build-isolation .
WORKDIR /gfootball
