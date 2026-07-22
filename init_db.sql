DROP TABLE IF EXISTS empleados;
DROP TABLE IF EXISTS fichajes;

CREATE TABLE empleados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE fichajes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empleado_id INTEGER NOT NULL,
    tipo TEXT NOT NULL, -- 'entrada' o 'salida'
    fecha_hora TEXT NOT NULL,
    FOREIGN KEY (empleado_id) REFERENCES empleados(id)
);
