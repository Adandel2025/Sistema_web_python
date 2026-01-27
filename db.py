import pymysql

def get_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="",          # Pon tu contraseña si MySQL tiene
        database="sistema_web_poo"
    )
