# -*- coding: utf-8 -*-
"""
Monitoreo predictivo del conjunto motor Emerson P55CST-1247 + bomba Goulds 3642
Universidad de las Fuerzas Armadas ESPE – Sede Latacunga | Ingeniería Electromecánica

Archivos: app_rodamientos.py (pantallas), nucleo.py (cálculos), estilos.py, logos, .streamlit/,
datos_prueba/ (data sintética del docente), catalogos/ (hojas de datos).
Ejecutar en la PC:  python -m streamlit run app_rodamientos.py
"""
import base64
import html
import json
import math
import time
import warnings
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st

BASE = Path(__file__).resolve().parent
_ICONO = BASE / "logo_em.png"
st.set_page_config(page_title="ESPE | Monitoreo Goulds 3642", page_icon=str(_ICONO) if _ICONO.exists() else "⚡", layout="wide")

import nucleo as N  # noqa: E402
from estilos import CSS  # noqa: E402

PALETA = ["#1F6FEB", "#0A1F44", "#00A3FF", "#F2B705", "#5B8DEF", "#8A9BB8", "#0D3B8C"]
DOM_EST = [N.NOMBRE_ESTADO[e] for e in N.ESTADOS]
RAN_EST = [N.COLOR_ESTADO[e] for e in N.ESTADOS]
ESCALA_EST = alt.Scale(domain=DOM_EST, range=RAN_EST)


# =============================================================================
# Utilidades de interfaz
# =============================================================================
def fmt(x, nd=1):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "—"
        return f"{float(x):.{nd}f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(x)


def muestra(datos: pd.DataFrame, n: int = 600) -> pd.DataFrame:
    if len(datos) <= n:
        return datos
    return datos.iloc[np.linspace(0, len(datos) - 1, n).astype(int)]


def imagen_b64(nombre: str):
    r = BASE / nombre
    return "data:image/png;base64," + base64.b64encode(r.read_bytes()).decode() if r.exists() else None


def texto_tarjeta(que: str, como: str, datos: str) -> None:
    st.markdown(f"""<div class="explica"><div><span class="etq">Qué muestra</span>{que}</div>
<div><span class="etq">Cómo se lee</span>{como}</div>
<div class="datos"><span class="etq">Lo que dicen los datos</span>{datos}</div></div>""", unsafe_allow_html=True)


def tarjetas_semaforo(items) -> None:
    bloques = ""
    for titulo, valor, zona, sub, *color in items:
        c = color[0] if color else (N.COLOR_ZONA.get(int(zona)) if zona is not None and not pd.isna(zona) else "#8A9BB8")
        bloques += (f'<div class="luz" style="background:{c}"><div class="t">{html.escape(titulo)}</div>'
                    f'<div class="v">{html.escape(valor)}</div><div class="s">{html.escape(sub)}</div></div>')
    st.markdown(f'<div class="semaforo">{bloques}</div>', unsafe_allow_html=True)


def tarjetas_diagnostico(diags) -> None:
    for d in diags:
        st.markdown(f"""<div class="diag {'critico' if d['Gravedad'] == 2 else ''}">
<h4>{'🔴' if d['Gravedad'] == 2 else '🟡'} {html.escape(d['Falla'])}</h4><div class="ev">{html.escape(d['Evidencia'])}</div>
<div class="cols"><div><b class="t">Causas probables</b><ul>{''.join(f'<li>{html.escape(c)}</li>' for c in d['Causas'])}</ul></div>
<div><b class="t">Qué hacer</b><ul>{''.join(f'<li>{html.escape(a)}</li>' for a in d['Acciones'])}</ul></div></div></div>""",
                    unsafe_allow_html=True)


def chip(estado: str) -> str:
    return f'<span class="chip" style="background:{N.COLOR_ESTADO.get(estado, "#8A9BB8")}">{html.escape(N.NOMBRE_ESTADO.get(estado, estado))}</span>'


def mostrar_encabezado(eq: dict) -> None:
    espe, em = imagen_b64("logo_espe.png"), imagen_b64("logo_em.png")
    logo_espe = f'<img class="espe" src="{espe}">' if espe else "<b>Universidad de las Fuerzas Armadas ESPE – Sede Latacunga</b>"
    logo_em = f'<img class="em" src="{em}">' if em else ""
    ops = [o for o in eq.get("operadores", []) if str(o.get("Nombre", "")).strip()]
    operadores = ("<ul>" + "".join(f"<li>{html.escape(str(o['Nombre']))}"
                                   + (f" <span style='font-weight:400;color:#5A6B88'>({html.escape(str(o.get('Función', '')))})</span>" if o.get("Función") else "")
                                   + "</li>" for o in ops) + "</ul>") if ops else '<div class="vacio">Agrégalos en «⚙️ Configuración»</div>'
    curso = " | ".join(x for x in [eq.get("asignatura", ""), f"NRC {eq['nrc']}" if eq.get("nrc") else "", eq.get("periodo", "")] if x)
    ficha = f'<div class="ficha"><div class="titulo">Asignatura</div><div class="valor">{html.escape(curso)}</div></div>' if curso else ""
    st.markdown(f"""<div class="hero"><div class="hero-logos">{logo_espe}{logo_em}</div><div class="hero-rayo"></div>
<div class="hero-banda"><p class="hero-carrera">Ingeniería Electromecánica | Departamento de Eléctrica y Electrónica</p>
<h1>Mantenimiento predictivo de rodamientos – Bomba Goulds 3642</h1>
<p class="sub">{html.escape(eq.get('proyecto', ''))}. Motor {html.escape(eq['motor_marca'])} {html.escape(eq['motor_modelo'])}; temperaturas en °F.</p></div>
<div class="hero-fichas"><div class="ficha docente"><div class="titulo">Docente responsable</div><div class="valor">{N.DOCENTE}</div></div>
<div class="ficha"><div class="titulo">Operadores a cargo</div>{operadores}</div>{ficha}</div></div>""", unsafe_allow_html=True)


def ficha_datasheet(c: dict) -> str:
    filas = [("Fabricante", c["Marca"]), ("Modelo", c["Modelo"]), ("Tipo", c["Tipo"]),
             ("Rango", f"{c['T_min_C']} a {c['T_max_C']} °C"), ("Relación óptica D:S", f"{fmt(c['DS'], 2 if float(c['DS']) % 1 else 0)} : 1"),
             ("Tiempo de respuesta", f"{c['Resp_ms']} ms"),
             ("Exactitud", f"±{fmt(c['Exact_C'])} °C" + (f" o ±{fmt(c['Exact_pct'])} % (el mayor)" if c.get("Exact_pct") else "")),
             ("Emisividad", f"{fmt(c['Emis_min'], 2)} fija" if c["Emis_max"] == c["Emis_min"] else f"ajustable {fmt(c['Emis_min'], 2)}–{fmt(c['Emis_max'], 2)}"),
             ("Salidas", c["Salidas"]), ("Alimentación", f"{fmt(c['V_min'])} – {fmt(c['V_max'])} VDC"),
             ("T. ambiente del cabezal", f"{c.get('Tcab_C')} °C"), ("T. ambiente de la electrónica", f"{c.get('Telec_C')} °C"),
             ("Protección", f"IP{int(c['IP'])}" if c.get("IP") else "No indicado en el folleto"), ("Montaje", c["Montaje"]),
             ("Proveedor en Ecuador", c.get("Proveedor") or "Importación"),
             ("Precio", f"USD {fmt(c['Precio_USD'], 2)}" if c.get("Precio_USD") else "Solicitar cotización"), ("Notas", c.get("Notas", ""))]
    return '<table class="ds">' + "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in filas) + "</table>"


# =============================================================================
# Carga de configuración y datos
# =============================================================================
st.markdown(CSS, unsafe_allow_html=True)
if "editor_ver" not in st.session_state:
    st.session_state.editor_ver = 0
if msg := st.session_state.pop("msg", None):
    st.toast(msg, icon="💾")

CLAVE_APP = str(N.secreto("app_password", "") or "")
if CLAVE_APP and not st.session_state.get("autenticado"):
    logo_l = imagen_b64("logo_espe.png")
    st.markdown(f'<div class="login">{f"<img src={chr(34)}{logo_l}{chr(34)} style=max-width:100%>" if logo_l else ""}'
                '<h2>Monitoreo predictivo Goulds 3642</h2><p>Ingeniería Electromecánica – ESPE Latacunga</p></div>', unsafe_allow_html=True)
    _c = st.columns([1, 2, 1])
    with _c[1].form("login"):
        clave_in = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar", type="primary", width="stretch"):
            if clave_in == CLAVE_APP:
                st.session_state["autenticado"] = True
                st.rerun()
            st.error("Contraseña incorrecta.")
    st.stop()


def cargar_equipo() -> dict:
    datos = N.cargar_json(N.ARCH_EQUIPO, {})
    if datos and datos.get("version") != 5:  # versión anterior: conservar solo lo ingresado por el usuario
        datos = {k: v for k, v in datos.items() if k in ("operadores", "asignatura", "nrc", "periodo", "proyecto")}
        datos = {**N.DEF_EQUIPO, **datos, "version": 5}
        N.guardar_json(N.ARCH_EQUIPO, datos)
    return {**N.DEF_EQUIPO, **(datos or {}), "version": 5}


def cargar_catalogo() -> list:
    c = N.cargar_json(N.ARCH_CATALOGO, None)
    if isinstance(c, dict) and c.get("version") == 5:
        return c["items"]
    return json.loads(json.dumps(N.CATALOGO_DEF))


try:
    equipo = cargar_equipo()
    catalogo = cargar_catalogo()
    alertas_cfg = N.cargar_json(N.ARCH_ALERTAS, N.ALERTAS_DEF)
    mant = N.cargar_json(N.ARCH_MANT, N.MANT_DEF)
    hist_rod = N.cargar_json(N.ARCH_HIST_ROD, {"filas": []})
    modelo_temp = N.cargar_json(N.ARCH_MODELO, None)
    if modelo_temp and modelo_temp.get("objetivo") != "T_F":
        modelo_temp = None
    reg = N.cargar_registros()
except Exception as ex:
    st.error(f"No se pudo conectar con la base de datos: {ex}")
    st.stop()

base = N.cargar_base()
if base.empty:
    st.error("No se encontró la data sintética del ingeniero en la carpeta «datos_prueba».")
    st.stop()
dbase = N.derivar(base, equipo)
modelos = N.entrenar_modelos(dbase, "v5")
dbase = N.completar_estado(dbase, None)
dreg = N.completar_estado(N.derivar(reg, equipo), modelos) if len(reg) else pd.DataFrame(columns=dbase.columns)
dtodo = pd.concat([dbase, dreg], ignore_index=True)
mant_estado = N.estado_mantenimiento(mant)
mant_venc = mant_estado[mant_estado["nivel"] == 2].to_dict("records")

try:
    import streamlit.components.v1 as components
    components.html("""<script>const d=window.parent.document; d.documentElement.lang="es";
d.documentElement.setAttribute("translate","no"); d.documentElement.classList.add("notranslate");</script>""", height=0)
except Exception:
    pass

mostrar_encabezado(equipo)

