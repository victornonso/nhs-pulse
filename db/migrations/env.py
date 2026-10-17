from alembic import context
from sqlalchemy import create_engine
from apps.api.settings import settings

config = context.config
if context.is_offline_mode():
    context.configure(url=settings.migration_database_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(settings.migration_database_url).connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
