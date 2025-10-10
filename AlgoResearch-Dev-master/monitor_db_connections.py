import psycopg2

conn = psycopg2.connect(
    dbname="dai7b9a9g995d2",
    user="uf3h3jdojd912u",
    password="pcf48a532b8aa15575beb0200cbe20cbb441d17ab436ef19445957ccfde292e42",
    host="c5hilnj7pn10vb.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com",
    port="5432"
)
cur = conn.cursor()

# Check active connections
cur.execute("""
    SELECT pid, usename, client_addr, application_name, state, backend_start
    FROM pg_stat_activity
    WHERE state = 'idle' AND usename = 'uf3h3jdojd912u';
""")
idle_connections = cur.fetchall()
print(f"Idle connections: {idle_connections}")

# Terminate idle connections
for conn in idle_connections:
    pid = conn[0]
    cur.execute(f"SELECT pg_terminate_backend({pid});")
    print(f"Terminated connection with pid: {pid}")

cur.close()
conn.close()