with st.sidebar:
    if (logo := imagen_b64("logo_em.png")):
        st.markdown(f'<div style="text-align:center;margin-bottom:.4rem"><img src="{logo}" style="width:120px;border-radius:50%;background:#fff;padding:6px"></div>',
                    unsafe_allow_html=True)
    st.markdown(f'<div class="lateral-titulo">Docente responsable</div><div class="lateral-valor">{N.DOCENTE}</div>', unsafe_allow_html=True)
    ops = [o["Nombre"] for o in equipo.get("operadores", []) if str(o.get("Nombre", "")).strip()]
    if ops:
        st.markdown('<div class="lateral-titulo">Operadores a cargo</div>' + "".join(f'<div class="lateral-valor">• {html.escape(n)}</div>' for n in ops),
                    unsafe_allow_html=True)
    st.divider()
    st.caption("☁️ Datos en la nube (Supabase)" if N.NUBE else "💻 Datos en esta computadora")
    if st.button("🔄 Actualizar datos", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    filtro = st.radio("Datos a analizar", [N.ORIGEN_BASE, "Registros nuevos", "Todos"], index=0)
    st.metric("Data del ingeniero", f"{len(dbase):,} h".replace(",", "."), f"{int((dbase['estado_bomba'] == 1).sum())} h en operación", delta_color="off")
    st.metric("Registros nuevos", len(dreg))

d = {N.ORIGEN_BASE: dbase, "Registros nuevos": dreg, "Todos": dtodo}[filtro].copy()
dop = d[d["estado_bomba"] == 1].copy()
req_ir = N.requisitos_ir(dop if len(dop) else dbase, equipo)
tabla_ir = N.evaluar_catalogo(catalogo, req_ir)

SECCIONES = ["🏠 Inicio", "➕ Registrar", "🩺 Diagnóstico", "⚙️ Rodamientos", "💧 Cavitación", "🧠 Estado y RUL",
             "🛠️ Mantenimiento", "📊 Gráficas", "🔍 Modelo", "🎯 Estimador", "🌡️ Transmisor IR", "▶️ Simulación",
             "📋 Datos", "🔔 Alertas", "⚙️ Configuración", "📄 Informe"]
with st.container(key="nav"):
    nav = st.radio("Sección", SECCIONES, horizontal=True, label_visibility="collapsed", key="seccion")

hoy_txt = datetime.now().strftime("%Y-%m-%d")
if alertas_cfg.get("activo") and mant_venc and mant.get("ultimo_aviso") != hoy_txt:
    ok_, det_ = N.telegram_enviar("🛠️ <b>Mantenimiento pendiente</b> – Goulds 3642 ESPE\n" + "\n".join(
        f"• {html.escape(t['Tarea'])}: {html.escape(t['Estado'])}" for t in mant_venc), alertas_cfg)
    mant["ultimo_aviso"] = hoy_txt
    N.guardar_json(N.ARCH_MANT, mant)
    N.registrar_alerta(alertas_cfg, "Mantenimiento", f"{len(mant_venc)} tareas vencidas", ok_, det_)


def zona_margen(m):
    return np.nan if m is None or pd.isna(m) else 2 if m <= N.REGLAS["margen_severa"] else 1 if m <= N.REGLAS["margen_incipiente"] else 0


def tarjetas_estado(f: dict) -> None:
    rul = f.get("RUL_h")
    zr = None if rul is None or pd.isna(rul) else (2 if rul <= equipo["rul_aviso_h"] / 4 else 1 if rul <= equipo["rul_aviso_h"] else 0)
    tarjetas_semaforo([
        ("Estado de falla", N.NOMBRE_ESTADO.get(f["estado"], f["estado"]), None, str(f.get("fuente_estado", ""))[:60], N.COLOR_ESTADO.get(f["estado"])),
        ("Temperatura IR del escudo", f"{fmt(f.get('T_F'))} °F", f.get("zona_T"), f"{fmt(f.get('temperatura_motor_C'))} °C | alarma {fmt(N.c_a_f(equipo['alarma_C']), 0)} °F"),
        ("Vida remanente rodamiento", (f"{fmt(rul, 0)} h" + (" o más" if rul and rul >= N.RUL_TOPE_H - 1 else "")) if rul is not None and not pd.isna(rul) else "—",
         zr, f"aviso a {fmt(equipo['rul_aviso_h'], 0)} h"),
        ("Margen NPSH", f"{fmt(f.get('margen_NPSH_m'), 2)} m", zona_margen(f.get("margen_NPSH_m")), f"Latacunga: {fmt(f.get('margen_lat_m'), 2)} m"),
        ("Vibración máxima", f"{fmt(f.get('Vib_max'), 2)} mm/s", f.get("zona_vib"), "ISO 10816 clase I"),
        ("Carga del motor", f"{fmt(f.get('carga_pct'), 0)} %", f.get("zona_carga"), f"{fmt(f.get('I_prom_A'), 2)} A de {equipo['motor_i']} A"),
    ])


# =============================================================================
# 🏠 Inicio
# =============================================================================
if nav == "🏠 Inicio":
    st.subheader("Estado general del equipo")
    if dop.empty:
        st.info("No hay registros en operación en el conjunto seleccionado. Registra mediciones en «➕ Registrar».")
    else:
        ult = dop.sort_values("timestamp").iloc[-1].to_dict()
        st.caption(f"Último registro en operación: {ult['timestamp']} ({ult['Origen']}). Horas acumuladas: {fmt(ult.get('horas_trabajo_acum_h'), 0)} h.")
        tarjetas_estado(ult)
        diags = N.diagnosticar(ult, equipo)
        if mant_venc:
            diags.append({"Falla": f"Mantenimiento vencido ({len(mant_venc)})", "Gravedad": 1, "Evidencia": "; ".join(t["Tarea"] for t in mant_venc[:3]),
                          "Causas": ["Tareas preventivas no registradas a tiempo"], "Acciones": ["Revisar «🛠️ Mantenimiento»"]})
        if diags:
            st.markdown(f"**{len(diags)} hallazgo(s) en el último registro.** El más importante:")
            tarjetas_diagnostico(diags[:1])
        else:
            st.success("El último registro no presenta fallas.")
        c = st.columns([3, 2])
        serie = muestra(dop.sort_values("timestamp"), 900).assign(Fecha=lambda x: pd.to_datetime(x["timestamp"]))
        c[0].markdown("**Temperatura IR del escudo y estado de falla**")
        c[0].altair_chart(alt.Chart(serie).mark_circle(size=14).encode(
            x=alt.X("Fecha:T", title=None), y=alt.Y("T_F:Q", title="°F", scale=alt.Scale(zero=False)),
            color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado"), tooltip=["timestamp", alt.Tooltip("T_F:Q", format=".1f"), "estado_txt"]
        ).properties(height=300), width="stretch")
        cuenta = d["estado_txt"].value_counts().reset_index()
        cuenta.columns = ["Estado", "Horas"]
        c[1].markdown("**Horas por estado**")
        c[1].altair_chart(alt.Chart(cuenta).mark_bar().encode(
            x="Horas:Q", y=alt.Y("Estado:N", sort="-x", title=None), color=alt.Color("Estado:N", scale=ESCALA_EST, legend=None),
            tooltip=["Estado", "Horas"]).properties(height=300), width="stretch")
        ok = tabla_ir[tabla_ir["Cumple todo"]] if len(tabla_ir) else tabla_ir
        if len(ok):
            st.info(f"Transmisor IR recomendado según los criterios del docente: **{ok.iloc[0]['Marca']} {ok.iloc[0]['Modelo']}** (ver «🌡️ Transmisor IR»).")

# =============================================================================
# ➕ Registrar
# =============================================================================
CAMPOS_REG = [  # (clave, etiqueta, paso)
    ("horas_trabajo_acum_h", "Horas de trabajo acumuladas (h)", 1.0), ("nivel_tanque_mm", "Nivel del tanque (mm)", 1.0),
    ("caudal_L_h", "Caudal (L/h)", 10.0), ("presion_succion_PSI", "Presión de succión (psi, negativa si hay vacío)", 0.1),
    ("presion_descarga_PSI", "Presión de descarga (psi)", 0.1), ("vibracion_succion_mm_s", "Vibración en succión (mm/s RMS)", 0.01),
    ("vibracion_descarga_mm_s", "Vibración en descarga (mm/s RMS)", 0.01), ("temperatura_motor_C", "Temperatura IR del escudo", 0.1),
    ("V_L1L2_V", "Voltaje L1-L2 (V)", 0.1), ("V_L2L3_V", "Voltaje L2-L3 (V)", 0.1), ("V_L3L1_V", "Voltaje L3-L1 (V)", 0.1),
    ("I_L1_A", "Corriente L1 (A)", 0.01), ("I_L2_A", "Corriente L2 (A)", 0.01), ("I_L3_A", "Corriente L3 (A)", 0.01),
    ("potencia_activa_kW", "Potencia activa (kW)", 0.001), ("potencia_reactiva_kVAr", "Potencia reactiva (kVAr)", 0.001),
]

if nav == "➕ Registrar":
    st.subheader("Registrar una medición")
    st.write("Solo se piden las variables que tiene la data del ingeniero. Caudal en GPM, altura, NPSH (con la presión de "
             "Latacunga), potencia aparente, factor de potencia, desbalances, **estado de falla y vida remanente (RUL)** se calculan solos.")
    for k, *_ in CAMPOS_REG:
        st.session_state.setdefault(f"r_{k}", None)
    if st.session_state.pop("limpiar_reg", False):
        for k, *_ in CAMPOS_REG:
            st.session_state[f"r_{k}"] = None
    with st.expander("¿No tienes una medición a mano? Carga un ejemplo real de la data del ingeniero"):
        c = st.columns([2, 1])
        est_ej = c[0].selectbox("Estado del ejemplo", [e for e in N.ESTADOS if e not in ("DETENIDA", "MANTENIMIENTO")], format_func=lambda e: N.NOMBRE_ESTADO[e])
        if c[1].button("Cargar ejemplo", width="stretch"):
            fila = dbase[(dbase["estado_falla"] == est_ej) & (dbase["estado_bomba"] == 1)].sample(1).iloc[0]
            for k, *_ in CAMPOS_REG:
                st.session_state[f"r_{k}"] = float(fila[k])
            st.session_state["r_ejemplo"] = f"Ejemplo tomado del registro {fila['timestamp']} ({N.NOMBRE_ESTADO[est_ej]})"
    if st.session_state.get("r_ejemplo"):
        st.caption(st.session_state["r_ejemplo"])
    u_t = st.radio("Unidad de la temperatura", ["°C", "°F"], horizontal=True)
    nombres = [o["Nombre"] for o in equipo.get("operadores", []) if o.get("Nombre")]
    with st.form("form_reg"):
        c = st.columns(4)
        fecha = c[0].date_input("Fecha", value=datetime.now().date())
        hora = c[1].time_input("Hora", value=datetime.now().time().replace(second=0, microsecond=0))
        estado_b = c[2].selectbox("Estado de la bomba", ["Operando", "Detenida"])
        operador = c[3].selectbox("Operador", nombres or ["—"])
        bloques = [("Proceso", CAMPOS_REG[0:5]), ("Vibración y temperatura", CAMPOS_REG[5:8]), ("Eléctricas", CAMPOS_REG[8:16])]
        for titulo, campos in bloques:
            st.markdown(f"**{titulo}**")
            cols = st.columns(4)
            for j, (k, etq, paso) in enumerate(campos):
                cols[j % 4].number_input(etq + (f" ({u_t})" if k == "temperatura_motor_C" else ""), step=paso, key=f"r_{k}", format="%.3f" if paso < 0.01 else None)
        obs = st.text_input("Observaciones")
        enviar = st.form_submit_button("Guardar medición", type="primary")
    if enviar:
        vals = {k: st.session_state.get(f"r_{k}") for k, *_ in CAMPOS_REG}
        if vals["temperatura_motor_C"] is not None and u_t == "°F":
            vals["temperatura_motor_C"] = N.f_a_c(vals["temperatura_motor_C"])
        if estado_b == "Operando" and vals["temperatura_motor_C"] is None:
            st.error("Falta la temperatura IR: es la variable principal del proyecto.")
        else:
            fila = {"ID": np.nan, "timestamp": f"{fecha} {hora.strftime('%H:%M')}:00", "Origen": N.ORIGEN_NUEVO,
                    "Operador": "" if operador == "—" else operador, "Observaciones": obs,
                    "estado_bomba": 1 if estado_b == "Operando" else 0, **{k: (np.nan if v is None else float(v)) for k, v in vals.items()}}
            guardado = N.guardar_registros(pd.concat([reg, pd.DataFrame([fila])], ignore_index=True))
            nuevo = N.completar_estado(N.derivar(guardado.tail(1), equipo), modelos).iloc[0].to_dict()
            diags = N.diagnosticar(nuevo, equipo)
            st.session_state["res_reg"] = {"fila": {k: nuevo.get(k) for k in ("estado", "fuente_estado", "RUL_h", "T_F", "temperatura_motor_C",
                                                                              "margen_NPSH_m", "margen_lat_m", "Vib_max", "zona_vib", "carga_pct",
                                                                              "zona_carga", "I_prom_A", "zona_T")}, "diags": diags}
            if alertas_cfg.get("activo") and diags and max(x["Gravedad"] for x in diags) >= int(alertas_cfg.get("nivel_min", 1)):
                ok_, det_ = N.telegram_enviar(N.mensaje_alerta(nuevo, diags), alertas_cfg)
                N.registrar_alerta(alertas_cfg, "Medición", "; ".join(x["Falla"] for x in diags[:3]), ok_, det_)
                st.session_state["res_reg"]["envio"] = (ok_, det_)
            st.session_state["limpiar_reg"] = True
            st.session_state.pop("r_ejemplo", None)
            st.session_state["msg"] = "Medición guardada"
            st.rerun()
    res = st.session_state.pop("res_reg", None)
    if res:
        st.markdown("**Resultado de la medición guardada**")
        tarjetas_estado(res["fila"])
        if res["diags"]:
            tarjetas_diagnostico(res["diags"])
        else:
            st.success("Sin fallas detectadas.")
        if res.get("envio"):
            (st.success if res["envio"][0] else st.error)("Alerta enviada por Telegram." if res["envio"][0] else f"No se pudo enviar: {res['envio'][1]}")

# =============================================================================
# 🩺 Diagnóstico
# =============================================================================
if nav == "🩺 Diagnóstico":
    st.subheader("Diagnóstico automático y soluciones")
    if d.empty:
        st.info("No hay datos en el conjunto seleccionado.")
    else:
        c = st.columns([2, 3])
        estados_f = c[0].multiselect("Filtrar por estado", N.ESTADOS, default=[], format_func=lambda e: N.NOMBRE_ESTADO[e])
        dd = d[d["estado"].isin(estados_f)] if estados_f else d
        dd = dd.sort_values("timestamp")
        if dd.empty:
            st.info("No hay registros con ese estado.")
        else:
            opciones = list(dd.index[::-1][:800])
            sel = c[1].selectbox("Registro", opciones, format_func=lambda i: f"{d.at[i, 'timestamp']} | {d.at[i, 'estado_txt']} | {d.at[i, 'Origen']}")
            f = d.loc[sel].to_dict()
            st.markdown(f"Estado: {chip(f['estado'])} &nbsp; <span style='color:#5A6B88'>{html.escape(str(f.get('fuente_estado', '')))}</span>", unsafe_allow_html=True)
            tarjetas_estado(f)
            diags = N.diagnosticar(f, equipo)
            if diags:
                tarjetas_diagnostico(diags)
            else:
                st.success("Sin fallas detectadas en este registro.")
        st.subheader("Resumen del conjunto de datos")
        t = d["estado"].value_counts().reindex(N.ESTADOS).fillna(0).astype(int).reset_index()
        t.columns = ["estado", "Horas"]
        t["Estado"] = t["estado"].map(N.NOMBRE_ESTADO)
        t["% del tiempo"] = (t["Horas"] / max(len(d), 1) * 100).round(1)
        t["Solución principal"] = t["estado"].map(lambda e: N.SOLUCIONES.get(e, {}).get("acciones", ["Continuar monitoreo"])[0])
        st.dataframe(t[["Estado", "Horas", "% del tiempo", "Solución principal"]], hide_index=True, width="stretch")

# =============================================================================
# ⚙️ Rodamientos
# =============================================================================
if nav == "⚙️ Rodamientos":
    st.subheader("Análisis de vibraciones en rodamientos")
    st.caption("Réplica automatizada de la hoja PRINCIPAL de la tabla del docente. Selecciona el rodamiento y coloca los datos del motor: el resto se calcula solo.")
    ult_op = dbase[dbase["estado_bomba"] == 1].iloc[-1]
    c = st.columns(3)
    with c[0]:
        st.markdown('<div class="caja"><h4>Datos de entrada</h4>', unsafe_allow_html=True)
        rod = st.selectbox("Rodamiento", list(N.BD_RODAMIENTOS), index=list(N.BD_RODAMIENTOS).index(equipo["rod_DE"]))
        polos = st.selectbox("Polos del motor", [2, 4, 6], index=[2, 4, 6].index(int(equipo["motor_polos"])))
        hz_vfd = st.number_input("Frecuencia del variador (Hz)", value=float(equipo["motor_f"]), step=0.1)
        rpm_placa = st.number_input("RPM de placa", value=float(equipo["motor_rpm"]), step=5.0)
        hz_placa = st.number_input("Frecuencia de placa asumida (Hz)", value=float(equipo["motor_f"]), step=1.0)
        cc = st.columns(2)
        punto = cc[0].selectbox("Punto", ["DE", "NDE"])
        direc = cc[1].selectbox("Dirección", ["Horizontal", "Vertical", "Axial"])
        st.selectbox("Modo IRD", ["mm/s RMS", "g Aceleración", "Hz"])
        vib = st.number_input("Vibración (mm/s RMS)", value=round(float(ult_op["vibracion_descarga_mm_s"]), 2), step=0.01,
                              help="Por defecto, la última vibración de descarga de la data del ingeniero")
        acel = st.number_input("Aceleración (g)", value=None, step=0.001, format="%.3f")
        pico = st.number_input("Pico medido (Hz)", value=None, step=0.1)
        fecha_m = st.date_input("Fecha de medición", value=datetime.now().date())
        st.markdown("</div>", unsafe_allow_html=True)
    with st.expander("Umbrales didácticos (editables)"):
        cu = st.columns(3)
        u_mm = tuple(cu[0].number_input(f"mm/s {n}", value=v, step=0.1, key=f"umm{n}") for n, v in zip(("normal", "atención", "alarma"), N.UMBRALES_ROD["mm_s"]))
        u_g = tuple(cu[1].number_input(f"g {n}", value=v, step=0.01, key=f"ug{n}") for n, v in zip(("bajo", "vigilar", "alerta"), N.UMBRALES_ROD["g"]))
        u_c = tuple(cu[2].number_input(f"Coincidencia {n} (%)", value=v * 100, step=0.5, key=f"uc{n}") / 100 for n, v in zip(("fuerte", "posible"), N.UMBRALES_ROD["coinc"]))
    a = N.analisis_rodamiento(rod, polos, hz_vfd, rpm_placa, hz_placa, vib, acel, pico, {"mm_s": u_mm, "g": u_g, "coinc": u_c})
    with c[1]:
        st.markdown('<div class="caja"><h4>Cálculos del motor</h4>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([("RPM síncronas a la frecuencia del variador", a["rpm_sinc"]), ("RPM estimadas reales", a["rpm"]),
                                   ("Frecuencia de giro fr (Hz)", a["fr"])] + list(a["armonicos"].items()), columns=["Cálculo", "Valor"]).round(2),
                     hide_index=True, width="stretch")
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown('<div class="caja"><h4>Datos automáticos del rodamiento</h4>', unsafe_allow_html=True)
        g_ = a["geom"]
        st.dataframe(pd.DataFrame([("Elementos rodantes", g_["n"]), ("Diámetro de bola (mm)", g_["d"]), ("Diámetro de paso (mm)", g_["D"]),
                                   ("Ángulo de contacto (°)", g_["alfa"])], columns=["Dato", "Valor"]), hide_index=True, width="stretch")
        st.caption("Valor de referencia; verificar con el fabricante.")
        st.markdown("</div>", unsafe_allow_html=True)
    with c[2]:
        col_d = {"🔴": "#D64545", "🟠": "#F28C28", "🟡": "#F2B705", "🟢": "#2E9E5B"}.get(a["diagnostico"][:1], "#8A9BB8")
        st.markdown(f"""<div class="caja"><h4>Diagnóstico automático</h4>
<p>Estado mm/s: <b>{a['estado_v']}</b><br>Estado g: <b>{a['estado_g']}</b><br>Mejor coincidencia: <b>{html.escape(a['mejor'])}</b><br>
Desviación mínima: <b>{fmt(a['dev_min'] * 100 if a['dev_min'] is not None else None)} %</b></p>
<div class="chip" style="background:{col_d};font-size:1rem">{html.escape(a['diagnostico'])}</div>
<p style="margin-top:.6rem"><b>Recomendación:</b> {html.escape(a['recomendacion'])}</p>
<p style="font-size:.8rem;color:#5A6B88">La frecuencia identifica una posible fuente; confirme con tendencia, armónicos, bandas laterales y condiciones de montaje/lubricación.</p></div>""",
                    unsafe_allow_html=True)
    st.markdown("**Frecuencias características del rodamiento**")
    tf = a["tabla"].copy()
    tf["Desviación"] = tf["Desviación"].map(lambda x: "" if x is None or pd.isna(x) else f"{x * 100:.1f} %")
    st.dataframe(tf.round(3), hide_index=True, width="stretch")
    barras = alt.Chart(pd.DataFrame({"Frecuencia": list(a["armonicos"]) + list(tf["Falla"]),
                                     "Hz": list(a["armonicos"].values()) + list(a["tabla"]["Frecuencia (Hz)"])})).mark_bar(color="#1F6FEB").encode(
        x="Hz:Q", y=alt.Y("Frecuencia:N", sort=None, title=None), tooltip=[alt.Tooltip("Hz:Q", format=".2f")])
    if pico:
        barras = barras + alt.Chart(pd.DataFrame({"x": [pico]})).mark_rule(color="#D64545", strokeWidth=3).encode(x="x:Q")
    st.altair_chart(barras.properties(height=240), width="stretch")
    st.markdown("**Semáforo de vibración (guía didáctica)**")
    st.dataframe(pd.DataFrame({"Parámetro": ["mm/s RMS", "g aceleración", "Pico vs falla"],
                               "🟢 Normal": [f"≤ {u_mm[0]}", f"≤ {u_g[0]}", f"> {u_c[1] * 100:.0f} %"],
                               "🟡 Atención": [f"{u_mm[0]}–{u_mm[1]}", f"{u_g[0]}–{u_g[1]}", f"{u_c[0] * 100:.0f}–{u_c[1] * 100:.0f} %"],
                               "🟠 Alarma": [f"{u_mm[1]}–{u_mm[2]}", f"{u_g[1]}–{u_g[2]}", f"≤ {u_c[0] * 100:.0f} %"],
                               "🔴 Crítico": [f"> {u_mm[2]}", f"> {u_g[2]}", "Confirmar + tendencia"]}), hide_index=True, width="stretch")
    c = st.columns([1, 3])
    if c[0].button("💾 Guardar en historial", type="primary"):
        hist_rod["filas"] = hist_rod.get("filas", []) + [{
            "Fecha": str(fecha_m), "Rodamiento": rod, "Punto": punto, "Dirección": direc, "Polos": polos, "Hz VFD": hz_vfd,
            "RPM placa": rpm_placa, "RPM estimadas": round(a["rpm"], 1), "mm/s": vib, "g": acel, "Pico Hz": pico,
            "Falla más cercana": a["mejor"], "Desviación %": round(a["dev_min"] * 100, 2) if a["dev_min"] is not None else None,
            "Diagnóstico": a["diagnostico"]}]
        N.guardar_json(N.ARCH_HIST_ROD, hist_rod)
        st.session_state["msg"] = "Medición guardada en el historial"
        st.rerun()
    c[1].caption("En Excel había que copiar y pegar la fila en HISTORIAL; aquí se guarda con un clic.")
    if hist_rod.get("filas"):
        h = pd.DataFrame(hist_rod["filas"])
        st.markdown("**Historial**")
        st.dataframe(h, hide_index=True, width="stretch")
        h["Serie"] = h["Rodamiento"] + " " + h["Punto"] + " " + h["Dirección"]
        st.altair_chart(alt.Chart(h).mark_line(point=True).encode(x=alt.X("Fecha:T"), y=alt.Y("mm/s:Q"), color=alt.Color("Serie:N", scale=alt.Scale(range=PALETA)),
                                                                  tooltip=list(h.columns)).properties(height=240), width="stretch")
    with st.expander("Correcciones respecto a las hojas ORIGINAL_6203 y ORIGINAL_6202 del Excel"):
        st.markdown("- **FTF:** la hoja usaba `COS(ángulo)` sin convertir a radianes; aquí se usa `COS(RADIANES(ángulo))`.\n"
                    "- **BSF y BPFI:** las celdas de factor estaban intercambiadas; aquí cada frecuencia usa su fórmula.\n"
                    "- **4× RPM (hoja 6202):** apuntaba a una celda vacía; aquí se calcula como 4·fr.\n"
                    "- La hoja **PRINCIPAL** estaba correcta y es la que se replica. Sus valores por defecto (2 polos con 1720 rpm) no eran "
                    "coherentes: 1720 rpm corresponde a 4 polos. Aquí se usan los datos del motor real (2 polos, 3450 rpm).")

