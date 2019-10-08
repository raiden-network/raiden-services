#!/usr/bin/env bash
set -e
case `hostname` in
	services-stable)
		COMPOSE_FILE="docker-compose.yml"
		docker pull raidennetwork/raiden-services:stable
		;;
	services-dev)
		COMPOSE_FILE="docker-compose.yml -f docker-compose.latest.yml"
		docker pull raidennetwork/raiden-services:latest
		;;
esac
[ -z $COMPOSE_FILE ] && { echo "Running on unknown host"; exit 1; }
docker-compose down
docker-compose -f $COMPOSE_FILE up -d
