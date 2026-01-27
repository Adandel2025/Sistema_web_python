from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
import re
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "mi_clave_secreta"

# Conexión a la base de datos
db = pymysql.connect(
    host="localhost",
    user="root",
    password="",
    database="sistema_web_poo",
    cursorclass=pymysql.cursors.DictCursor
)

# Función para validar correo
def validar_correo(correo):
    patron = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(patron, correo)

# ----------------------
# LOGIN (estudiante)
# ----------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nombre = request.form['nombre']
        correo = request.form['correo']

        if not validar_correo(correo):
            flash("Correo inválido. Por favor ingresa un correo real.")
            return render_template("login.html")

        cursor = db.cursor()
        cursor.execute("SELECT * FROM estudiantes WHERE correo=%s", (correo,))
        estudiante = cursor.fetchone()

        if not estudiante:
            cursor.execute("INSERT INTO estudiantes (nombre, correo) VALUES (%s, %s)", (nombre, correo))
            db.commit()
            estudiante_id = cursor.lastrowid
        else:
            estudiante_id = estudiante['id']

        session['estudiante_id'] = estudiante_id
        session['estudiante_nombre'] = nombre

        return redirect(url_for('panel'))

    return render_template("login.html")

# ----------------------
# PANEL PRINCIPAL (estudiante)
# ----------------------
@app.route('/panel')
def panel():
    if 'estudiante_id' not in session:
        return redirect(url_for('login'))

    estudiante_id = session['estudiante_id']
    cursor = db.cursor()

    cursor.execute("SELECT * FROM modulos ORDER BY id")
    modulos = cursor.fetchall()

    cursor.execute("SELECT * FROM resultados_examen WHERE estudiante_id=%s", (estudiante_id,))
    examenes_resultados = cursor.fetchall()
    examenes_dict = {r['modulo_id']: r for r in examenes_resultados}

    cursor.execute("SELECT * FROM modulos_estudiante WHERE estudiante_id=%s", (estudiante_id,))
    mod_estudiantes = cursor.fetchall()
    progreso_dict = {m['modulo_id']: m['progreso'] for m in mod_estudiantes}

    modulos_progreso = []
    for i, modulo in enumerate(modulos):
        desbloqueado = False
        if i == 0:
            desbloqueado = True
        else:
            anterior_id = modulos[i-1]['id']
            if anterior_id in examenes_dict and examenes_dict[anterior_id]['porcentaje'] >= 70:
                desbloqueado = True
        modulo['desbloqueado'] = desbloqueado
        modulo['progreso'] = progreso_dict.get(modulo['id'], 0)
        modulos_progreso.append(modulo)

    return render_template('panel.html', modulos=modulos_progreso)

# ----------------------
# VER MÓDULO
# ----------------------
@app.route('/modulo/<int:modulo_id>')
def ver_modulo(modulo_id):
    if 'estudiante_id' not in session:
        return redirect(url_for('login'))

    estudiante_id = session['estudiante_id']
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM modulos WHERE id=%s", (modulo_id,))
    modulo = cursor.fetchone()

    cursor.execute("SELECT * FROM lecciones WHERE modulo_id=%s ORDER BY orden", (modulo_id,))
    lecciones = cursor.fetchall()

    for leccion in lecciones:
        cursor.execute("SELECT * FROM ejercicios WHERE leccion_id=%s", (leccion['id'],))
        leccion['ejercicios'] = cursor.fetchall()

    cursor.execute("SELECT * FROM examen_final WHERE modulo_id=%s", (modulo_id,))
    examen = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM resultados_examen WHERE estudiante_id=%s AND modulo_id=%s",
        (estudiante_id, modulo_id)
    )
    examen_resultado = cursor.fetchone()
    porcentaje = None
    permitir_reintento = False
    if examen_resultado:
        porcentaje = examen_resultado['porcentaje']
        if porcentaje < 70:
            permitir_reintento = True

    return render_template('modulo.html', modulo=modulo, lecciones=lecciones, examen=examen,
                           porcentaje=porcentaje, permitir_reintento=permitir_reintento)

