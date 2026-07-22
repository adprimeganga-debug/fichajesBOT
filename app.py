from flask import Flask, request, redirect, url_for
import sqlite3
from datetime import datetime, date, timedelta
import qrcode
import os

DB_PATH = "fichajes.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            activo INTEGER NOT NULL DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS fichajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            fecha_hora TEXT NOT NULL,
            FOREIGN KEY (empleado_id) REFERENCES empleados(id)
        )
    """)

    conn.commit()
    conn.close()

init_db()
app = Flask(__name__)

DB_PATH = "fichajes.db"
HORAS_DIA = 9
HORAS_SEMANA = 54

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ---------- HOME / ADMIN ----------

@app.route("/")
def index():
    return """
    <h1>Panel de fichaje</h1>
    <ul>
        <li><a href='/admin/empleados'>Empleados</a></li>
        <li><a href='/admin/fichajes'>Fichajes</a></li>
        <li><a href='/admin/horas'>Horas diarias</a></li>
        <li><a href='/admin/horas_semanales'>Horas semanales</a></li>
    </ul>
    """

# ---------- EMPLEADOS ----------

@app.route("/admin/empleados", methods=["GET", "POST"])
def empleados():
    conn = db()
    c = conn.cursor()

    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        if nombre:
            try:
                c.execute("INSERT INTO empleados (nombre, activo) VALUES (?, 1)", (nombre,))
                conn.commit()
            except sqlite3.IntegrityError:
                pass

    c.execute("SELECT * FROM empleados ORDER BY nombre")
    lista = c.fetchall()
    conn.close()

    html = "<h2>Empleados</h2>"
    html += "<form method='POST'>Nombre: <input name='nombre'><button>Añadir</button></form>"
    html += "<ul>"
    for emp in lista:
        html += f"<li>{emp['nombre']} "
        html += f"<a href='/admin/generar_qr/{emp['id']}'>QR</a> | "
        html += f"<a href='/admin/eliminar/{emp['id']}'>Eliminar</a></li>"
    html += "</ul>"
    html += "<a href='/'>Volver</a>"
    return html

@app.route("/admin/eliminar/<int:id>")
def eliminar_empleado(id):
    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM empleados WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("empleados"))

# ---------- GENERAR QR ----------

@app.route("/admin/generar_qr/<int:id>")
def generar_qr(id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT nombre FROM empleados WHERE id=?", (id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return "Empleado no encontrado"

    nombre = row["nombre"]
    url = f"http://localhost:5000/fichar?user={nombre}"

    if not os.path.exists("static"):
        os.makedirs("static")

    filename = f"qr_{nombre}.png"
    path = os.path.join("static", filename)
    img = qrcode.make(url)
    img.save(path)

    return f"""
    <h2>QR de {nombre}</h2>
    <p>Usa este QR para fichar:</p>
    <img src='/static/{filename}'><br>
    <a href='/admin/empleados'>Volver</a>
    """

# ---------- FICHAR ----------

@app.route("/fichar", methods=["GET", "POST"])
def fichar():
    empleado_nombre = request.args.get("user")
    if not empleado_nombre:
        return "Falta parámetro user"

    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM empleados WHERE nombre=?", (empleado_nombre,))
    emp = c.fetchone()

    if not emp:
        conn.close()
        return "Empleado no encontrado"

    empleado_id = emp["id"]

    if request.method == "POST":
        tipo = request.form["tipo"]
        fecha_hora = datetime.now().isoformat(timespec="seconds")

        c.execute(
            "INSERT INTO fichajes (empleado_id, tipo, fecha_hora) VALUES (?, ?, ?)",
            (empleado_id, tipo, fecha_hora),
        )
        conn.commit()
        conn.close()
        return f"Fichaje {tipo} registrado para {empleado_nombre}"

    conn.close()
    return f"""
    <h2>Fichaje de {empleado_nombre}</h2>
    <form method="POST">
        <button name="tipo" value="entrada">Entrar</button>
        <button name="tipo" value="salida">Salir</button>
    </form>
    """

# ---------- LISTA FICHAJES ----------

@app.route("/admin/fichajes")
def ver_fichajes():
    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT f.id, e.nombre, f.tipo, f.fecha_hora
        FROM fichajes f
        JOIN empleados e ON f.empleado_id = e.id
        ORDER BY f.fecha_hora DESC
    """)
    filas = c.fetchall()
    conn.close()

    html = "<h2>Fichajes</h2><table border='1'><tr><th>ID</th><th>Empleado</th><th>Tipo</th><th>Fecha/hora</th></tr>"
    for f in filas:
        html += f"<tr><td>{f['id']}</td><td>{f['nombre']}</td><td>{f['tipo']}</td><td>{f['fecha_hora']}</td></tr>"
    html += "</table><a href='/'>Volver</a>"
    return html

