package main

// pqtest: exercises github.com/lib/pq against a hostile server.
//   pqtest ping  <port> <password>   - open connection + Ping (startup path)
//   pqtest query <port> <password>   - Query + rows.Next (decode path)
// A panic in the driver (no recover in pq or database/sql) kills the process:
// exit 2 with a Go panic stack = vulnerability triggered.
// A handled protocol error prints "ping:/query:" and exits 0 = not vulnerable.
import (
	"database/sql"
	"fmt"
	"os"

	_ "github.com/lib/pq"
)

func main() {
	mode, port, pass := "ping", "5433", "Secret123"
	if len(os.Args) > 1 {
		mode = os.Args[1]
	}
	if len(os.Args) > 2 {
		port = os.Args[2]
	}
	if len(os.Args) > 3 {
		pass = os.Args[3]
	}
	dsn := fmt.Sprintf("host=127.0.0.1 port=%s user=postgres dbname=postgres sslmode=disable connect_timeout=8 password=%s", port, pass)
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		fmt.Println("open:", err)
		os.Exit(0)
	}
	defer db.Close()
	db.SetMaxOpenConns(1)

	if mode == "ping" {
		if err := db.Ping(); err != nil {
			fmt.Println("ping:", err)
			os.Exit(0)
		}
		fmt.Println("PING_OK")
		return
	}

	rows, err := db.Query("select b")
	if err != nil {
		fmt.Println("query:", err)
		os.Exit(0)
	}
	defer rows.Close()
	if rows.Next() {
		var v any
		if err := rows.Scan(&v); err != nil {
			fmt.Println("scan:", err)
		} else {
			fmt.Println("row:", v)
		}
	}
	fmt.Println("QUERY_DONE")
}
