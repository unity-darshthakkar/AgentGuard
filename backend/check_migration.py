from sqlalchemy import create_engine, inspect, text
engine = create_engine('sqlite:///agentguard.db')
inspector = inspect(engine)

# Check alembic version
with engine.connect() as conn:
    result = conn.execute(text('SELECT * FROM alembic_version'))
    print('Alembic version:', result.fetchall())

# Check indexes on authorization_decisions
indexes = inspector.get_indexes('authorization_decisions')
print('\nIndexes on authorization_decisions:')
for idx in indexes:
    print(f'  {idx["name"]}: {idx["column_names"]} (unique={idx["unique"]})')