# ---------- CÁLCULO DIARIO ----------

def calcular_dia(empleado_id, fecha_str):
    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT tipo, fecha_hora
        FROM fichajes
        WHERE empleado_id=? AND date(fecha_hora)=?
        ORDER BY fecha_hora
    """, (empleado_id, fecha_str))
    registros = c.fetchall()
    conn.close()

    entrada = None
    salida = None

    for r in registros:
        fh = datetime.fromisoformat(r["fecha_hora"])
        if r["tipo"] == "entrada":
            entrada = fh
        elif r["tipo"] == "salida":
            salida = fh

    if not entrada or not salida:
        return None

    horas = (salida - entrada).total_seconds() / 3600.0
    extra = max(0, horas - HORAS_DIA)
    debe = max(0, HORAS_DIA - horas)

    return {
        "fecha": fecha_str,
        "horas_trabajadas": round(horas, 2),
        "horas_extra": round(extra, 2),
        "horas_debe": round(debe, 2),
    }

@app.route("/admin/horas")
def horas_diarias():
    hoy = date.today().isoformat()

    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM empleados ORDER BY nombre")
    empleados = c.fetchall()
    conn.close()

    html = f"<h2>Horas diarias (hoy {hoy})</h2><table border='1'><tr><th>Empleado</th><th>Horas</th><th>Extra</th><th>Debe</th></tr>"

    for emp in empleados:
        res = calcular_dia(emp["id"], hoy)
        if res:
            html += f"<tr><td>{emp['nombre']}</td><td>{res['horas_trabajadas']}</td><td>{res['horas_extra']}</td><td>{res['horas_debe']}</td></tr>"
        else:
            html += f"<tr><td>{emp['nombre']}</td><td colspan='3'>Sin datos completos</td></tr>"

    html += "</table><a href='/'>Volver</a>"
    return html

# ---------- CÁLCULO SEMANAL ----------

def rango_semana(fecha_base=None):
    if fecha_base is None:
        fecha_base = date.today()
    # asumimos semana lunes-sábado
    lunes = fecha_base - timedelta(days=fecha_base.weekday())
    dias = [lunes + timedelta(days=i) for i in range(6)]
    return dias

@app.route("/admin/horas_semanales")
def horas_semanales():
    dias = rango_semana()
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM empleados ORDER BY nombre")
    empleados = c.fetchall()
    conn.close()

    html = "<h2>Horas semanales</h2>"
    html += "<p>Semana: " + ", ".join(d.isoformat() for d in dias) + "</p>"
    html += "<table border='1'><tr><th>Empleado</th><th>Total semana</th><th>Extra</th><th>Debe</th></tr>"

    for emp in empleados:
        total = 0.0
        for d in dias:
            res = calcular_dia(emp["id"], d.isoformat())
            if res:
                total += res["horas_trabajadas"]

        extra = max(0, total - HORAS_SEMANA)
        debe = max(0, HORAS_SEMANA - total)

        html += f"<tr><td>{emp['nombre']}</td><td>{round(total,2)}</td><td>{round(extra,2)}</td><td>{round(debe,2)}</td></tr>"

    html += "</table><a href='/'>Volver</a>"
    return html

# ---------- MAIN ----------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)