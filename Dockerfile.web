ARG IMAGE=quay.io/acoustid/acoustid-server
ARG VERSION=master
FROM ${IMAGE}:${VERSION}

EXPOSE 3032

HEALTHCHECK --start-period=10s \
  CMD curl -qf http://localhost:3032/_health_docker || exit 1

CMD ["/opt/acoustid/server/admin/docker/run-web.sh"]