# ----------------------
# MARCAR EJERCICIO COMO CORRECTO
# ----------------------
@app.route('/marcar_como_correcto', methods=['POST'])
def marcar_como_correcto():
    if 'estudiante_id' not in session:
        return redirect(url_for('login'))

    estudiante_id = session['estudiante_id']
    ejercicio_id = request.form.get('ejercicio_id')
    modulo_id = int(request.form.get('modulo_id'))

    if not ejercicio_id or not modulo_id:
        flash("No se pudo procesar el ejercicio. Datos incompletos.")
        return redirect(url_for('panel'))

    cursor = db.cursor()

    cursor.execute(
        "SELECT * FROM resultados WHERE estudiante_id=%s AND ejercicio_id=%s",
        (estudiante_id, ejercicio_id)
    )
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO resultados (estudiante_id, ejercicio_id, estado) VALUES (%s, %s, 'Correcto')",
            (estudiante_id, ejercicio_id)
        )
        db.commit()

    cursor.execute(
        "SELECT COUNT(*) AS total FROM ejercicios WHERE leccion_id IN (SELECT id FROM lecciones WHERE modulo_id=%s)",
        (modulo_id,)
    )
    total_ejercicios = cursor.fetchone()['total']

    cursor.execute(
        "SELECT COUNT(*) AS completados FROM resultados WHERE estudiante_id=%s AND ejercicio_id IN (SELECT id FROM ejercicios WHERE leccion_id IN (SELECT id FROM lecciones WHERE modulo_id=%s))",
        (estudiante_id, modulo_id)
    )
    completados = cursor.fetchone()['completados']

    cursor.execute(
        "SELECT porcentaje FROM resultados_examen WHERE estudiante_id=%s AND modulo_id=%s",
        (estudiante_id, modulo_id)
    )
    examen = cursor.fetchone()
    porcentaje_examen = examen['porcentaje'] if examen else 0

    porcentaje_final = (((completados / total_ejercicios) * 100) if total_ejercicios else 0 + porcentaje_examen) / 2

    cursor.execute(
        "SELECT * FROM modulos_estudiante WHERE estudiante_id=%s AND modulo_id=%s",
        (estudiante_id, modulo_id)
    )
    mod_estudiante = cursor.fetchone()
    if mod_estudiante:
        cursor.execute(
            "UPDATE modulos_estudiante SET progreso=%s WHERE estudiante_id=%s AND modulo_id=%s",
            (porcentaje_final, estudiante_id, modulo_id)
        )
    else:
        cursor.execute(
            "INSERT INTO modulos_estudiante (estudiante_id, modulo_id, progreso) VALUES (%s, %s, %s)",
            (estudiante_id, modulo_id, porcentaje_final)
        )
    db.commit()

    flash("Ejercicio marcado como completado.")
    return redirect(url_for('panel'))

# ----------------------
# RESOLVER EXAMEN
# ----------------------
@app.route('/resolver_examen', methods=['POST'])
def resolver_examen():
    if 'estudiante_id' not in session:
        return redirect(url_for('login'))

    estudiante_id = session['estudiante_id']
    modulo_id = int(request.form.get('modulo_id'))
    cursor = db.cursor()

    cursor.execute("SELECT * FROM examen_final WHERE modulo_id=%s", (modulo_id,))
    preguntas = cursor.fetchall()

    correctas = 0
    for pregunta in preguntas:
        respuesta = request.form.get(f"pregunta_{pregunta['id']}")
        if respuesta and int(respuesta) == pregunta['correcta']:
            correctas += 1

    porcentaje = (correctas / len(preguntas)) * 100 if preguntas else 0

    cursor.execute(
        "SELECT * FROM resultados_examen WHERE estudiante_id=%s AND modulo_id=%s",
        (estudiante_id, modulo_id)
    )
    resultado_existente = cursor.fetchone()

    if resultado_existente:
        cursor.execute(
            "UPDATE resultados_examen SET correctas=%s, total=%s, porcentaje=%s WHERE estudiante_id=%s AND modulo_id=%s",
            (correctas, len(preguntas), porcentaje, estudiante_id, modulo_id)
        )
    else:
        cursor.execute(
            "INSERT INTO resultados_examen (estudiante_id, modulo_id, correctas, total, porcentaje) VALUES (%s, %s, %s, %s, %s)",
            (estudiante_id, modulo_id, correctas, len(preguntas), porcentaje)
        )
    db.commit()

    cursor.execute(
        "SELECT * FROM modulos_estudiante WHERE estudiante_id=%s AND modulo_id=%s",
        (estudiante_id, modulo_id)
    )
    mod_estudiante = cursor.fetchone()
    if mod_estudiante:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM ejercicios WHERE leccion_id IN (SELECT id FROM lecciones WHERE modulo_id=%s)",
            (modulo_id,)
        )
        total_ejercicios = cursor.fetchone()['total']

        cursor.execute(
            "SELECT COUNT(*) AS completados FROM resultados WHERE estudiante_id=%s AND ejercicio_id IN (SELECT id FROM ejercicios WHERE leccion_id IN (SELECT id FROM lecciones WHERE modulo_id=%s))",
            (estudiante_id, modulo_id)
        )
        completados = cursor.fetchone()['completados']

        porcentaje_final = (((completados / total_ejercicios) * 100) if total_ejercicios else 0 + porcentaje) / 2

        cursor.execute(
            "UPDATE modulos_estudiante SET progreso=%s WHERE estudiante_id=%s AND modulo_id=%s",
            (porcentaje_final, estudiante_id, modulo_id)
        )
    else:
        cursor.execute(
            "INSERT INTO modulos_estudiante (estudiante_id, modulo_id, progreso) VALUES (%s, %s, %s)",
            (estudiante_id, modulo_id, porcentaje)
        )
    db.commit()

    flash(f"Examen completado. Respuestas correctas: {correctas} de {len(preguntas)} ({porcentaje:.2f}%)")
    return redirect(url_for('ver_modulo', modulo_id=modulo_id))

