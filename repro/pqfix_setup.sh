#!/bin/bash
set -e
cd /home/rasp/pqfix
export PATH=/home/rasp/pqfix/go/bin:$PATH
[ -d go ] || tar -xzf go.tgz
go version

mkdir -p client1123 clientmain
cp -f main.go client1123/main.go
cp -f main.go clientmain/main.go

cd client1123
[ -f go.mod ] || go mod init pqdemo
go get github.com/lib/pq@v1.12.3
go mod tidy
GOOS=linux GOARCH=arm GOARM=7 go build -o client1123_arm .
cd ..

cd clientmain
[ -f go.mod ] || go mod init pqdemo
go get github.com/lib/pq@main
go mod tidy
GOOS=linux GOARCH=arm GOARM=7 go build -o clientmain_arm .
GOOS=linux GOARCH=arm64 go build -o clientmain_arm64 .
cd ..

echo BUILD_DONE
ls -la client1123_arm clientmain_arm clientmain_arm64
grep -E "lib/pq" client1123/go.mod clientmain/go.mod
