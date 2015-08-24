# Use semantic versioning
__version__ = "2.0.0"

# Hack!
# dbmodels depends on this variable, it MUST be set correctly before dbmodels is
# loaded. This is likely to be fragile given recursive module imports...
DB_SCHEMA = "jscert"