# ----------------------
# REINTENTAR EXAMEN
# ----------------------
@app.route('/reintentar_examen/<int:modulo_id>')
def reintentar_examen(modulo_id):
    if 'estudiante_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('ver_modulo', modulo_id=modulo_id))

# ----------------------
# IR AL SIGUIENTE MÓDULO
# ----------------------
@app.route('/siguiente_modulo/<int:modulo_id>')
def siguiente_modulo(modulo_id):
    if 'estudiante_id' not in session:
        return redirect(url_for('login'))

    estudiante_id = session['estudiante_id']
    cursor = db.cursor()

    cursor.execute(
        "SELECT * FROM resultados_examen WHERE estudiante_id=%s AND modulo_id=%s",
        (estudiante_id, modulo_id)
    )
    resultado = cursor.fetchone()

    if resultado and resultado['porcentaje'] >= 70:
        flash("¡Siguiente módulo desbloqueado!")
    else:
        flash("No has alcanzado el 70%, no puedes desbloquear el siguiente módulo aún.")

    return redirect(url_for('panel'))

# ----------------------
# ADMIN: LOGIN
# ----------------------
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('password')

        cursor = db.cursor()
        cursor.execute("SELECT * FROM admin WHERE usuario=%s", (usuario,))
        admin = cursor.fetchone()

        if admin:
            stored = admin.get('password') or ''
            valid = False

            try:
                if stored and check_password_hash(stored, password):
                    valid = True
            except Exception:
                valid = False

            if not valid and stored == password:
                valid = True

            if valid:
                session['admin_id'] = admin['id']
                session['admin_usuario'] = admin['usuario']
                return redirect(url_for('admin_panel'))

        return render_template("admin_login.html", error="Credenciales incorrectas")

    return render_template("admin_login.html")

# ----------------------
# ADMIN: PANEL
# ----------------------
@app.route('/admin/panel')
def admin_panel():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor()

    cursor.execute("""
        SELECT id, nombre, correo
        FROM estudiantes
        ORDER BY id
    """)
    estudiantes = cursor.fetchall()

    # CORREGIDO: obtener SOLO el módulo más reciente por estudiante
    cursor.execute("""
        SELECT estudiante_id, modulo_id, progreso
        FROM modulos_estudiante
        ORDER BY estudiante_id, modulo_id DESC
    """)
    examenes_raw = cursor.fetchall()

    examenes = {}
    for reg in examenes_raw:
        est_id = reg['estudiante_id']
        if est_id not in examenes:  
            examenes[est_id] = reg  # el primero es el más reciente

    examenes = list(examenes.values())

    return render_template(
        "admin_panel.html",
        estudiantes=estudiantes,
        examenes=examenes
    )

# ----------------------
# ADMIN: EDITAR ESTUDIANTE
# ----------------------
@app.route('/admin/editar/<int:estudiante_id>', methods=['GET', 'POST'])
def admin_editar(estudiante_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor()

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        correo = request.form.get('correo')

        if not nombre or not correo:
            flash("Nombre y correo son obligatorios.")
            return redirect(url_for('admin_editar', estudiante_id=estudiante_id))

        if not validar_correo(correo):
            flash("Correo inválido.")
            return redirect(url_for('admin_editar', estudiante_id=estudiante_id))

        cursor.execute(
            "UPDATE estudiantes SET nombre=%s, correo=%s WHERE id=%s",
            (nombre, correo, estudiante_id)
        )
        db.commit()
        flash("Estudiante actualizado.")
        return redirect(url_for('admin_panel'))

    cursor.execute("SELECT * FROM estudiantes WHERE id=%s", (estudiante_id,))
    estudiante = cursor.fetchone()

    if not estudiante:
        flash("Estudiante no encontrado.")
        return redirect(url_for('admin_panel'))

    return render_template("admin_edit.html", estudiante=estudiante)

# ----------------------
# ADMIN: ELIMINAR ESTUDIANTE
# ----------------------
@app.route('/admin/eliminar/<int:estudiante_id>', methods=['POST', 'GET'])
def admin_eliminar(estudiante_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    cursor = db.cursor()

    cursor.execute("DELETE FROM resultados WHERE estudiante_id=%s", (estudiante_id,))
    cursor.execute("DELETE FROM resultados_examen WHERE estudiante_id=%s", (estudiante_id,))
    cursor.execute("DELETE FROM modulos_estudiante WHERE estudiante_id=%s", (estudiante_id,))
    cursor.execute("DELETE FROM estudiantes WHERE id=%s", (estudiante_id,))
    db.commit()

    flash("Estudiante y datos relacionados eliminados.")
    return redirect(url_for('admin_panel'))

# ----------------------
# ADMIN: LOGOUT
# ----------------------
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_usuario', None)
    return redirect(url_for('admin_login'))

# ----------------------
# LOGOUT ESTUDIANTE
# ----------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ----------------------
# INICIO
# ----------------------
@app.route('/')
def inicio():
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
