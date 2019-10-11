#!/usr/bin/env bash
# Called manually to update all services
# Called from builder as `update.sh UPDATED_TAG` to update only when the relevant tag is passed
# Builder and traefik are not restarted to allow the builder to properly finish the update and respond
set -e
case $HOSTNAME in
	services-stable)
		COMPOSE_FILE="docker-compose.yml"
                TAG=stable
		;;
	services-dev)
		COMPOSE_FILE="docker-compose.yml -f docker-compose.latest.yml"
                TAG=latest
		;;
esac
[ -n "$COMPOSE_FILE" ] || { echo "Running on unknown host"; exit 1; }

UPDATED_TAG=$1
[ -n "$UPDATED_TAG" ] || UPDATED_TAG=$TAG
[ $UPDATED_TAG = $TAG ] || { echo "Only listening on tag $TAG"; exit 0; }

docker-compose -f $COMPOSE_FILE pull
SERVICES=`docker-compose config --services | grep -v traefik | grep -v builder | xargs`  # exclude builder and traefik from restart
docker-compose -f $COMPOSE_FILE up --no-deps -d $SERVICES
