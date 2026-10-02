import tkinter as tk
from tkinter import messagebox
import mysql.connector
from datetime import datetime, timedelta
import os
import getpass
import requests
from msal import ConfidentialClientApplication
import secrets
import socket

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

BUZON = "noreply@setex.es"

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]
GRAPH_URL = "https://graph.microsoft.com/v1.0"

# ==========================
# DESTINATARIOS
# ==========================

DESTINATARIOS_2FA = [
    "informatica@setex.es"
]

DESTINATARIOS_AUDITORIA = [
    "informatica@setex.es"
]

# ==========================
# USUARIOS DE LA APLICACION
# ==========================

USUARIOS = {
    "admin": "Taxas@2026"
}

# ==========================
# VARIABLES GLOBALES
# ==========================

registro_actual = None

codigo_2fa_actual = None
codigo_2fa_expira = None
codigo_2fa_usado = True

usuario_app_logado = None


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
# MICROSOFT GRAPH
# ==========================

def obtener_token():

    app = ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )

    result = app.acquire_token_for_client(
        scopes=SCOPES
    )

    if "access_token" not in result:
        raise Exception(
            f"Error obteniendo token de Microsoft Graph: {result}"
        )

    return result["access_token"]


def enviar_correo_graph(asunto, contenido, destinatarios):

    token = obtener_token()

    email_url = f"{GRAPH_URL}/users/{BUZON}/sendMail"

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
                        "address": correo
                    }
                }
                for correo in destinatarios
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


# ==========================
# ENVIO CODIGO 2FA
# ==========================

def generar_codigo_2fa():

    return str(secrets.randbelow(900000) + 100000)


def enviar_codigo_2fa(usuario):

    global codigo_2fa_actual
    global codigo_2fa_expira
    global codigo_2fa_usado

    codigo_2fa_actual = generar_codigo_2fa()
    codigo_2fa_expira = datetime.now() + timedelta(minutes=5)
    codigo_2fa_usado = False

    asunto = "[TAXAS] Código de acceso ModificarTaxas"

    contenido = f"""
Se ha solicitado acceso a la aplicación ModificarTaxas.

Usuario aplicación: {usuario}
Usuario Windows: {getpass.getuser()}
Equipo: {socket.gethostname()}
Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

Código de verificación:

{codigo_2fa_actual}

Este código es de un solo uso y caduca en 5 minutos.

Si no has solicitado este acceso, revisa el equipo indicado.
"""

    enviar_correo_graph(
        asunto,
        contenido,
        DESTINATARIOS_2FA
    )

    escribir_log(f"""
====================================================
FECHA: {datetime.now()}
EVENTO: CODIGO 2FA ENVIADO
USUARIO APP: {usuario}
USUARIO WINDOWS: {getpass.getuser()}
EQUIPO: {socket.gethostname()}
DESTINATARIOS: {', '.join(DESTINATARIOS_2FA)}
====================================================
""")


# ==========================
# VALIDACION IMPORTES
# ==========================

def validar_decimal(texto):

    if texto == "":
        return True

    permitidos = "0123456789,."

    return all(c in permitidos for c in texto)


def convertir_decimal(valor):

    valor_original = valor
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
            f"El importe '{valor_original}' no es válido.\n\n"
            "Solo se permiten números.\n\n"
            "Ejemplos válidos:\n"
            "123\n"
            "123,45\n"
            "123.45"
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


# ==========================
# ENVIO CORREO AUDITORIA
# ==========================

def enviar_correo_modificacion(retirada, deposito, total):

    asunto = f"[TAXAS] Modificación expediente {registro_actual['EXPEDIENTE']}"

    contenido = f"""
Se ha modificado un expediente TAXAS.

Expediente: {registro_actual['EXPEDIENTE']}
Usuario aplicación: {usuario_app_logado}
Usuario Windows: {getpass.getuser()}
Equipo: {socket.gethostname()}
Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

VALORES ANTERIORES

TOTALRETIRADASETEX: {registro_actual['TOTALRETIRADASETEX']}
TOTALDEPOSITOSETEX: {registro_actual['TOTALDEPOSITOSETEX']}
TOTALSETEX: {registro_actual['TOTALSETEX']}

VALORES NUEVOS

TOTALRETIRADASETEX: {retirada:.2f}
TOTALDEPOSITOSETEX: {deposito:.2f}
TOTALSETEX: {total:.2f}

Este correo ha sido generado automáticamente por ModificarTaxas.
"""

    enviar_correo_graph(
        asunto,
        contenido,
        DESTINATARIOS_AUDITORIA
    )


# ==========================
# BUSCAR EXPEDIENTE
# ==========================

