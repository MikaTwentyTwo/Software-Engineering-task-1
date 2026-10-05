-- Separate database and least-privilege login per service; passwords share one local-only secret.
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', name, :'password')
FROM (VALUES ('users'), ('rooms'), ('equipment'), ('bookings'), ('notifications')) AS services(name) \gexec
SELECT format('CREATE DATABASE %I OWNER %I', name, name)
FROM (VALUES ('users'), ('rooms'), ('equipment'), ('bookings'), ('notifications')) AS services(name) \gexec
