FROM python:3.9

LABEL Name=raiden-services Version=0.18.3 Maintainer="Raiden Network Team <contact@raiden.network>"
EXPOSE 6000

WORKDIR /services
ADD . /services

RUN python3 -m pip install -r requirements.txt
RUN python3 -m pip install -e .