def buscar(mostrar_aviso=True):

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
            LIMIT 1
        """, (expediente,))

        registro_actual = cursor.fetchone()

        cursor.close()
        conn.close()

        if not registro_actual:

            lbl_retirada_actual.config(
                text="Retirada SETEX: 0.00"
            )

            lbl_deposito_actual.config(
                text="Depósito SETEX: 0.00"
            )

            lbl_total_actual.config(
                text="Total SETEX: 0.00"
            )

            txt_retirada.delete(0, tk.END)
            txt_deposito.delete(0, tk.END)

            messagebox.showwarning(
                "No encontrado",
                "No existe el expediente."
            )

            return

        retirada_actual = float(
            registro_actual["TOTALRETIRADASETEX"]
        )

        deposito_actual = float(
            registro_actual["TOTALDEPOSITOSETEX"]
        )

        total_actual = float(
            registro_actual["TOTALSETEX"]
        )

        lbl_retirada_actual.config(
            text=f"Retirada SETEX: {retirada_actual:.2f}"
        )

        lbl_deposito_actual.config(
            text=f"Depósito SETEX: {deposito_actual:.2f}"
        )

        lbl_total_actual.config(
            text=f"Total SETEX: {total_actual:.2f}"
        )

        txt_retirada.delete(0, tk.END)
        txt_retirada.insert(0, f"{retirada_actual:.2f}")

        txt_deposito.delete(0, tk.END)
        txt_deposito.insert(0, f"{deposito_actual:.2f}")

        if mostrar_aviso:
            messagebox.showinfo(
                "Expediente encontrado",
                f"El expediente {expediente} ha sido localizado correctamente."
            )

    except Exception as e:

        escribir_log(
            f"{datetime.now()} ERROR BUSCAR: {str(e)}"
        )

        messagebox.showerror(
            "Error",
            str(e)
        )


# ==========================
# ACTUALIZAR EXPEDIENTE
# ==========================

def actualizar():

    global registro_actual

    if not registro_actual:

        messagebox.showwarning(
            "Aviso",
            "Primero debe buscar un expediente."
        )

        return

    conn = None
    cursor = None

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
            LIMIT 1
        """,
        (
            retirada,
            deposito,
            total,
            registro_actual["EXPEDIENTE"]
        ))

        conn.commit()

        try:

            enviar_correo_modificacion(
                retirada,
                deposito,
                total
            )

            resultado_correo = "CORREO ENVIADO OK"

        except Exception as error_correo:

            resultado_correo = f"ERROR ENVIANDO CORREO: {str(error_correo)}"

            messagebox.showwarning(
                "Aviso",
                "El expediente se actualizó correctamente, pero falló el envío del correo.\n\n"
                f"Detalle: {str(error_correo)}"
            )

        usuario_windows = getpass.getuser()

        log = f"""
====================================================
FECHA: {datetime.now()}
USUARIO APP: {usuario_app_logado}
USUARIO WINDOWS: {usuario_windows}
EQUIPO: {socket.gethostname()}

EXPEDIENTE: {registro_actual['EXPEDIENTE']}

ANTES
TOTALRETIRADASETEX = {registro_actual['TOTALRETIRADASETEX']}
TOTALDEPOSITOSETEX = {registro_actual['TOTALDEPOSITOSETEX']}
TOTALSETEX = {registro_actual['TOTALSETEX']}

DESPUES
TOTALRETIRADASETEX = {retirada:.2f}
TOTALDEPOSITOSETEX = {deposito:.2f}
TOTALSETEX = {total:.2f}

RESULTADO = OK
{resultado_correo}
====================================================
"""

        escribir_log(log)

        buscar(mostrar_aviso=False)

        messagebox.showinfo(
            "Correcto",
            "Registro actualizado correctamente."
        )

    except Exception as e:

        escribir_log(
            f"{datetime.now()} ERROR ACTUALIZAR: {str(e)}"
        )

        messagebox.showerror(
            "Error",
            str(e)
        )

    finally:

        try:
            if cursor:
                cursor.close()
        except:
            pass

        try:
            if conn:
                conn.close()
        except:
            pass


# ==========================
# LOGIN Y DOBLE FACTOR
# ==========================

def validar_usuario_password():

    usuario = txt_usuario.get().strip()
    password = txt_password.get().strip()

    if not usuario or not password:
        messagebox.showerror(
            "Error",
            "Debe indicar usuario y contraseña."
        )
        return

    if usuario in USUARIOS and USUARIOS[usuario] == password:

        try:

            enviar_codigo_2fa(usuario)

            txt_usuario.config(state="disabled")
            txt_password.config(state="disabled")
            btn_entrar.config(state="disabled")

            txt_codigo.config(state="normal")
            btn_validar_codigo.config(state="normal")
            btn_reenviar_codigo.config(state="normal")

            txt_codigo.delete(0, tk.END)
            txt_codigo.focus()

            messagebox.showinfo(
                "Código enviado",
                "Se ha enviado un código de verificación por correo.\n\n"
                "Introduce el código recibido para acceder."
            )

        except Exception as e:

            escribir_log(
                f"{datetime.now()} ERROR ENVIANDO CODIGO 2FA: {str(e)}"
            )

            messagebox.showerror(
                "Error",
                f"No se pudo enviar el código de verificación.\n\n{str(e)}"
            )

    else:

        escribir_log(f"""
====================================================
FECHA: {datetime.now()}
EVENTO: LOGIN FALLIDO
USUARIO INTENTADO: {usuario}
USUARIO WINDOWS: {getpass.getuser()}
EQUIPO: {socket.gethostname()}
====================================================
""")

        messagebox.showerror(
            "Acceso denegado",
            "Usuario o contraseña incorrectos."
        )


