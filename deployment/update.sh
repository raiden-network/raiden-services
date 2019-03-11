#!/usr/bin/env bash
docker-compose build
docker-compose down
docker-compose up -d
