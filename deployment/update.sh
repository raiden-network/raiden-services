#!/usr/bin/env bash
docker-compose build
docker-compose down
docker-compose -f docker-compose.yml up -d
