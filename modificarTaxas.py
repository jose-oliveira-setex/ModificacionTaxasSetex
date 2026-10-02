import tkinter as tk
from tkinter import messagebox
import mysql.connector
from datetime import datetime
import os
import getpass
import base64
import requests
from msal import ConfidentialClientApplication
import random

codigo_2fa = str(random.randint(100000, 999999))

# ==========================
# CONFIGURACION MYSQL
# ==========================

DB_HOST = "colocar ip aqui"
DB_USER = "usuario base de datos"
DB_PASSWORD = "contraseña base de datos"
DB_NAME = "nombre de la base de datos"

# ==========================
# CONFIGURACION Correos
# ==========================

TENANT_ID = "tenant id del correo empresarial"
CLIENT_ID = "client id del correo empresarial que enviara los correos"
CLIENT_SECRET = "clave secreta para poder enviar correos, esta en graphl"

BUZON = "no_reply@setex.es"

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

SCOPES = ["https://graph.microsoft.com/.default"]

GRAPH_URL = "https://graph.microsoft.com/v1.0"

USUARIOS = {
    "admin": "Taxas@2026"
}

# =====================================================
# OBTENER TOKEN
# =====================================================

def obtener_token():

    app = ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET
    )

    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )

    if "access_token" not in result:
        raise Exception(
            f"Error obteniendo token: {result}"
        )

    return result["access_token"]


# ==========================
# LOGS
# ==========================

def escribir_log(texto):

    os.makedirs("logs", exist_ok=True)

    fichero = os.path.join(
        "logs",
        datetime.now().strftime("%Y-%m-%d") + ".log"
    )

    with open(fichero, "a", encoding="utf-8") as f:
        f.write(texto)
        f.write("\n")


# ==========================
# VALIDACION
# ==========================

def validar_decimal(texto):

    if texto == "":
        return True

    permitidos = "0123456789,."

    return all(c in permitidos for c in texto)


def convertir_decimal(valor):

    valor = valor.strip()

    if not valor:
        raise ValueError(
            "Debe introducir un importe."
        )

    valor = valor.replace(",", ".")

    try:
        numero = float(valor)
    except:
        raise ValueError(
            "Solo se permiten números.\n\nEjemplos válidos:\n123\n123,45\n123.45"
        )

    if numero < 0:
        raise ValueError(
            "No se permiten importes negativos."
        )

    return round(numero, 2)


# ==========================
# MYSQL
# ==========================

def obtener_conexion():

    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8"
    )


registro_actual = None


# ==========================
# ENVIO CORREOS
# ==========================


def enviar_correo(
    retirada,
    deposito,
    total
):

    token = obtener_token()

    asunto = f"[TAXAS] Modificación expediente {registro_actual['EXPEDIENTE']}"

    contenido = f"""
Se ha modificado un expediente TAXAS.

Expediente: {registro_actual['EXPEDIENTE']}
Usuario: {getpass.getuser()}
Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

VALORES ANTERIORES

TOTALRETIRADASETEX: {registro_actual['TOTALRETIRADASETEX']}
TOTALDEPOSITOSETEX: {registro_actual['TOTALDEPOSITOSETEX']}
TOTALSETEX: {registro_actual['TOTALSETEX']}

VALORES NUEVOS

TOTALRETIRADASETEX: {retirada}
TOTALDEPOSITOSETEX: {deposito}
TOTALSETEX: {total}

Este correo ha sido generado automáticamente por ModificarTaxas.
"""

    email_url = (
        f"https://graph.microsoft.com/v1.0"
        f"/users/{BUZON}/sendMail"
    )

    email_body = {
        "message": {
            "subject": asunto,
            "body": {
                "contentType": "Text",
                "content": contenido
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": "luisponte@vigo.setex.es"
                    },
                    "emailAddress": {
                        "address": "informatica@setex.es"
                    }
                }
            ]
        },
        "saveToSentItems": True
    }

    resp_mail = requests.post(
        email_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json=email_body
    )

    if resp_mail.status_code != 202:
        raise Exception(
            f"Error enviando correo: {resp_mail.text}"
        )




registro_actual = None


# ==========================
# BUSCAR
# ==========================

def buscar():

    global registro_actual

    expediente = txt_expediente.get().strip()

    if not expediente:
        messagebox.showerror(
            "Error",
            "Debe indicar un expediente."
        )
        return

    try:

        conn = obtener_conexion()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM serviciossetex
            WHERE EXPEDIENTE = %s
        """, (expediente,))

        registro_actual = cursor.fetchone()

        cursor.close()
        conn.close()

        if not registro_actual:

            messagebox.showwarning(
                "No encontrado",
                "No existe el expediente."
            )

            return
        
        
        messagebox.showinfo(
            "Expediente encontrado",
            f"El expediente {expediente} ha sido localizado correctamente."
        )


        retirada = float(
            registro_actual["TOTALRETIRADASETEX"]
        )

        deposito = float(
            registro_actual["TOTALDEPOSITOSETEX"]
        )

        total = float(
            registro_actual["TOTALSETEX"]
        )

        lbl_retirada_actual.config(
            text=f"Retirada SETEX: {retirada:.2f}"
        )

        lbl_deposito_actual.config(
            text=f"Depósito SETEX: {deposito:.2f}"
        )

        lbl_total_actual.config(
            text=f"Total SETEX: {total:.2f}"
        )

        txt_retirada.delete(0, tk.END)
        txt_retirada.insert(0, f"{retirada:.2f}")

        txt_deposito.delete(0, tk.END)
        txt_deposito.insert(0, f"{deposito:.2f}")

    except Exception as e:

        messagebox.showerror(
            "Error",
            str(e)
        )


# ==========================
# ACTUALIZAR
# ==========================

def actualizar():

    global registro_actual

    if not registro_actual:

        messagebox.showwarning(
            "Aviso",
            "Primero debe buscar un expediente."
        )

        return

    try:

        retirada = convertir_decimal(
            txt_retirada.get()
        )

        deposito = convertir_decimal(
            txt_deposito.get()
        )

        total = round(
            retirada + deposito,
            2
        )

        texto = f"""
