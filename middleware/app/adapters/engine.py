from middleware.app.adapters.db_adapter import DatabaseAdapter
# from middleware.app.adapters.api_adapter import ApiAdapter
# from middleware.app.adapters.file_adapter import FileAdapter

class AdapterEngine:
    @staticmethod
    def get_adapter(source_type: str, connection_config: dict):
        """
        Factory method to return the correct adapter instance based on the source type.
        """
        if source_type == "database":
            return DatabaseAdapter(connection_config)
        
        # We will add other adapters in the future
        # elif source_type == "api":
        #     return ApiAdapter(connection_config)
        # elif source_type == "file":
        #     return FileAdapter(connection_config)
        
        raise ValueError(f"Unsupported source type: {source_type}")

    @staticmethod
    def auto_detect_source_type(connection_info: dict) -> str:
        """
        Auto-detect the source type from generic connection info.
        For example, if it has 'postgres://' or 'mysql://', it's a database.
        """
        url = connection_info.get("url", "")
        if url.startswith(("postgres", "mysql", "sqlite", "mssql", "oracle")):
            return "database"
        elif url.startswith(("http", "https")):
            return "api"
        elif "file_path" in connection_info:
            return "file"
            
        return "unknown"
