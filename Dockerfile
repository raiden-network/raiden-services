FROM python:3.7

LABEL Name=raiden-services Version=0.2.0 Author="Raiden Services Team"
EXPOSE 6000

WORKDIR /services
ADD . /services

RUN python3 -m pip install -r requirements.txt
RUN python3 -m pip install -e .