Expediente: {registro_actual['EXPEDIENTE']}

Retirada SETEX:
{float(registro_actual['TOTALRETIRADASETEX']):.2f} -> {retirada:.2f}

Depósito SETEX:
{float(registro_actual['TOTALDEPOSITOSETEX']):.2f} -> {deposito:.2f}

Total SETEX:
{float(registro_actual['TOTALSETEX']):.2f} -> {total:.2f}

¿Desea continuar?
"""

        resp = messagebox.askyesno(
            "Confirmar actualización",
            texto
        )

        if not resp:
            return

        conn = obtener_conexion()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE serviciossetex
            SET
                TOTALRETIRADASETEX = %s,
                TOTALDEPOSITOSETEX = %s,
                TOTALSETEX = %s
            WHERE EXPEDIENTE = %s
        """,
        (
            retirada,
            deposito,
            total,
            registro_actual["EXPEDIENTE"]
        ))

        conn.commit()

        
        enviar_correo(
            retirada,
            deposito,
            total
        )


        cursor.close()
        conn.close()

        usuario = getpass.getuser()

        log = f"""
====================================================
FECHA: {datetime.now()}
USUARIO: {usuario}

EXPEDIENTE: {registro_actual['EXPEDIENTE']}

ANTES
TOTALRETIRADASETEX = {registro_actual['TOTALRETIRADASETEX']}
TOTALDEPOSITOSETEX = {registro_actual['TOTALDEPOSITOSETEX']}
TOTALSETEX = {registro_actual['TOTALSETEX']}

DESPUES
TOTALRETIRADASETEX = {retirada}
TOTALDEPOSITOSETEX = {deposito}
TOTALSETEX = {total}

RESULTADO = OK
====================================================
"""

        escribir_log(log)

        buscar()

        messagebox.showinfo(
            "Correcto",
            "Registro actualizado correctamente."
        )

    except Exception as e:

        escribir_log(
            f"{datetime.now()} ERROR: {str(e)}"
        )

        messagebox.showerror(
            "Error",
            str(e)
        )


# ==========================
# INTERFAZ
# ==========================

def validar_login():

    usuario = txt_usuario.get().strip()
    password = txt_password.get().strip()

    if usuario in USUARIOS and USUARIOS[usuario] == password:
        ventana_login.destroy()
        root.deiconify()

    else:
        messagebox.showerror(
            "Acceso denegado",
            "Usuario o contraseña incorrectos."
        )


def cerrar_login():
    root.destroy()

root = tk.Tk()
root.withdraw()

root.title("Actualización Servicios SETEX")
root.geometry("500x420")
root.resizable(False, False)

vcmd = (
    root.register(validar_decimal),
    "%P"
)

tk.Label(
    root,
    text="Expediente",
    font=("Arial", 10, "bold")
).pack(pady=(15, 5))

txt_expediente = tk.Entry(
    root,
    width=25
)

txt_expediente.pack()

tk.Button(
    root,
    text="Buscar",
    command=buscar,
    width=12
).pack(pady=10)

tk.Label(
    root,
    text="DATOS ACTUALES",
    font=("Arial", 11, "bold")
).pack(pady=(10, 10))

lbl_retirada_actual = tk.Label(
    root,
    text="Retirada SETEX: 0.00",
    font=("Arial", 10)
)
lbl_retirada_actual.pack()

lbl_deposito_actual = tk.Label(
    root,
    text="Depósito SETEX: 0.00",
    font=("Arial", 10)
)
lbl_deposito_actual.pack()

lbl_total_actual = tk.Label(
    root,
    text="Total SETEX: 0.00",
    font=("Arial", 10, "bold")
)
lbl_total_actual.pack()

tk.Label(
    root,
    text="Nueva Retirada SETEX"
).pack(pady=(20, 5))

txt_retirada = tk.Entry(
    root,
    width=20,
    validate="key",
    validatecommand=vcmd
)
txt_retirada.pack()

tk.Label(
    root,
    text="Nuevo Depósito SETEX"
).pack(pady=(10, 5))

txt_deposito = tk.Entry(
    root,
    width=20,
    validate="key",
    validatecommand=vcmd
)
txt_deposito.pack()

tk.Button(
    root,
    text="Actualizar",
    command=actualizar,
    bg="green",
    fg="white",
    width=15
).pack(pady=25)

# ==========================
# LOGIN
# ==========================

ventana_login = tk.Toplevel()

ventana_login.title("Acceso ModificarTaxas")
ventana_login.geometry("300x180")
ventana_login.resizable(False, False)

ventana_login.protocol(
    "WM_DELETE_WINDOW",
    cerrar_login
)

tk.Label(
    ventana_login,
    text="Usuario"
).pack(pady=(15, 5))

txt_usuario = tk.Entry(
    ventana_login,
    width=25
)
txt_usuario.pack()

tk.Label(
    ventana_login,
    text="Contraseña"
).pack(pady=(10, 5))

txt_password = tk.Entry(
    ventana_login,
    show="*",
    width=25
)
txt_password.pack()

tk.Button(
    ventana_login,
    text="Entrar",
    command=validar_login,
    width=15
).pack(pady=20)

txt_usuario.focus()

root.mainloop()