# =============================================================================
# 💧 Cavitación
# =============================================================================
if nav == "💧 Cavitación":
    st.subheader("Diagnóstico automático de cavitación – bomba centrífuga")
    st.caption("Réplica automatizada de la hoja CAVITACION del docente (Sánchez, Carvajal, Poalacin y Salazar).")
    ult_op = dbase[dbase["estado_bomba"] == 1].iloc[-1]
    c = st.columns(3)
    with c[0]:
        st.markdown('<div class="caja"><h4>1. Datos de placa / operación</h4>', unsafe_allow_html=True)
        hp = st.number_input("Potencia del motor (HP)", value=float(equipo["motor_hp"]), step=0.25)
        hz_p = st.number_input("Frecuencia de placa (Hz)", value=60.0, step=1.0)
        rpm_p = st.number_input("RPM de placa", value=float(equipo["motor_rpm"]), step=5.0)
        hz_o = st.number_input("Frecuencia real de operación / VFD (Hz)", value=60.0, step=0.1)
        z = st.number_input("Número de álabes del impulsor Z", value=int(equipo.get("bomba_alabes") or 8), min_value=1, step=1,
                            help="Confirmar con el impulsor de la Goulds 3642")
        fund = st.selectbox("Tipo de fundación", ["RÍGIDA", "BLANDA"])
        rpm_r = st.number_input("RPM real medida (opcional)", value=None, step=1.0)
        st.markdown("</div>", unsafe_allow_html=True)
    with c[1]:
        st.markdown('<div class="caja"><h4>3. Mediciones del IRD</h4>', unsafe_allow_html=True)
        vg = st.number_input("Vibración global medida (mm/s RMS)", value=round(float(ult_op["vibracion_succion_mm_s"]), 2), step=0.01,
                             help="Por defecto, la última vibración en succión de la data del ingeniero")
        an = st.number_input("Amplitud en BPF – condición NORMAL (mm/s)", value=0.02, step=0.001, format="%.3f")
        aa = st.number_input("Amplitud en BPF – medición ACTUAL (mm/s)", value=0.004, step=0.001, format="%.3f")
        pk = st.number_input("Frecuencia del pico observado (Hz, opcional)", value=None, step=1.0)
        um = st.number_input("Umbral de aumento en BPF (%)", value=25.0, step=1.0, help="Criterio didáctico, no ISO")
        st.markdown("</div>", unsafe_allow_html=True)
    cav = N.analisis_cavitacion(hp, hz_p, rpm_p, hz_o, z, fund, rpm_r, vg, an, aa, pk, um)
    with c[2]:
        col = {"SIN INDICIOS CLAROS DE CAVITACIÓN": "#2E9E5B", "POSIBLE CAVITACIÓN – VIGILAR": "#F2B705", "CAVITACIÓN PROBABLE": "#F28C28",
               "CAVITACIÓN SEVERA / INSPECCIONAR": "#D64545"}.get(cav["diagnostico"], "#5B8DEF")
        col_e = {"BUENO": "#2E9E5B", "SATISFACTORIO": "#F2B705", "INSATISFACTORIO": "#F28C28", "INACEPTABLE": "#D64545"}.get(cav["estado"], "#8A9BB8")
        st.markdown(f"""<div class="caja"><h4>2. Referencias calculadas</h4>
RPM de operación: <b>{fmt(cav['rpm'], 0)}</b><br>Frecuencia 1×: <b>{fmt(cav['fr'], 2)} Hz</b> | 2×: <b>{fmt(cav['f2'], 2)} Hz</b><br>
Frecuencia de paso de álabes <b>BPF = {fmt(cav['bpf'], 2)} Hz</b><br>Clase de máquina: <b>{cav['clase']}</b><br>
Límites: bueno ≤ {cav['lim'][0]}, satisfactorio ≤ {cav['lim'][1]}, insatisfactorio ≤ {cav['lim'][2]} mm/s</div>
<div class="caja"><h4>4–5. Semáforo y diagnóstico</h4>Estado global: <span class="chip" style="background:{col_e}">{cav['estado']}</span><br><br>
Aumento en BPF: <b>{cav['aumento_txt']}</b><br>Coincidencia del pico: <b>{cav['coincidencia']}</b><br><br>
<div class="chip" style="background:{col};font-size:1rem">{cav['diagnostico']}</div></div>""", unsafe_allow_html=True)
    st.caption("Los datos de placa permiten calcular la frecuencia de referencia (BPF), pero no confirman por sí solos que exista cavitación: "
               "se necesita al menos una medición real de vibración. El umbral del 25 % es un criterio didáctico interno.")
    st.subheader("Margen NPSH: data del ingeniero vs presión real de Latacunga")
    patm = N.p_atm_kpa(equipo)
    op_b = dbase[dbase["estado_bomba"] == 1].copy()
    op_b["Estado en Latacunga"] = [N.NOMBRE_ESTADO[N.estado_por_reglas(m, h, True)] for m, h in zip(op_b["margen_lat_m"], op_b["health_index_rodamiento"])]
    cambian = int((op_b["Estado en Latacunga"] != op_b["estado_txt"]).sum())
    tarjetas_semaforo([("Presión atmosférica de la data", "101,3 kPa", None, "nivel del mar", "#5B8DEF"),
                       ("Presión en Latacunga", f"{fmt(patm)} kPa", None, f"{fmt(equipo['altitud_m'], 0)} m s.n.m.", "#0D3B8C"),
                       ("Pérdida de NPSH disponible", f"{fmt((op_b['margen_mar_m'] - op_b['margen_lat_m']).mean(), 2)} m", 1, "por la altitud"),
                       ("Horas que cambiarían de estado", str(cambian), 2 if cambian else 0, f"de {len(op_b)} en operación")])
    st.dataframe(pd.crosstab(op_b["estado_txt"], op_b["Estado en Latacunga"]).rename_axis(index="Estado en la data (nivel del mar)"), width="stretch")
    m = muestra(op_b, 800)
    ch = alt.Chart(m).mark_circle(size=16, opacity=.5).encode(x=alt.X("caudal_GPM:Q", title="Caudal (GPM)", scale=alt.Scale(zero=False)))
    capa = (ch.encode(y=alt.Y("NPSHa_m:Q", title="NPSH (m)"), color=alt.value("#1F6FEB"))
            + ch.encode(y="NPSHa_lat_m:Q", color=alt.value("#F28C28"))
            + alt.Chart(N.CURVA[N.CURVA["Q_gpm"].between(20, 40)]).mark_line(color="#D64545", strokeWidth=3).encode(x="Q_gpm:Q", y="NPSHr_m:Q"))
    st.altair_chart(capa.properties(height=320), width="stretch")
    texto_tarjeta("NPSH disponible de la data del ingeniero (azul, nivel del mar) y el mismo cálculo con la presión de Latacunga (naranja), "
                  "frente al NPSH requerido del fabricante (rojo).",
                  "Mientras los puntos estén sobre la línea roja con margen, no hay cavitación. La altitud baja todos los puntos casi 3 m.",
                  f"Con la presión de Latacunga, {cambian} horas de operación cambiarían de estado. Las mediciones nuevas de esta app ya "
                  "usan la presión local; la data del ingeniero se conserva como viene para respetar sus etiquetas.")

