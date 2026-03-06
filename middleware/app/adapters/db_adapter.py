from sqlalchemy import create_engine, MetaData, select, Table
import logging

logger = logging.getLogger(__name__)

class DatabaseAdapter:
    def __init__(self, connection_config: dict):
        self.url = connection_config.get("url")
        if not self.url:
            raise ValueError("Database connection URL is required")
        
        # We only ever read from external databases
        self.engine = create_engine(self.url)
        self.metadata = MetaData()
        
    def test_connection(self) -> bool:
        """Test if the credentials and URL work"""
        try:
            with self.engine.connect() as conn:
                return True
        except Exception as e:
            logger.error(f"Failed to connect to external DB: {e}")
            return False

    def get_schema_summary(self) -> dict:
        """
        Introspect the database and return tables and columns.
        This helps the LLM with AI-assisted mapping.
        """
        self.metadata.reflect(bind=self.engine)
        schema = {}
        for table_name, table in self.metadata.tables.items():
            columns = [{"name": col.name, "type": str(col.type)} for col in table.columns]
            schema[table_name] = columns
        return schema

    def execute_query(self, query_str: str, params: dict = None) -> list:
        """
        Execute a raw read-only query (used by dynamic mapping engine).
        Caution: Ensure queries are safe and read-only. We only use this internally.
        """
        try:
            # Simple text wrapper for raw queries
            from sqlalchemy import text
            with self.engine.connect() as conn:
                result = conn.execute(text(query_str), params or {})
                return [dict(row._mapping) for row in result]
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
