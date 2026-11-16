#!/bin/bash
set -e
cd /home/rasp/pqfix2
export PATH=/home/rasp/pqfix2/go/bin:$PATH
[ -d go ] || tar -xzf go.tgz
go version

mkdir -p v1123 mainv
cp -f pqtest.go v1123/
cp -f pqtest.go mainv/

cd v1123
[ -f go.mod ] || go mod init pqtest
go get github.com/lib/pq@v1.12.3
go mod tidy
GOOS=linux GOARCH=arm64 go build -o /home/rasp/pqfix2/pqtest_v1123 .
cd ..

cd mainv
[ -f go.mod ] || go mod init pqtest
go get github.com/lib/pq@main
go mod tidy
GOOS=linux GOARCH=arm64 go build -o /home/rasp/pqfix2/pqtest_main .
cd ..

echo BUILD_DONE
ls -la pqtest_v1123 pqtest_main
grep -H "lib/pq" v1123/go.mod mainv/go.mod
