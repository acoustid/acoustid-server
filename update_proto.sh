#!/usr/bin/env bash

set -eux

: ${GO_ACOUSTID_DIR:=../go-acoustid}

cd $(dirname $0)

for name in common/fingerprint.proto fpstore/fpstore.proto
do
    python -m grpc_tools.protoc \
        -I${GO_ACOUSTID_DIR}/proto \
        --python_out=acoustid/proto \
        --grpc_python_out=acoustid/proto \
        --mypy_out=acoustid/proto \
	--include_imports \
        ${name}
done

perl -pi -e 's{from (common|fpstore)\b}{from acoustid.proto.\1}' acoustid/proto/fpstore/*_pb2*.py*
