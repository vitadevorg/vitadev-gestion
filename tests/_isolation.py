"""Importar antes que el backend en cada suite.

Sin una selección explícita en el entorno del proceso, las pruebas usan SQLite
temporal y nunca la base configurada en .env. NEXO_TEST_SUITE impide además que
PostgreSQL se conecte a un esquema que no sea desechable (vitadev_test_*).
"""

import os

os.environ.setdefault("VITADEV_DATABASE", "sqlite")
os.environ["NEXO_TEST_SUITE"] = "1"
