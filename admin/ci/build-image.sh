#!/bin/sh

set -ex

IMAGE=quay.io/acoustid/acoustid-server

if [ -n "$CI_COMMIT_TAG" ]
then
  VERSION=$(echo "$CI_COMMIT_TAG" | sed 's/^v//')
  PREV_VERSION=master
  GIT_RELEASE=$CI_COMMIT_TAG
else
  VERSION=$CI_COMMIT_REF_SLUG
  PREV_VERSION=$CI_COMMIT_REF_SLUG
  GIT_RELEASE=$CI_COMMIT_SHORT_SHA
fi

echo "GIT_RELEASE = '$GIT_RELEASE'" > acoustid/_release.py

docker pull $IMAGE:$PREV_VERSION || true
docker build --cache-from=$IMAGE:$PREV_VERSION -t $IMAGE:$VERSION .
docker push $IMAGE:$VERSION

for name in api web import cron
do
    docker build -t $IMAGE:$VERSION-$name -f Dockerfile.$name --build-arg IMAGE=$IMAGE --build-arg VERSION=$VERSION .
    docker push $IMAGE:$VERSION-$name
done

if [ -n "$CI_COMMIT_TAG" ]
then
    docker tag $IMAGE:$VERSION $IMAGE:latest
    docker push $IMAGE:latest
fi
