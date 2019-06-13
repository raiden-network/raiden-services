FROM python:3.7

LABEL Name=pathfinding-service-dev Version=0.0.1 Author="Paul Lange"
EXPOSE 6000

# add user and group
RUN set -eux; \
    groupadd -g 999 services; \
    useradd -m -u 999 -g services -s /bin/bash services

WORKDIR /services
ADD . /services

USER services

RUN python3 -m pip install -r requirements.txt
RUN python3 -m pip install -e .
