from flask import Flask, request, redirect, url_for
import sqlite3
from datetime import datetime, date
import qrcode
import os
import pytz

app = Flask(__name__)

# BASE DE DATOS PERSISTENTE EN RENDER
DB_PATH = "/var/fichajes.db"

HORAS_DIA = 9  # jornada diaria
TZ = pytz.timezone("Europe/Madrid")

# ---------- DB ----------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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

# ---------- HOME / ADMIN ----------

@app.route("/")
def index():
    return """
    <h1>Panel de fichaje</h1>
    <ul>
        <li><a href='/admin/empleados'>Empleados</a></li>
        <li><a href='/admin/fichajes'>Fichajes</a></li>
        <li><a href='/admin/horas'>Horas diarias</a></li>
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

    # URL del QR (Render)
    url = f"https://fichajesbot.onrender.com/fichar?user={nombre}"

    # Crear carpeta static si no existe
    if not os.path.exists("static"):
        os.makedirs("static")

    # Generar QR (solo imagen)
    qr_img = qrcode.make(url)
    filename = f"qr_{nombre}.png"
    path = os.path.join("static", filename)
    qr_img.save(path)

    return f"""
    <h2>QR de {nombre}</h2>
    <img src='/static/{filename}' style='width:300px'><br>
    <h3>{nombre}</h3>

    <button onclick="window.print()" 
            style="padding:10px 20px; font-size:18px;">
        Imprimir QR
    </button>

    <br><br>
    <a href='/admin/empleados'>Volver</a>
    """

# ---------- FICHAR AUTOMÁTICO ----------

@app.route("/fichar")
def fichar():
    empleado_nombre = request.args.get("user")
    if not empleado_nombre:
        return "Falta parámetro user"

    conn = db()
    c = conn.cursor()

    c.execute("SELECT id FROM empleados WHERE nombre=?", (empleado_nombre,))
    emp = c.fetchone()
    if not emp:
        conn.close()
        return "Empleado no encontrado"

    empleado_id = emp["id"]

    # Último fichaje
    c.execute("""
        SELECT tipo, fecha_hora 
        FROM fichajes 
        WHERE empleado_id=? 
        ORDER BY fecha_hora DESC 
        LIMIT 1
    """, (empleado_id,))
    ultimo = c.fetchone()

    if ultimo and ultimo["tipo"] == "entrada":
        tipo = "salida"
    else:
        tipo = "entrada"

    fecha_hora = datetime.now(TZ).astimezone(TZ).isoformat()

    c.execute(
        "INSERT INTO fichajes (empleado_id, tipo, fecha_hora) VALUES (?, ?, ?)",
        (empleado_id, tipo, fecha_hora)
    )
    conn.commit()
    conn.close()

    return f"""
    <h2>Fichaje automático realizado</h2>
    <p>Empleado: <b>{empleado_nombre}</b></p>
    <p>Acción: <b>{tipo.upper()}</b></p>
    <p>Hora: {fecha_hora}</p>
    <script>
        setTimeout(() => window.close(), 2000);
    </script>
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

# ---------- CÁLCULO DIARIO CON PAUSAS ----------

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
        fh = fh.astimezone(TZ)

        if r["tipo"] == "entrada":
            entrada = fh
        elif r["tipo"] == "salida":
            salida = fh

    if not entrada or not salida:
        return None

    # Pausas del día (comida y cena)
    dia = entrada.date()
    comida_ini = TZ.localize(datetime.combine(dia, datetime.strptime("12:30", "%H:%M").time()))
    comida_fin = TZ.localize(datetime.combine(dia, datetime.strptime("13:00", "%H:%M").time()))
    cena_ini = TZ.localize(datetime.combine(dia, datetime.strptime("19:00", "%H:%M").time()))
    cena_fin = TZ.localize(datetime.combine(dia, datetime.strptime("19:30", "%H:%M").time()))

    # Ajustar entrada si cae dentro de pausa
    if comida_ini <= entrada <= comida_fin:
        entrada = comida_fin
    if cena_ini <= entrada <= cena_fin:
        entrada = cena_fin

    # Ajustar salida si cae dentro de pausa
    if comida_ini <= salida <= comida_fin:
        salida = comida_ini
    if cena_ini <= salida <= cena_fin:
        salida = cena_ini

    # Calcular horas trabajadas
    horas = (salida - entrada).total_seconds() / 3600.0

    pausa_total = 0.0

    # Pausa comida dentro del rango trabajado
    if entrada < comida_ini and salida > comida_fin:
        pausa_total += 0.5  # 30 minutos

    # Pausa cena dentro del rango trabajado
    if entrada < cena_ini and salida > cena_fin:
        pausa_total += 0.5  # 30 minutos

    horas -= pausa_total

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

# ---------- MAIN ----------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
