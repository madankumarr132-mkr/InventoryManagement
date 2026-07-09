import os

MYSQL_HOST = os.getenv("MYSQLHOST", "hayabusa.proxy.rlwy.net")
MYSQL_USER = os.getenv("MYSQLUSER", "root")
MYSQL_PASSWORD = os.getenv("MYSQLPASSWORD", "XFtTSfJqYCFHlZFyBxxyQmILFOzwTckI")
MYSQL_DB = os.getenv("MYSQLDATABASE", "railway")
MYSQL_PORT = int(os.getenv("MYSQLPORT", "51558"))