def validar_codigo_2fa():

    global codigo_2fa_actual
    global codigo_2fa_expira
    global codigo_2fa_usado
    global usuario_app_logado

    usuario = txt_usuario.get().strip()
    codigo_introducido = txt_codigo.get().strip()

    if not codigo_introducido:
        messagebox.showerror(
            "Error",
            "Debe introducir el código de verificación."
        )
        return

    if codigo_2fa_usado:
        messagebox.showerror(
            "Error",
            "Este código ya fue utilizado o no hay ningún código activo."
        )
        return

    if codigo_2fa_actual is None:
        messagebox.showerror(
            "Error",
            "No hay código de verificación activo."
        )
        return

    if datetime.now() > codigo_2fa_expira:

        codigo_2fa_usado = True
        codigo_2fa_actual = None

        messagebox.showerror(
            "Código caducado",
            "El código ha caducado.\n\nSolicita un nuevo código."
        )
        return

    if codigo_introducido != codigo_2fa_actual:

        escribir_log(f"""
====================================================
FECHA: {datetime.now()}
EVENTO: CODIGO 2FA INCORRECTO
USUARIO APP: {usuario}
USUARIO WINDOWS: {getpass.getuser()}
EQUIPO: {socket.gethostname()}
====================================================
""")

        messagebox.showerror(
            "Código incorrecto",
            "El código introducido no es correcto."
        )

        return

    codigo_2fa_usado = True
    codigo_2fa_actual = None
    codigo_2fa_expira = None

    usuario_app_logado = usuario

    escribir_log(f"""
====================================================
FECHA: {datetime.now()}
EVENTO: LOGIN CORRECTO CON 2FA
USUARIO APP: {usuario_app_logado}
USUARIO WINDOWS: {getpass.getuser()}
EQUIPO: {socket.gethostname()}
====================================================
""")

    ventana_login.destroy()
    root.deiconify()


def reenviar_codigo_2fa():

    usuario = txt_usuario.get().strip()

    if not usuario:
        messagebox.showerror(
            "Error",
            "No hay usuario indicado."
        )
        return

    try:

        enviar_codigo_2fa(usuario)

        txt_codigo.delete(0, tk.END)
        txt_codigo.focus()

        messagebox.showinfo(
            "Código reenviado",
            "Se ha generado y enviado un nuevo código.\n\n"
            "El código anterior ya no es válido."
        )

    except Exception as e:

        escribir_log(
            f"{datetime.now()} ERROR REENVIANDO CODIGO 2FA: {str(e)}"
        )

        messagebox.showerror(
            "Error",
            f"No se pudo reenviar el código.\n\n{str(e)}"
        )


def cerrar_login():

    root.destroy()


# ==========================
# INTERFAZ PRINCIPAL
# ==========================

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
# VENTANA LOGIN
# ==========================

ventana_login = tk.Toplevel(root)

ventana_login.title("Acceso ModificarTaxas")
ventana_login.geometry("340x300")
ventana_login.resizable(False, False)

ventana_login.protocol(
    "WM_DELETE_WINDOW",
    cerrar_login
)

ventana_login.grab_set()

tk.Label(
    ventana_login,
    text="Usuario",
    font=("Arial", 10, "bold")
).pack(pady=(15, 5))

txt_usuario = tk.Entry(
    ventana_login,
    width=28
)
txt_usuario.pack()

tk.Label(
    ventana_login,
    text="Contraseña",
    font=("Arial", 10, "bold")
).pack(pady=(10, 5))

txt_password = tk.Entry(
    ventana_login,
    show="*",
    width=28
)
txt_password.pack()

btn_entrar = tk.Button(
    ventana_login,
    text="Validar usuario",
    command=validar_usuario_password,
    width=18
)
btn_entrar.pack(pady=15)

tk.Label(
    ventana_login,
    text="Código de verificación",
    font=("Arial", 10, "bold")
).pack(pady=(5, 5))

txt_codigo = tk.Entry(
    ventana_login,
    width=28,
    state="disabled"
)
txt_codigo.pack()

btn_validar_codigo = tk.Button(
    ventana_login,
    text="Entrar",
    command=validar_codigo_2fa,
    width=18,
    state="disabled",
    bg="green",
    fg="white"
)
btn_validar_codigo.pack(pady=(15, 5))

btn_reenviar_codigo = tk.Button(
    ventana_login,
    text="Reenviar código",
    command=reenviar_codigo_2fa,
    width=18,
    state="disabled"
)
btn_reenviar_codigo.pack()

txt_usuario.focus()

root.mainloop()