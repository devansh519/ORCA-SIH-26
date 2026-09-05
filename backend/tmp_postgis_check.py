import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

root = Path(r'C:\Users\DEVANSH\Desktop\orca')
load_dotenv(root / '.env')
url = os.getenv('DATABASE_URL')
engine = create_engine(url, pool_pre_ping=True)
with engine.connect() as conn:
    queries = [
        "SELECT extname, extversion FROM pg_extension ORDER BY extname;",
        "SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name = 'postgis';",
        "SELECT current_user, current_database(), version();",
    ]
    for q in queries:
        print('QUERY:', q)
        try:
            rows = conn.execute(text(q)).fetchall()
            print(rows)
        except Exception as ex:
            print('ERR:' + type(ex).__name__ + ':' + str(ex))
