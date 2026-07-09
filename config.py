import os

MYSQL_HOST = os.getenv("MYSQLHOST", "localhost")
MYSQL_USER = os.getenv("MYSQLUSER", "root")
MYSQL_PASSWORD = os.getenv("MYSQLPASSWORD", "1234")
MYSQL_DB = os.getenv("MYSQLDATABASE", "zp_inventory")