# =============================================================================
# 🧠 Estado y RUL
# =============================================================================
if nav == "🧠 Estado y RUL":
    st.subheader("Estado de falla y vida remanente (RUL) del rodamiento")
    st.markdown("**Reglas del estado de falla** (reconstruidas por el docente con un árbol de decisión; concordancia del 100 % con la data)")
    st.dataframe(pd.DataFrame([
        ("Bomba detenida", "Detenida (o Mantenimiento tras el cambio de rodamiento)"),
        (f"Margen NPSH ≤ {N.REGLAS['margen_severa']} m e índice de salud ≤ {N.REGLAS['hi_degradacion']}", "Falla combinada"),
        (f"Margen NPSH ≤ {N.REGLAS['margen_severa']} m", "Cavitación severa"),
        (f"Índice de salud ≤ {N.REGLAS['hi_critico']}", "Rodamiento crítico"),
        (f"Margen NPSH ≤ {N.REGLAS['margen_incipiente']} m", "Cavitación incipiente"),
        (f"Índice de salud ≤ {N.REGLAS['hi_degradacion']}", "Degradación de rodamiento"),
        ("Ninguna de las anteriores", "Normal")], columns=["Condición (en este orden)", "Estado"]), hide_index=True, width="stretch")
    st.caption("El margen NPSH y el índice de salud no se miden directamente en planta. Por eso, para los registros nuevos el estado lo "
               "predice una red neuronal MLP con 19 variables medibles, y la cavitación se confirma con el margen NPSH calculado en Latacunga.")
    tl = muestra(dbase.sort_values("timestamp"), 1500).assign(Fecha=lambda x: pd.to_datetime(x["timestamp"]))
    st.markdown("**Línea de tiempo de la data del ingeniero**")
    st.altair_chart(alt.Chart(tl).mark_tick(thickness=2).encode(x=alt.X("Fecha:T", title=None), y=alt.Y("estado_txt:N", sort=DOM_EST, title=None),
                                                                color=alt.Color("estado_txt:N", scale=ESCALA_EST, legend=None)).properties(height=230), width="stretch")
    hi = dbase[dbase["estado_bomba"] == 1][["horas_trabajo_acum_h", "health_index_rodamiento", "RUL_rodamiento_h"]]
    c = st.columns(2)
    c[0].altair_chart(alt.Chart(muestra(hi, 800)).mark_line(color="#0D3B8C").encode(
        x=alt.X("horas_trabajo_acum_h:Q", title="Horas de operación"), y=alt.Y("health_index_rodamiento:Q", title="Índice de salud")).properties(height=230), width="stretch")
    cr = modelos["curva_rul"].melt("horas", var_name="Serie", value_name="RUL (h)")
    c[1].altair_chart(alt.Chart(muestra(cr, 1200)).mark_line().encode(
        x=alt.X("horas:Q", title="Horas de operación"), y="RUL (h):Q", color=alt.Color("Serie:N", scale=alt.Scale(range=["#1F6FEB", "#F28C28"]))).properties(height=230), width="stretch")
    texto_tarjeta("Izquierda: índice de salud del rodamiento original. Derecha: RUL real (recortado a 800 h) y el estimado por la red MLP.",
                  "El índice empieza a bajar unas 800–900 h antes de la falla; mientras el rodamiento está sano, el RUL no es observable desde los "
                  "sensores y solo se puede decir «800 h o más».",
                  f"La red MLP estima el RUL con un error medio de {fmt(modelos['mae'])} h (R² = {fmt(modelos['r2'], 3)}) en datos de prueba.")
    st.subheader("Red neuronal MLP entrenada en la aplicación")
    rep = pd.DataFrame(modelos["reporte"]).T.drop(index=["accuracy"], errors="ignore")
    rep = rep[rep.index.isin(modelos["clases"])].rename(index=N.NOMBRE_ESTADO)
    c = st.columns([2, 3])
    c[0].dataframe(rep.rename(columns={"precision": "Precisión", "recall": "Sensibilidad", "f1-score": "F1", "support": "Casos"}).round(3), width="stretch")
    cm = pd.DataFrame(modelos["matriz"], index=[N.NOMBRE_ESTADO[x] for x in modelos["clases"]], columns=[N.NOMBRE_ESTADO[x] for x in modelos["clases"]])
    cml = cm.rename_axis("Real").reset_index().melt("Real", var_name="Predicho", value_name="n")
    bm = alt.Chart(cml).encode(x=alt.X("Predicho:N", sort=None), y=alt.Y("Real:N", sort=None))
    c[1].altair_chart((bm.mark_rect().encode(color=alt.Color("n:Q", scale=alt.Scale(scheme="blues"), legend=None))
                       + bm.mark_text().encode(text="n:Q")).properties(height=280), width="stretch")
    st.markdown("**Comparación con el cuaderno Colab del docente**")
    st.dataframe(pd.DataFrame([
        ("MLP (Colab, TensorFlow)", 0.966, 15.4, 0.962), ("LSTM (Colab, TensorFlow)", 0.646, 6.9, 0.993),
        ("MLP (esta aplicación, scikit-learn)", round(modelos["f1"], 3), round(modelos["mae"], 1), round(modelos["r2"], 3))],
        columns=["Modelo", "F1 macro (estado)", "MAE RUL (h)", "R² RUL"]), hide_index=True, width="stretch")
    with st.expander("Lectura crítica de las métricas (del cuaderno del docente)"):
        st.markdown("- **Un solo ciclo de falla:** la data tiene una única degradación hasta la falla; las métricas de RUL son optimistas.\n"
                    "- **RUL sintético determinista:** RUL = 2725 − horas; por eso no se usan las horas como entrada.\n"
                    "- **Clases pequeñas:** cavitación incipiente (24 h), falla combinada (8 h) y mantenimiento (12 h) dan métricas inestables.\n"
                    "- **NPSHa calculado a baja altitud:** para el banco real hay que recalcularlo con la presión de Latacunga (ver «💧 Cavitación»).")

