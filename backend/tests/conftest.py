import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql://root@localhost:26257/oncall?sslmode=disable"
)
