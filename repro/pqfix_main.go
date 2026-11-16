package main

import (
	"database/sql"
	"fmt"
	"os"
	"strconv"
	"sync"

	_ "github.com/lib/pq"
)

// Opens N concurrent PostgreSQL connections to a hostile server and Pings each
// one, exactly like a scanner's credential test does. Any crash inside the pq
// driver (fatal error: out of memory) kills this whole process.
func main() {
	n := 100
	port := "5433"
	ct := "10"
	if len(os.Args) > 1 {
		n, _ = strconv.Atoi(os.Args[1])
	}
	if len(os.Args) > 2 {
		port = os.Args[2]
	}
	if len(os.Args) > 3 {
		ct = os.Args[3]
	}
	dsn := "host=127.0.0.1 port=" + port + " user=scan dbname=scan sslmode=disable connect_timeout=" + ct
	fmt.Printf("connecting %d times to %s\n", n, dsn)
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			db, err := sql.Open("postgres", dsn)
			if err != nil {
				fmt.Println(i, "open:", err)
				return
			}
			defer db.Close()
			db.SetMaxOpenConns(1)
			if err := db.Ping(); err != nil {
				fmt.Println(i, "ping:", err)
				return
			}
			fmt.Println(i, "ping: OK")
		}(i)
	}
	wg.Wait()
	fmt.Println("ALL_DONE")
}