# =============================================================================
# 🛠️ Mantenimiento
# =============================================================================
if nav == "🛠️ Mantenimiento":
    st.subheader("Mantenimiento predictivo y preventivo")
    if len(dop):
        u = dop.sort_values("timestamp").iloc[-1]
        rul = u.get("RUL_h")
        horas_dia = (dbase["estado_bomba"] == 1).sum() / max(pd.to_datetime(dbase["timestamp"]).dt.date.nunique(), 1)
        dias = rul / horas_dia if rul is not None and not pd.isna(rul) else None
        tarjetas_semaforo([
            ("Vida remanente del rodamiento", f"{fmt(rul, 0)} h" if dias is not None else "—",
             None if dias is None else 2 if rul <= equipo["rul_aviso_h"] / 4 else 1 if rul <= equipo["rul_aviso_h"] else 0, f"≈ {fmt(dias, 0)} días a {fmt(horas_dia, 0)} h/día"),
            ("Horas acumuladas (data)", f"{fmt(u['horas_trabajo_acum_h'], 0)} h", None, str(u["timestamp"]), "#0D3B8C"),
            ("Estado actual", N.NOMBRE_ESTADO.get(u["estado"], u["estado"]), None, "último registro en operación", N.COLOR_ESTADO.get(u["estado"]))])
        if rul is not None and not pd.isna(rul) and rul <= equipo["rul_aviso_h"]:
            st.warning(f"Programar el cambio de rodamiento ({equipo['rod_DE']} lado bomba / {equipo['rod_NDE']} lado ventilador) en los próximos {fmt(dias, 0)} días.")
        ev = dbase[dbase["evento_mantenimiento"].notna()][["timestamp", "horas_trabajo_acum_h", "evento_mantenimiento"]]
        if len(ev):
            st.caption("Eventos de la data del ingeniero: " + "; ".join(f"{r.timestamp} – {r.evento_mantenimiento} a las {r.horas_trabajo_acum_h:.0f} h" for r in ev.itertuples()))
    c = st.columns(3)
    c[0].metric("Horómetro registrado", f"{fmt(float(mant.get('horometro_h') or 0), 0)} h")
    c[1].metric("Tareas vencidas", int((mant_estado["nivel"] == 2).sum()))
    c[2].metric("Próximas a vencer", int((mant_estado["nivel"] == 1).sum()))
    if len(mant_estado):
        v = mant_estado.copy()
        v["Situación"] = v["nivel"].map({0: "🟢 Al día", 1: "🟡 Próxima", 2: "🔴 Vencida"})
        st.dataframe(v[["Situación", "Tarea", "Frecuencia", "Última vez", "Estado"]], hide_index=True, width="stretch")
    with st.form("form_mant", clear_on_submit=True):
        st.markdown("**Registrar un mantenimiento realizado**")
        c = st.columns([3, 1, 1])
        tarea = c[0].selectbox("Tarea", [t["Tarea"] for t in mant["tareas"]] + ["Cambio de rodamiento", "Otra (correctiva)"])
        fecha = c[1].date_input("Fecha", value=datetime.now().date())
        resp = c[2].selectbox("Responsable", [o["Nombre"] for o in equipo.get("operadores", []) if o.get("Nombre")] or ["—"])
        obs = st.text_input("Observaciones")
        if st.form_submit_button("Guardar mantenimiento", type="primary"):
            for t in mant["tareas"]:
                if t["Tarea"] == tarea:
                    t["Ultima_fecha"], t["Ultima_horas"] = str(fecha), float(mant.get("horometro_h") or 0)
            mant["historial"] = [{"Fecha": str(fecha), "Tarea": tarea, "Responsable": resp, "Horas": mant.get("horometro_h"), "Observaciones": obs}] + mant.get("historial", [])
            N.guardar_json(N.ARCH_MANT, mant)
            st.session_state["msg"] = "Mantenimiento registrado"
            st.rerun()
    c = st.columns([2, 1, 1])
    horo = c[0].number_input("Horómetro de la bomba (h)", value=float(mant.get("horometro_h") or 0), step=1.0)
    if c[1].button("Actualizar horómetro"):
        mant["horometro_h"] = horo
        N.guardar_json(N.ARCH_MANT, mant)
        st.rerun()
    if c[2].button("Tomar horas de la data"):
        mant["horometro_h"] = float(dbase["horas_trabajo_acum_h"].max())
        N.guardar_json(N.ARCH_MANT, mant)
        st.rerun()
    if mant.get("historial"):
        st.dataframe(pd.DataFrame(mant["historial"]), hide_index=True, width="stretch")

