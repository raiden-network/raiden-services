FROM python:3.8
MAINTAINER Ulrich Petri <ulrich@brainbot.com>

ADD app /app

WORKDIR /app

RUN pip install -r requirements.txt

EXPOSE 5000

ENV FLASK_APP=main.py

ENTRYPOINT ["python", "-m", "flask", "run", "--host", "0.0.0.0"]
