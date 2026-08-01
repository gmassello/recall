import os

TEST_ENV = {
    "DATABASE_URL": "postgresql://root@localhost:26257/oncall?sslmode=disable",
    "DEMO_API_KEY": "",
    "GEMINI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "BEDROCK_API_KEY": "",
    "AWS_ACCESS_KEY_ID": "",
    "AWS_SECRET_ACCESS_KEY": "",
    "AWS_SESSION_TOKEN": "",
    "COCKROACH_MCP_URL": "",
    "COCKROACH_MCP_API_KEY": "",
}

os.environ.update(TEST_ENV)