# =============================================================================
# 📊 Gráficas
# =============================================================================
if nav == "📊 Gráficas":
    st.subheader("Gráficas con interpretación")
    if dop.empty:
        st.info("No hay datos en operación en el conjunto seleccionado.")
    else:
        sec = st.radio("Sección", ["💧 Hidráulica", "🌡️ Térmico", "📳 Vibraciones", "⚡ Eléctrico", "🟥 Mapas de calor"], horizontal=True, label_visibility="collapsed")
        if len(dop) > 600:
            st.caption(f"Las gráficas de puntos muestran 600 de {len(dop)} registros en operación; los cálculos usan todos.")
        m = muestra(dop.sort_values("timestamp")).assign(Fecha=lambda x: pd.to_datetime(x["timestamp"]))
        if sec == "💧 Hidráulica":
            q = np.linspace(0, 80, 81)
            st.altair_chart((alt.Chart(pd.DataFrame({"Q": q, "H": N.h_ref(q)})).mark_line(color="#0A1F44", strokeWidth=3).encode(x=alt.X("Q:Q", title="Caudal (GPM)"), y=alt.Y("H:Q", title="Altura (m)", scale=alt.Scale(zero=False)))
                             + alt.Chart(m).mark_circle(size=25, opacity=.6).encode(x="caudal_GPM:Q", y="head_total_m:Q", color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado"))).properties(height=330), width="stretch")
            texto_tarjeta("Curva H–Q del fabricante (negra) y los puntos de operación de la data, coloreados por estado.",
                          "Los puntos sobre la curva indican desempeño normal; por debajo, pérdida de altura por desgaste o cavitación.",
                          f"Error de altura medio: {fmt(dop['E_H_pct'].mean())} %. Caudal entre {fmt(dop['caudal_GPM'].min())} y {fmt(dop['caudal_GPM'].max())} GPM.")
            st.altair_chart(alt.Chart(m).mark_circle(size=20).encode(x=alt.X("Fecha:T", title=None), y=alt.Y("margen_NPSH_m:Q", title="Margen NPSH (m)"),
                                                                     color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado")).properties(height=260)
                            + alt.Chart(pd.DataFrame({"y": [N.REGLAS["margen_incipiente"], N.REGLAS["margen_severa"]]})).mark_rule(strokeDash=[6, 4], color="#D64545").encode(y="y:Q"), width="stretch")
            texto_tarjeta("Margen NPSH (NPSHa − NPSHr) en el tiempo, con los umbrales del docente (0,82 m incipiente; 0,107 m severa).",
                          "Las caídas bruscas son los episodios de cavitación inducidos por nivel bajo o restricción en la succión.",
                          f"{int((dop['margen_NPSH_m'] <= N.REGLAS['margen_incipiente']).sum())} horas bajo 0,82 m.")
        if sec == "🌡️ Térmico":
            st.altair_chart(alt.Chart(m).mark_boxplot(extent="min-max").encode(x=alt.X("estado_txt:N", sort=DOM_EST, title=None), y=alt.Y("T_F:Q", title="Temperatura IR (°F)", scale=alt.Scale(zero=False)),
                                                                              color=alt.Color("estado_txt:N", scale=ESCALA_EST, legend=None)).properties(height=320), width="stretch")
            med = dop.groupby("estado_txt")["T_F"].median()
            texto_tarjeta("Distribución de la temperatura del escudo del rodamiento en cada estado de falla.",
                          "Si las cajas de los estados de rodamiento están más arriba que la de Normal, la temperatura es un buen indicador para el transmisor IR.",
                          " | ".join(f"{k}: {fmt(v)} °F" for k, v in med.items()))
            cuenta, bordes = np.histogram(dop["T_F"].dropna(), bins=30)
            hb = pd.DataFrame({"x0": bordes[:-1], "x1": bordes[1:], "n": cuenta})
            st.altair_chart((alt.Chart(hb).mark_rect(color="#1F6FEB").encode(x=alt.X("x0:Q", title="Temperatura IR (°F)", scale=alt.Scale(zero=False)), x2="x1:Q", y=alt.Y("n:Q", title="Horas"), y2=alt.datum(0))
                             + alt.Chart(pd.DataFrame({"x": [N.c_a_f(equipo["alarma_C"]), N.c_a_f(equipo["disparo_C"])]})).mark_rule(strokeDash=[6, 4], color="#D64545", strokeWidth=2).encode(x="x:Q")).properties(height=250), width="stretch")
            texto_tarjeta("Cuántas horas se midió cada temperatura, con la alarma y el disparo.", "Define el rango que debe cubrir el transmisor.",
                          f"Mínimo {fmt(dop['T_F'].min())} °F, máximo {fmt(dop['T_F'].max())} °F; percentil 95 {fmt(np.percentile(dop['T_F'].dropna(), 95))} °F.")
            sc = alt.Chart(m).mark_circle(size=20, opacity=.6).encode(x=alt.X("vibracion_descarga_mm_s:Q", title="Vibración en descarga (mm/s)"), y=alt.Y("T_F:Q", title="°F", scale=alt.Scale(zero=False)),
                                                                      color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado"))
            st.altair_chart((sc + sc.transform_regression("vibracion_descarga_mm_s", "T_F").mark_line(color="#0A1F44")).properties(height=280), width="stretch")
            r = dop["T_F"].corr(dop["vibracion_descarga_mm_s"])
            texto_tarjeta("Temperatura frente a vibración.", "Un rodamiento que se degrada vibra y se calienta a la vez.", f"Correlación r = {fmt(r, 2)}.")
        if sec == "📳 Vibraciones":
            lv = m.melt(id_vars=["Fecha", "estado_txt"], value_vars=["vibracion_succion_mm_s", "vibracion_descarga_mm_s"], var_name="Punto", value_name="mm/s")
            lv["Punto"] = lv["Punto"].map({"vibracion_succion_mm_s": "Succión", "vibracion_descarga_mm_s": "Descarga"})
            zonas = pd.DataFrame({"y0": [0, equipo["iso_A"], equipo["iso_B"], equipo["iso_C"]], "y1": [equipo["iso_A"], equipo["iso_B"], equipo["iso_C"], max(8, lv["mm/s"].max())], "Zona": list("ABCD")})
            st.altair_chart((alt.Chart(zonas).mark_rect(opacity=.13).encode(y="y0:Q", y2="y1:Q", color=alt.Color("Zona:N", scale=alt.Scale(range=["#2E9E5B", "#7BC67E", "#F2B705", "#D64545"])))
                             + alt.Chart(lv).mark_circle(size=12).encode(x=alt.X("Fecha:T", title=None), y=alt.Y("mm/s:Q"), shape="Punto:N", color=alt.value("#0A1F44"))).properties(height=320), width="stretch")
            texto_tarjeta("Vibración global en succión y descarga sobre las zonas ISO 10816 clase I.", "Zona C: investigar; zona D: riesgo de daño.",
                          f"{int((dop['zona_vib'] >= 1).sum())} horas en zona C o D. Para el espectro y las frecuencias de falla usa «⚙️ Rodamientos» y «💧 Cavitación».")
        if sec == "⚡ Eléctrico":
            st.altair_chart(alt.Chart(m).mark_circle(size=14).encode(x=alt.X("Fecha:T", title=None), y=alt.Y("carga_pct:Q", title="Carga (% I nominal)", scale=alt.Scale(zero=False)),
                                                                     color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado")).properties(height=260), width="stretch")
            texto_tarjeta("Corriente promedio como porcentaje de la nominal de placa (3,0 A a 230 V).", "Sobre 100 % el motor usa su factor de servicio.",
                          f"Carga media {fmt(dop['carga_pct'].mean(), 0)} %, máxima {fmt(dop['carga_pct'].max(), 0)} %. Desbalance de corriente medio {fmt(dop['desb_corriente_pct'].mean(), 2)} %; de tensión {fmt(dop['desb_tension_pct'].mean(), 2)} %.")
        if sec == "🟥 Mapas de calor":
            vars_c = ["T_F"] + [c for c in N.CANDIDATAS if dop[c].std() > 0]
            corr = dop[vars_c].astype(float).corr()
            mp = corr.rename_axis("V1").reset_index().melt("V1", var_name="V2", value_name="r")
            bc = alt.Chart(mp).encode(x=alt.X("V1:N", sort=None, title=None), y=alt.Y("V2:N", sort=None, title=None))
            st.altair_chart(bc.mark_rect().encode(color=alt.Color("r:Q", scale=alt.Scale(scheme="redblue", domain=[-1, 1])), tooltip=["V1", "V2", alt.Tooltip("r:Q", format=".2f")]).properties(height=26 * len(corr) + 40), width="stretch")
            top = corr["T_F"].drop("T_F").abs().sort_values(ascending=False).head(3)
            texto_tarjeta("Correlación entre todas las variables.", "Rojo/azul intenso: relación fuerte. Sirve para elegir las variables del modelo.",
                          "Más relacionadas con la temperatura: " + ", ".join(f"{N.ETIQUETAS.get(k, k)} (r = {fmt(corr.at[k, 'T_F'], 2)})" for k in top.index) + ".")
            opciones = [c for c in N.CANDIDATAS if dop[c].std() > 0]
            c = st.columns(2)
            vx = c[0].selectbox("Eje X", opciones, index=opciones.index("vibracion_descarga_mm_s"), format_func=lambda v: N.ETIQUETAS.get(v, v))
            vy = c[1].selectbox("Eje Y", opciones, index=opciones.index("horas_trabajo_acum_h"), format_func=lambda v: N.ETIQUETAS.get(v, v))
            dm = dop.dropna(subset=[vx, vy, "T_F"])
            cel = dm.groupby([pd.cut(dm[vx], 18), pd.cut(dm[vy], 18)], observed=True)["T_F"].agg(["mean", "count"]).reset_index()
            cel = pd.DataFrame({"x0": cel[vx].map(lambda i: i.left), "x1": cel[vx].map(lambda i: i.right), "y0": cel[vy].map(lambda i: i.left),
                                "y1": cel[vy].map(lambda i: i.right), "T": cel["mean"], "n": cel["count"]}).astype(float)
            st.altair_chart(alt.Chart(cel).mark_rect().encode(x=alt.X("x0:Q", title=N.ETIQUETAS.get(vx, vx), scale=alt.Scale(zero=False)), x2="x1:Q",
                                                              y=alt.Y("y0:Q", title=N.ETIQUETAS.get(vy, vy), scale=alt.Scale(zero=False)), y2="y1:Q",
                                                              color=alt.Color("T:Q", scale=alt.Scale(scheme="turbo"), title="T media (°F)"),
                                                              tooltip=[alt.Tooltip("T:Q", format=".1f"), "n:Q"]).properties(height=360), width="stretch")
            texto_tarjeta("Temperatura media del escudo en cada combinación de dos variables.", "Las celdas rojas son las condiciones que más calientan el rodamiento.",
                          f"La temperatura media va de {fmt(cel['T'].min())} a {fmt(cel['T'].max())} °F.")
            fechas = pd.to_datetime(d["timestamp"])
            meses = sorted(fechas.dt.to_period("M").astype(str).unique())
            mes = st.selectbox("Mes para el mapa de estado", meses, index=len(meses) - 1)
            de = d[fechas.dt.to_period("M").astype(str) == mes].assign(Dia=lambda x: pd.to_datetime(x["timestamp"]).dt.strftime("%Y-%m-%d"), Hora=lambda x: pd.to_datetime(x["timestamp"]).dt.hour)
            st.altair_chart(alt.Chart(de).mark_rect().encode(x=alt.X("Hora:O"), y=alt.Y("Dia:O", title=None), color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado"),
                                                             tooltip=["timestamp", "estado_txt"]).properties(height=14 * de["Dia"].nunique() + 40), width="stretch")
            texto_tarjeta("Estado de falla de cada hora del mes.", "Las franjas grises son las paradas nocturnas (23:00 a 04:59).",
                          ", ".join(f"{k}: {v} h" for k, v in de["estado_txt"].value_counts().items()) + ".")

# =============================================================================
# 🔍 Modelo de temperatura
# =============================================================================
if nav == "🔍 Modelo":
    st.subheader("Modelo de estimación de la temperatura del escudo (°F)")
    if len(dop) < 10:
        st.info("Se necesitan al menos 10 registros en operación.")
    else:
        num = dop[[c for c in N.CANDIDATAS if dop[c].std() > 0] + ["T_F"]].astype(float)
        corr = num.corr()
        rk = pd.DataFrame({"Variable": [c for c in num.columns if c != "T_F"]})
        rk["Descripción"] = rk["Variable"].map(lambda v: N.ETIQUETAS.get(v, v))
        rk["r"] = rk["Variable"].map(corr["T_F"])
        rk = rk.reindex(rk["r"].abs().sort_values(ascending=False).index).reset_index(drop=True)
        c = st.columns([3, 2])
        c[0].altair_chart(alt.Chart(rk).mark_bar().encode(x=alt.X("r:Q", scale=alt.Scale(domain=[-1, 1])), y=alt.Y("Descripción:N", sort="-x", title=None),
                                                         color=alt.condition(alt.datum.r > 0, alt.value("#1F6FEB"), alt.value("#D64545"))), width="stretch")
        c[1].dataframe(rk[["Variable", "r"]].round(3), hide_index=True, width="stretch")
        sug = []
        for v in rk["Variable"]:
            if v not in ("horas_trabajo_acum_h", "margen_NPSH_m") and all(abs(corr.at[v, u]) < 0.9 for u in sug):
                sug.append(v)
            if len(sug) == 3:
                break
        vars_x = st.multiselect("Variables del modelo", list(rk["Variable"]), default=sug, format_func=lambda v: f"{v} — {N.ETIQUETAS.get(v, v)}")
        if vars_x:
            dm = dop.dropna(subset=vars_x + ["T_F"]).sort_values("timestamp")
            corte = int(len(dm) * 0.7)
            res = []
            for nombre, terms in (("Lineal", vars_x), ("Polinómico 2º orden", vars_x + [f"{v}^2" for v in vars_x])):
                X = N.matriz_terminos(dm, terms)
                r = N.regresion(X.iloc[:corte].values, dm["T_F"].iloc[:corte].values)
                pred = np.column_stack([np.ones(len(dm)), X.values]) @ r["beta"]
                rv = math.sqrt(float(((dm["T_F"].values[corte:] - pred[corte:]) ** 2).mean()))
                res.append({"nombre": nombre, "terminos": terms, "reg": r, "pred": pred, "rmse_val": rv, "X": X})
            st.dataframe(pd.DataFrame([{"Modelo": x["nombre"], "R² ajuste": x["reg"]["r2"], "RMSE ajuste (°F)": x["reg"]["rmse"], "RMSE validación (°F)": x["rmse_val"]} for x in res]).round(3),
                         hide_index=True, width="stretch")
            el = st.radio("Modelo", [x["nombre"] for x in res], index=int(np.argmin([x["rmse_val"] for x in res])), horizontal=True)
            x = next(r for r in res if r["nombre"] == el)
            ecu = N.ecuacion_texto("T(°F)", float(x["reg"]["beta"][0]), x["reg"]["beta"][1:], x["terminos"])
            st.code(ecu, language=None)
            tc = pd.DataFrame({"Término": ["Intercepto"] + x["terminos"], "Coeficiente": x["reg"]["beta"], "p-valor": x["reg"]["p"],
                               "VIF": [np.nan] + N.vif(x["X"].iloc[:corte])})
            st.dataframe(tc.round(5), hide_index=True, width="stretch")
            cp = muestra(pd.DataFrame({"Medida": dm["T_F"].values, "Estimada": x["pred"], "Conjunto": ["Ajuste"] * corte + ["Validación"] * (len(dm) - corte)}))
            lo, hi = float(cp[["Medida", "Estimada"]].min().min()), float(cp[["Medida", "Estimada"]].max().max())
            st.altair_chart((alt.Chart(cp).mark_circle(size=25, opacity=.6).encode(x=alt.X("Medida:Q", scale=alt.Scale(domain=[lo, hi])), y=alt.Y("Estimada:Q", scale=alt.Scale(domain=[lo, hi])),
                                                                                   color=alt.Color("Conjunto:N", scale=alt.Scale(range=["#1F6FEB", "#F2B705"])))
                             + alt.Chart(pd.DataFrame({"a": [lo, hi]})).mark_line(color="gray", strokeDash=[5, 5]).encode(x="a:Q", y="a:Q")).properties(height=320), width="stretch")
            texto_tarjeta("Temperatura medida frente a la estimada por la ecuación.", "Un buen modelo deja los puntos sobre la diagonal.",
                          f"R² = {fmt(x['reg']['r2'], 3)}; error típico {fmt(x['reg']['rmse'], 2)} °F en ajuste y {fmt(x['rmse_val'], 2)} °F en validación (últimos 30 % de los datos).")
            if st.button("Guardar este modelo", type="primary"):
                N.guardar_json(N.ARCH_MODELO, {"nombre": el, "objetivo": "T_F", "variables": vars_x, "terminos": x["terminos"],
                                               "intercepto": float(x["reg"]["beta"][0]), "coeficientes": [float(b) for b in x["reg"]["beta"][1:]],
                                               "ecuacion": ecu, "r2": x["reg"]["r2"], "rmse_F": x["reg"]["rmse"], "rmse_validacion_F": x["rmse_val"],
                                               "n": len(dm), "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")})
                st.session_state["msg"] = "Modelo guardado"
                st.rerun()

# =============================================================================
# 🎯 Estimador
# =============================================================================
if nav == "🎯 Estimador":
    if not modelo_temp:
        st.info("Primero guarda un modelo en «🔍 Modelo».")
    else:
        st.subheader("Estimación de la temperatura del escudo")
        st.code(modelo_temp["ecuacion"], language=None)
        st.caption(f"{modelo_temp['nombre']} | R² = {fmt(modelo_temp['r2'], 3)} | RMSE = {fmt(modelo_temp['rmse_F'], 2)} °F | {modelo_temp['fecha']}")
        nec = []
        for v in modelo_temp["variables"]:
            for x in N.DEPENDE.get(v, [v]):
                if x not in nec:
                    nec.append(x)
        ent = {c: np.nan for c in N.COLS}
        ent.update({"timestamp": "", "Origen": N.ORIGEN_NUEVO, "Operador": "", "Observaciones": "", "estado_bomba": 1})
        ult = dop.sort_values("timestamp").iloc[-1] if len(dop) else dbase.iloc[-1]
        cols = st.columns(3)
        for i, v in enumerate(nec):
            ent[v] = cols[i % 3].number_input(N.ETIQUETAS.get(v, v), value=float(ult[v]), key=f"e_{v}")
        f = N.derivar(N.normalizar(pd.DataFrame([ent])), equipo)
        t = N.evaluar_modelo(modelo_temp, f)
        z = 0 if N.f_a_c(t) < equipo["alarma_C"] else 1 if N.f_a_c(t) < equipo["disparo_C"] else 2
        tarjetas_semaforo([("Temperatura estimada", f"{fmt(t)} °F", z, f"{fmt(N.f_a_c(t))} °C")])
        t_ir = st.number_input("Lectura del transmisor IR (°F), opcional", value=None, step=0.1)
        if t_ir is not None:
            dif = t_ir - t
            (st.warning if abs(dif) > 2 * modelo_temp["rmse_F"] else st.success)(
                f"Diferencia {dif:+.1f} °F. " + ("Revisa el sensor (emisividad, alineación) o el rodamiento." if abs(dif) > 2 * modelo_temp["rmse_F"] else "Medición coherente con el modelo."))

# =============================================================================
# 🌡️ Transmisor IR
# =============================================================================
if nav == "🌡️ Transmisor IR":
    st.subheader("1. Criterios de selección (informe técnico del docente)")
    with st.form("form_ir"):
        c = st.columns(4)
        e = {}
        e["ir_rango_max_C"] = c[0].number_input("Rango mínimo requerido hasta (°C)", value=float(equipo["ir_rango_max_C"]))
        e["ir_ds_min"] = c[1].number_input("Relación D:S mínima", value=float(equipo["ir_ds_min"]))
        e["ir_cabezal_min_C"] = c[2].number_input("T. ambiente mínima del cabezal (°C)", value=float(equipo["ir_cabezal_min_C"]))
        e["ir_resp_max_ms"] = c[3].number_input("Tiempo de respuesta máximo (ms)", value=float(equipo["ir_resp_max_ms"]))
        c = st.columns(4)
        e["ir_salida"] = c[0].selectbox("Salida", ["4–20 mA", "0–10 V"], index=["4–20 mA", "0–10 V"].index(equipo["ir_salida"]))
        e["ir_exactitud_C"] = c[1].number_input("Exactitud requerida (±°C)", value=float(equipo["ir_exactitud_C"]), step=0.5)
        e["ir_d_objetivo_mm"] = c[2].number_input("Diámetro útil de la tapa del rodamiento (mm)", value=float(equipo["ir_d_objetivo_mm"]))
        e["ir_distancia_mm"] = c[3].number_input("Distancia de montaje (mm)", value=float(equipo["ir_distancia_mm"]))
        if st.form_submit_button("Guardar criterios", type="primary"):
            N.guardar_json(N.ARCH_EQUIPO, {**equipo, **e})
            st.session_state["msg"] = "Criterios guardados"
            st.rerun()
    r = req_ir
    st.dataframe(pd.DataFrame([
        ("Rango", f"{fmt(r['rango_min_C'], 0)} a {fmt(r['rango_max_C'], 0)} °C", f"Máximo medido {fmt(r['t_max_obs_C'])} °C; el docente pide ~0–150 °C"),
        ("Relación D:S", f"≥ {fmt(r['ds_req'])} : 1", f"Criterio del docente (15:1 a 22:1) y geometría: punto ≤ {fmt(r['spot_max_mm'])} mm a {fmt(r['distancia_mm'], 0)} mm"),
        ("Cabezal", f"≥ {fmt(r['cabezal_C'], 0)} °C", "Temperatura ambiente junto al motor ODP"), ("Respuesta", f"≤ {fmt(r['resp_ms'], 0)} ms", "Más que suficiente para la degradación térmica"),
        ("Exactitud", f"±{fmt(r['exactitud_C'])} °C", "Menor que la separación entre estados normal y de degradación"),
        ("Salida", r["salida"], "4–20 mA con SM 1231 / SB 1231, o 0–10 V a la entrada integrada"), ("Emisividad", "Ajustable o fija 0,95", "Con cinta negra mate en el punto"),
        ("Protección", f"≥ IP{r['ip_min']}", "Salpicaduras de la bomba")], columns=["Requisito", "Valor", "Justificación"]), hide_index=True, width="stretch")
    st.subheader("2. Evaluación del catálogo")
    st.dataframe(tabla_ir.drop(columns=["Marca"]), hide_index=True, width="stretch",
                 column_config={"Puntaje": st.column_config.ProgressColumn("Puntaje", min_value=0, max_value=100, format="%.0f")})
    ok = tabla_ir[tabla_ir["Cumple todo"]]
    if len(ok):
        el = next(c for c in catalogo if c["Modelo"] == ok.iloc[0]["Modelo"])
        st.markdown(f"""<div class="recomendado"><div class="k">Transmisor recomendado</div><h2>{html.escape(el['Marca'])} {html.escape(el['Modelo'])}</h2>
<span class="badge">Puntaje {fmt(ok.iloc[0]['Puntaje'], 0)}</span><span class="badge">D:S {fmt(el['DS'], 0)}:1</span><span class="badge">Cabezal {el['Tcab_C']} °C</span>
<p style="margin:.7rem 0 0;color:#E3EEFF">Cumple todos los criterios del docente; mide un punto de {fmt(ok.iloc[0]['Punto medido (mm)'])} mm a {fmt(r['distancia_mm'], 0)} mm.
Se recomiendan dos unidades (rodamientos DE y NDE) y un PT100 de contacto como referencia de calibración.</p></div>""", unsafe_allow_html=True)
        ca, cb = st.columns([3, 2])
        ca.markdown(ficha_datasheet(el), unsafe_allow_html=True)
        with cb:
            pdf = N.DIR_CATALOGOS / el.get("PDF", "")
            if el.get("PDF") and pdf.exists():
                st.download_button(f"📄 Descargar datasheet ({pdf.name})", pdf.read_bytes(), pdf.name, "application/pdf")
                if hasattr(st, "pdf"):
                    try:
                        st.pdf(str(pdf), height=480)
                    except Exception:
                        pass
            st.info("**Conexión al S7-1200 CPU 1214C** (entradas integradas solo 0–10 V):\n\n"
                    "- **Recomendado:** módulo **SM 1231 AI** (4 u 8 canales) o **SB 1231 AI**; 4–20 mA → 5530 a 27648. Escalar con NORM_X y SCALE_X y vigilar "
                    "valores bajo 5530 (cable roto).\n- **Alternativa:** salida 0–10 V a la entrada integrada (X12), 0 a 27648, resolución de 10 bits.\n"
                    "- Configurar en el transmisor un rango de salida de 0–150 °C y emisividad 0,95 sobre cinta mate.")
    st.dataframe(pd.DataFrame(N.PORTATILES), hide_index=True, width="stretch")
    with st.expander("Editar catálogo (precios, cotizaciones, modelos nuevos)"):
        k = f"cat_{st.session_state.editor_ver}"
        ce = st.data_editor(pd.DataFrame(catalogo), num_rows="dynamic", hide_index=True, width="stretch", key=k)
        cam = st.session_state.get(k, {})
        if cam and (cam.get("edited_rows") or cam.get("added_rows") or cam.get("deleted_rows")):
            N.guardar_json(N.ARCH_CATALOGO, {"version": 5, "items": [{kk: N.limpio(v) for kk, v in x.items()} for x in ce.to_dict("records") if x.get("Modelo")]})
            st.session_state.editor_ver += 1
            st.rerun()
        if st.button("Restaurar catálogo original"):
            N.guardar_json(N.ARCH_CATALOGO, {"version": 5, "items": N.CATALOGO_DEF})
            st.rerun()

# =============================================================================
# ▶️ Simulación en vivo (reproduce la data del ingeniero hora por hora)
# =============================================================================
if nav == "▶️ Simulación":
    st.subheader("Monitoreo simulado en tiempo real")
    st.write("Reproduce la data del ingeniero hora por hora, como si llegara del PLC: actualiza el estado, la temperatura y el diagnóstico, "
             "y puede enviar alertas a Telegram cuando aparece una falla.")
    eventos = dbase[(dbase["nivel"] > 0)]
    inicios = dbase[(dbase["nivel"] > 0) & (dbase["nivel"].shift() == 0)]
    sugeridos = {f"{r.timestamp} – {N.NOMBRE_ESTADO[r.estado]}": i for i, r in zip(inicios.index, inicios.itertuples())}
    c = st.columns([3, 1, 1])
    elec = c[0].selectbox("Empezar 12 h antes de este evento", list(sugeridos))
    horas = c[1].number_input("Horas a reproducir", 6, 240, 36)
    vel = c[2].selectbox("Velocidad", ["Rápida", "Normal", "Lenta"], index=1)
    enviar_tg = st.toggle("Enviar alertas a Telegram al cambiar a un estado de falla (máximo 3 por reproducción)", value=False)
    if st.button("▶️ Reproducir", type="primary"):
        i0 = max(0, sugeridos[elec] - 12)
        tramo = dbase.iloc[i0:i0 + int(horas)]
        pausa = {"Rápida": 0.08, "Normal": 0.35, "Lenta": 0.9}[vel]
        caja, graf, diag_box = st.empty(), st.empty(), st.empty()
        hist, previo, enviados, log = [], None, 0, []
        for _, f in tramo.iterrows():
            f = f.to_dict()
            hist.append(f)
            with caja.container():
                st.markdown(f"**{f['timestamp']}** &nbsp; {chip(f['estado'])}", unsafe_allow_html=True)
                tarjetas_estado(f)
            hdf = pd.DataFrame(hist).assign(Fecha=lambda x: pd.to_datetime(x["timestamp"]))
            graf.altair_chart(alt.Chart(hdf[hdf["estado_bomba"] == 1]).mark_line(point=True).encode(
                x=alt.X("Fecha:T", title=None), y=alt.Y("T_F:Q", title="°F", scale=alt.Scale(zero=False)),
                color=alt.value("#1F6FEB")).properties(height=220), width="stretch")
            if f["estado"] != previo:
                diags = N.diagnosticar(f, equipo)
                with diag_box.container():
                    if diags:
                        tarjetas_diagnostico(diags[:2])
                    else:
                        st.success("Operación sin fallas.")
                log.append({"Hora": f["timestamp"], "Nuevo estado": N.NOMBRE_ESTADO.get(f["estado"], f["estado"])})
                if enviar_tg and diags and N.NIVEL_ESTADO.get(f["estado"], 0) >= int(alertas_cfg.get("nivel_min", 1)) and enviados < 3:
                    ok_, det_ = N.telegram_enviar(N.mensaje_alerta(f, diags, "🧪 SIMULACIÓN · "), alertas_cfg)
                    enviados += 1
                    log[-1]["Telegram"] = "✔" if ok_ else f"✘ {det_}"
            previo = f["estado"]
            time.sleep(pausa)
        st.markdown("**Cambios de estado durante la simulación**")
        st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")

# =============================================================================
# 📋 Datos
# =============================================================================
if nav == "📋 Datos":
    vista = st.radio("Ver", ["Data del ingeniero (solo lectura)", "Registros nuevos (editable)"], horizontal=True)
    if vista.startswith("Data"):
        cols = ["timestamp", "estado_txt", "horas_trabajo_acum_h", "caudal_GPM", "presion_succion_PSI", "presion_descarga_PSI", "margen_NPSH_m",
                "margen_lat_m", "vibracion_succion_mm_s", "vibracion_descarga_mm_s", "temperatura_motor_C", "T_F", "I_prom_A", "potencia_activa_kW",
                "factor_potencia", "health_index_rodamiento", "RUL_rodamiento_h", "evento_mantenimiento"]
        est = st.multiselect("Filtrar por estado", N.ESTADOS, format_func=lambda e: N.NOMBRE_ESTADO[e])
        v = dbase[dbase["estado"].isin(est)] if est else dbase
        st.dataframe(v[cols].round(3), hide_index=True, width="stretch", height=420)
        st.download_button("Descargar CSV con variables calculadas", dbase.to_csv(index=False).encode("utf-8-sig"), "data_goulds_calculada.csv", "text/csv")
    else:
        k = f"reg_{st.session_state.editor_ver}"
        ed = st.data_editor(reg, num_rows="dynamic", hide_index=True, width="stretch", key=k,
                            column_config={"ID": st.column_config.NumberColumn("ID", disabled=True), "Origen": st.column_config.TextColumn("Origen", disabled=True)})
        cam = st.session_state.get(k, {})
        if cam and (cam.get("edited_rows") or cam.get("added_rows") or cam.get("deleted_rows")):
            N.guardar_registros(ed)
            st.session_state.editor_ver += 1
            st.session_state["msg"] = "Cambios guardados"
            st.rerun()
        if len(dreg):
            st.markdown("**Resultado calculado de los registros nuevos**")
            st.dataframe(dreg[["ID", "timestamp", "estado_txt", "fuente_estado", "RUL_h", "T_F", "margen_NPSH_m", "Vib_max", "carga_pct"]].round(2), hide_index=True, width="stretch")
        sub = st.file_uploader("Cargar mediciones desde CSV o Excel (mismos nombres de columna que la data del ingeniero)", type=["csv", "xlsx"])
        if sub is not None and st.button("Importar archivo"):
            nuevo = pd.read_csv(sub) if sub.name.lower().endswith(".csv") else pd.read_excel(sub)
            nuevo["ID"] = np.nan
            N.guardar_registros(pd.concat([reg, N.normalizar(nuevo)], ignore_index=True))
            st.session_state["msg"] = f"{len(nuevo)} registros importados"
            st.rerun()

# =============================================================================
# 🔔 Alertas
# =============================================================================
if nav == "🔔 Alertas":
    st.subheader("Alertas en el celular y la computadora (Telegram)")
    with st.form("form_alertas"):
        activo = st.toggle("Enviar alertas por Telegram", value=bool(alertas_cfg.get("activo")))
        token = st.text_input("Token del bot (@BotFather)", value=alertas_cfg.get("token", ""), type="password")
        chats = st.text_input("Chat ID de los destinatarios (separados por coma)", value=alertas_cfg.get("chats", ""))
        nivel = st.radio("Enviar desde", [1, 2], index=int(alertas_cfg.get("nivel_min", 1)) - 1, horizontal=True,
                         format_func=lambda n: "🟡 Alerta y crítico" if n == 1 else "🔴 Solo crítico")
        if st.form_submit_button("Guardar configuración", type="primary"):
            alertas_cfg.update({"activo": activo, "token": token.strip(), "chats": chats.strip(), "nivel_min": nivel})
            N.guardar_json(N.ARCH_ALERTAS, alertas_cfg)
            st.session_state["msg"] = "Configuración guardada"
            st.rerun()
    c = st.columns(2)
    if c[0].button("📨 Enviar mensaje de prueba"):
        ok_, det_ = N.telegram_enviar("✅ Prueba de alertas – Monitoreo Goulds 3642 ESPE Latacunga", alertas_cfg)
        (st.success if ok_ else st.error)(det_)
    if c[1].button("🔎 Buscar mi chat ID"):
        try:
            rr = requests.get(f"https://api.telegram.org/bot{alertas_cfg.get('token', '')}/getUpdates", timeout=10).json()
            enc = {}
            for u in rr.get("result", []):
                ch = (u.get("message") or u.get("my_chat_member") or {}).get("chat", {})
                if ch.get("id"):
                    enc[ch["id"]] = ch.get("first_name") or ch.get("title") or ""
            (st.success if enc else st.warning)("Chats: " + ", ".join(f"{k} ({v})" for k, v in enc.items()) if enc else "Escribe un mensaje a tu bot y vuelve a pulsar.")
        except Exception as ex:
            st.error(f"No se pudo consultar Telegram: {ex}")
    if alertas_cfg.get("historial"):
        st.dataframe(pd.DataFrame(alertas_cfg["historial"]), hide_index=True, width="stretch")

# =============================================================================
# ⚙️ Configuración
# =============================================================================
if nav == "⚙️ Configuración":
    st.subheader("Operadores y asignatura")
    st.markdown(f"**Docente responsable:** {N.DOCENTE}")
    k = f"ops_{st.session_state.editor_ver}"
    oe = st.data_editor(pd.DataFrame(equipo.get("operadores", []), columns=["Nombre", "Función"]), num_rows="dynamic", hide_index=True, width="stretch", key=k,
                        column_config={"Función": st.column_config.SelectboxColumn("Función", options=["Coordinador", "Operador de ensayo", "Registro de datos", "Instrumentación", "Análisis del modelo"])})
    cam = st.session_state.get(k, {})
    if cam and (cam.get("edited_rows") or cam.get("added_rows") or cam.get("deleted_rows")):
        equipo["operadores"] = [o for o in oe.fillna("").to_dict("records") if str(o.get("Nombre", "")).strip()]
        N.guardar_json(N.ARCH_EQUIPO, equipo)
        st.session_state.editor_ver += 1
        st.rerun()
    with st.form("form_cfg"):
        c = st.columns([3, 1, 1])
        e = dict(equipo)
        e["asignatura"] = c[0].text_input("Asignatura", e.get("asignatura", ""))
        e["nrc"] = c[1].text_input("NRC", e.get("nrc", ""))
        e["periodo"] = c[2].text_input("Período", e.get("periodo", ""))
        e["proyecto"] = st.text_area("Título del proyecto", e.get("proyecto", ""), height=70)
        st.markdown("**Límites y datos técnicos**")
        c = st.columns(4)
        e["alarma_C"] = c[0].number_input("Alarma de temperatura (°C)", value=float(e["alarma_C"]))
        e["disparo_C"] = c[1].number_input("Disparo de temperatura (°C)", value=float(e["disparo_C"]))
        e["rul_aviso_h"] = c[2].number_input("Aviso de RUL (h)", value=float(e["rul_aviso_h"]))
        e["altitud_m"] = c[3].number_input("Altitud del laboratorio (m)", value=float(e["altitud_m"]))
        c = st.columns(4)
        e["motor_i"] = c[0].number_input("Corriente nominal (A)", value=float(e["motor_i"]))
        e["motor_i_sf"] = c[1].number_input("Corriente con SF (A)", value=float(e["motor_i_sf"]))
        e["bomba_alabes"] = c[2].number_input("Álabes del impulsor Z", value=int(e["bomba_alabes"]), min_value=1)
        e["t_agua_C"] = c[3].number_input("Temperatura del agua (°C)", value=float(e["t_agua_C"]))
        c = st.columns(4)
        e["rod_DE"] = c[0].selectbox("Rodamiento DE", list(N.BD_RODAMIENTOS), index=list(N.BD_RODAMIENTOS).index(e["rod_DE"]))
        e["rod_NDE"] = c[1].selectbox("Rodamiento NDE", list(N.BD_RODAMIENTOS), index=list(N.BD_RODAMIENTOS).index(e["rod_NDE"]))
        e["iso_B"] = c[2].number_input("ISO zona B ≤ (mm/s)", value=float(e["iso_B"]))
        e["iso_C"] = c[3].number_input("ISO zona C ≤ (mm/s)", value=float(e["iso_C"]))
        if st.form_submit_button("Guardar", type="primary"):
            N.guardar_json(N.ARCH_EQUIPO, e)
            st.session_state["msg"] = "Configuración guardada"
            st.rerun()

# =============================================================================
# 📄 Informe
# =============================================================================
def generar_informe() -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    figs = []

    def fig_png(fig):
        b = BytesIO()
        fig.tight_layout()
        fig.savefig(b, format="png", dpi=160)
        plt.close(fig)
        return b.getvalue()

    op = dbase[dbase["estado_bomba"] == 1]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    for e in N.ESTADOS:
        s = op[op["estado"] == e]
        if len(s):
            ax.scatter(pd.to_datetime(s["timestamp"]), s["T_F"], s=4, color=N.COLOR_ESTADO[e], label=N.NOMBRE_ESTADO[e])
    ax.set_ylabel("°F"), ax.legend(fontsize=6, markerscale=3), ax.grid(alpha=.3), ax.set_title("Temperatura IR del escudo por estado de falla")
    figs.append(("La temperatura del escudo sube cuando el rodamiento se degrada.", fig_png(fig)))
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.scatter(op["caudal_GPM"], op["NPSHa_m"], s=4, label="NPSHa (data, nivel del mar)")
    ax.scatter(op["caudal_GPM"], op["NPSHa_lat_m"], s=4, label="NPSHa en Latacunga")
    ax.plot(N.CURVA["Q_gpm"], N.CURVA["NPSHr_m"], color="#D64545", lw=2, label="NPSHr fabricante")
    ax.set_xlim(20, 40), ax.set_xlabel("Caudal (GPM)"), ax.set_ylabel("m"), ax.legend(fontsize=7), ax.grid(alpha=.3), ax.set_title("Efecto de la altitud en el NPSH")
    figs.append(("A 2750 m el NPSH disponible baja cerca de 3 m.", fig_png(fig)))
    cm = modelos["matriz"]
    fig, ax = plt.subplots(figsize=(5.8, 5))
    ax.imshow(cm, cmap="Blues")
    et = [N.NOMBRE_ESTADO[c] for c in modelos["clases"]]
    ax.set_xticks(range(len(et))), ax.set_xticklabels(et, rotation=45, ha="right", fontsize=7), ax.set_yticks(range(len(et))), ax.set_yticklabels(et, fontsize=7)
    for i in range(len(et)):
        for j in range(len(et)):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=8)
    ax.set_title("Matriz de confusión del MLP (prueba)")
    figs.append(("Clasificación del estado de falla con variables medibles.", fig_png(fig)))
    cr = modelos["curva_rul"]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.plot(cr["horas"], cr["RUL real"], label="RUL real (recortado)"), ax.plot(cr["horas"], cr["RUL MLP"], alpha=.7, label="RUL MLP")
    ax.set_xlabel("Horas de operación"), ax.set_ylabel("h"), ax.legend(), ax.grid(alpha=.3), ax.set_title("Vida remanente del rodamiento")
    figs.append(("El RUL solo es observable cuando empieza la degradación.", fig_png(fig)))

    doc = Document()
    doc.styles["Normal"].font.name, doc.styles["Normal"].font.size = "Calibri", Pt(11)
    tl = doc.add_table(rows=1, cols=2)
    tl.autofit = False
    tl.cell(0, 0).width, tl.cell(0, 1).width = Cm(12.6), Cm(4)
    for celda, nom, w in ((tl.cell(0, 0), "logo_espe.png", 8), (tl.cell(0, 1), "logo_em.png", 2.4)):
        if (BASE / nom).exists():
            celda.paragraphs[0].add_run().add_picture(str(BASE / nom), width=Cm(w))
    tl.cell(0, 1).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    def tit(t, n=1):
        h = doc.add_heading(t, level=n)
        for r_ in h.runs:
            r_.font.color.rgb = RGBColor(0x0A, 0x1F, 0x44)

    def tabla(filas, enc):
        t = doc.add_table(rows=1, cols=len(enc))
        t.style = "Light Grid Accent 1"
        for i, v in enumerate(enc):
            t.rows[0].cells[i].text = str(v)
        for f in filas:
            cs = t.add_row().cells
            for i, v in enumerate(f):
                cs[i].text = str(v)
        doc.add_paragraph()

    tit(equipo["proyecto"], 0)
    p = doc.add_paragraph()
    p.add_run("Universidad de las Fuerzas Armadas ESPE – Sede Latacunga\n").bold = True
    p.add_run(f"Departamento de Eléctrica y Electrónica | Ingeniería Electromecánica\nDocente responsable: {N.DOCENTE}\n")
    p.add_run("Operadores: " + (", ".join(o["Nombre"] for o in equipo.get("operadores", []) if o.get("Nombre")) or "—") + "\n")
    p.add_run(f"Fecha: {datetime.now():%Y-%m-%d %H:%M}")
    tit("1. Datos analizados")
    doc.add_paragraph(f"Data sintética Goulds 3642 del docente: {len(dbase)} registros horarios, {int((dbase['estado_bomba'] == 1).sum())} h en operación. "
                      f"Registros nuevos: {len(dreg)}.")
    cnt = dbase["estado_txt"].value_counts()
    tabla([(k, v, f"{v / len(dbase) * 100:.1f} %") for k, v in cnt.items()], ["Estado", "Horas", "%"])
    tit("2. Resultados")
    for i, (txt, img) in enumerate(figs, 1):
        doc.add_picture(BytesIO(img), width=Cm(15 if i != 3 else 11))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Figura {i}. {txt}").runs[0].italic = True
    tit("3. Modelos")
    tabla([("MLP estado (esta app)", f"F1 macro {modelos['f1']:.3f}"), ("MLP RUL (esta app)", f"MAE {modelos['mae']:.1f} h; R² {modelos['r2']:.3f}"),
           ("MLP / LSTM (Colab del docente)", "F1 0,966 / 0,646; RUL R² 0,962 / 0,993")], ["Modelo", "Resultado"])
    if modelo_temp:
        doc.add_paragraph("Modelo de temperatura del escudo: ").add_run(modelo_temp["ecuacion"]).bold = True
        doc.add_paragraph(f"R² = {modelo_temp['r2']:.3f}; RMSE = {modelo_temp['rmse_F']:.2f} °F.")
    tit("4. Selección del transmisor IR")
    tabla([(x["Modelo"], "Sí" if x["Cumple todo"] else "No", x["Punto medido (mm)"], x["Puntaje"], x["No cumple"]) for x in tabla_ir.to_dict("records")],
          ["Modelo", "Cumple", "Punto (mm)", "Puntaje", "No cumple"])
    if len(tabla_ir) and tabla_ir["Cumple todo"].any():
        doc.add_paragraph(f"Transmisor recomendado: {tabla_ir.iloc[0]['Marca']} {tabla_ir.iloc[0]['Modelo']}, dos unidades (DE y NDE), conectadas a un SM 1231 AI "
                          "(4–20 mA → 5530–27648) y un PT100 de contacto como referencia.")
    b = BytesIO()
    doc.save(b)
    return b.getvalue()


if nav == "📄 Informe":
    st.subheader("Informe automático en Word")
    if st.button("Generar informe", type="primary"):
        try:
            with st.spinner("Generando..."):
                st.session_state["informe"] = generar_informe()
        except ImportError:
            st.error("Falta python-docx o matplotlib.")
    if st.session_state.get("informe"):
        st.download_button("📄 Descargar informe (.docx)", st.session_state["informe"], f"Informe_Goulds3642_{datetime.now():%Y%m%d_%H%M}.docx",
                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    st.subheader("Respaldo")
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("registros_nuevos.csv", reg.to_csv(index=False))
        for nom, cont in (("equipo.json", equipo), ("mantenimiento.json", mant), ("historial_rodamientos.json", hist_rod), ("modelo.json", modelo_temp)):
            if cont:
                z.writestr(nom, json.dumps(cont, indent=2, ensure_ascii=False, default=str))
    st.download_button("💾 Descargar respaldo (.zip)", buf.getvalue(), f"respaldo_{datetime.now():%Y%m%d}.zip", "application/zip")

st.markdown("""<div class="pie"><b>Universidad de las Fuerzas Armadas ESPE – Sede Latacunga</b><br>
Departamento de Eléctrica y Electrónica | Carrera de Ingeniería Electromecánica</div>""", unsafe_allow_html=True)
