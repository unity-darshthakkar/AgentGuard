from sqlalchemy import create_engine, inspect
engine = create_engine('sqlite:///agentguard.db')
inspector = inspect(engine)
tables = inspector.get_table_names()
print('Tables:', tables)
for t in tables:
    cols = inspector.get_columns(t)
    print(f'{t}:')
    for c in cols:
        print(f'  {c["name"]} {c["type"]}')