import re
import MySQLdb


def backend_for(values):
    connection = MySQLdb.connect(host=values.get('DB_HOST', '127.0.0.1'),
        port=int(values.get('DB_PORT', '3306')), user=values.get('MYSQL_USER', 'autoparts'),
        passwd=values.get('MYSQL_PASSWORD', ''), db=values.get('MYSQL_DATABASE', 'autoparts'),
        charset='utf8mb4', connect_timeout=5)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT VERSION()')
            version = cursor.fetchone()[0]
    finally:
        connection.close()
    match = re.match(r'(\d+)\.(\d+)', version)
    if not match or 'mariadb' in version.lower():
        raise ValueError('Supported databases: MySQL 5.7 or MySQL 8.x.')
    major, minor = map(int, match.groups())
    if major == 5 and minor == 7:
        return 'mysql57', version
    if major >= 8:
        return ('mysql57' if values.get('AUTOPARTS_BACKEND') == 'mysql57' else 'django'), version
    raise ValueError('Supported databases: MySQL 5.7 or MySQL 8.x.')
