"""
Candado de lo que el programa puede pedir a Telegram con la cuenta del dueño.

Regla del proyecto: con la cuenta personal del dueño SOLO se lee y se
organizan carpetas; nunca se envía nada, ni se marca como leído, ni se
une, sale, borra o bloquea nada. Para que eso no dependa de que el resto del
código "se porte bien", toda petición pasa por `comprobar()` antes de salir
(lector.py lo engancha en el punto por el que Telethon envía todas sus
peticiones). Lo que no está en la lista blanca del modo activo se bloquea y
se registra.

Las peticiones se identifican por su nombre completo en la API de
Telegram (espacio + clase), p. ej. "messages.GetDialogFiltersRequest".
"""

# Solo lectura: lo que Telethon necesita para funcionar y para leer chats.
LECTURA = frozenset({
    "updates.GetStateRequest",
    "updates.GetDifferenceRequest",
    "updates.GetChannelDifferenceRequest",
    "help.GetConfigRequest",
    "help.GetCdnConfigRequest",
    "users.GetUsersRequest",
    "users.GetFullUserRequest",
    "contacts.GetContactsRequest",
    "contacts.ResolveUsernameRequest",
    "channels.GetChannelsRequest",
    "channels.GetFullChannelRequest",
    "channels.GetMessagesRequest",
    "messages.GetChatsRequest",
    "messages.GetFullChatRequest",
    "messages.GetDialogsRequest",
    "messages.GetPeerDialogsRequest",
    "messages.GetHistoryRequest",
    "messages.GetMessagesRequest",
    "messages.SearchRequest",
    "messages.SearchGlobalRequest",
    "messages.GetDialogFiltersRequest",
    # Pregunta a qué canal lleva un enlace de invitación, sin unirse.
    "messages.CheckChatInviteRequest",
})

# Organizar carpetas (crear, cambiar los chats de una y borrarla: borrar una
# carpeta no borra ningún chat).
CARPETAS = frozenset({"messages.UpdateDialogFilterRequest"})

# Solo para el comando de iniciar sesión, que ejecuta el dueño a mano.
INICIO_SESION = frozenset({
    "auth.SendCodeRequest",
    "auth.ResendCodeRequest",
    "auth.SignInRequest",
    "auth.CheckPasswordRequest",
    "account.GetPasswordRequest",
})

# Registro de acciones de un canal (entradas y salidas de los canales de
# venta): solo lectura, autorizado por el dueño el 2026-10-28.
REGISTRO = frozenset({"channels.GetAdminLogRequest"})

# Quién se unió con cada enlace de invitación (lo mismo que se ve en la app
# en Enlaces de invitación → «X se unieron»): solo lectura, autorizado por el
# dueño el 2026-10-29, para emparejar cada venta de overoption con su persona;
# y el 2026-10-30, también dentro del lector (los enlaces de las ventas nuevas).
INVITADOS = frozenset({"messages.GetChatInviteImportersRequest"})

MODOS = {
    "iniciar-sesion": LECTURA | INICIO_SESION,
    "historico": LECTURA,
    # El lector en simulación no puede ni pedir cambios de carpetas: aunque
    # hubiera un fallo en el código, Telegram no recibiría nada que escriba.
    "simulacion": LECTURA | REGISTRO | INVITADOS | {"account.UpdateStatusRequest"},
    "lector": LECTURA | REGISTRO | INVITADOS | CARPETAS | {"account.UpdateStatusRequest"},
    # Leer la lista de suscriptores del canal principal (solo lectura;
    # autorizado por el dueño el 2026-10-23), para no ofrecer la gratuita a
    # quien ya estaba dentro.
    "suscriptores": LECTURA | {"channels.GetParticipantsRequest"},
    # Miembros y registro de los canales de venta (ventas.py; solo lectura,
    # autorizado por el dueño el 2026-10-28).
    "ventas": LECTURA | REGISTRO | {"channels.GetParticipantsRequest"},
    # Quién se unió con los enlaces de las ventas de overoption (invitaciones.py).
    "invitaciones": LECTURA | INVITADOS,
}


class PeticionProhibida(Exception):
    pass


def nombre_peticion(peticion):
    """'messages.GetDialogFiltersRequest' a partir del objeto de Telethon."""
    espacio = type(peticion).__module__.rsplit(".", 1)[-1]
    return f"{espacio}.{type(peticion).__name__}"


def comprobar(peticion, modo):
    """Lanza PeticionProhibida si `peticion` no se permite en `modo`."""
    if isinstance(peticion, (list, tuple)):
        for p in peticion:
            comprobar(p, modo)
        return
    nombre = nombre_peticion(peticion)
    if nombre not in MODOS[modo]:
        raise PeticionProhibida(f"{nombre} no está permitida (modo {modo})")
    # "No en línea" sí; "en línea", no: el programa no debe hacer parecer
    # que el dueño está conectado.
    if nombre == "account.UpdateStatusRequest" and getattr(peticion, "offline", None) is not True:
        raise PeticionProhibida("account.UpdateStatusRequest solo se permite con offline=True")
