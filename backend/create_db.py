#!/usr/bin/env python3
"""Create ai_agent_platform database if it doesn't exist."""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Connect to default 'postgres' database to create our DB
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="luisaaronjimenez",
    password="",  # Add password if your local Postgres requires it
    dbname="postgres"
)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

cur = conn.cursor()
try:
    cur.execute("CREATE DATABASE ai_agent_platform;")
    print("Database 'ai_agent_platform' created successfully.")
except psycopg2.errors.DuplicateDatabase:
    print("Database 'ai_agent_platform' already exists.")
cur.close()
conn.close()
