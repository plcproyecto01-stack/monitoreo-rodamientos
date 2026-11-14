# -*- coding: utf-8 -*-
"""
Monitoreo predictivo del conjunto motor Emerson P55CST-1247 + bomba Goulds 3642
Universidad de las Fuerzas Armadas ESPE – Sede Latacunga | Ingeniería Electromecánica

Archivos: app_rodamientos.py (pantallas), nucleo.py (cálculos), estilos.py, logos, .streamlit/,
datos_prueba/ (datos recolectados), catalogos/ (hojas de datos).
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


def U() -> str:
    return st.session_state.get("unidad", "°F")


def temp(t_f, nd=1) -> str:
    """Temperatura en la unidad elegida, con la otra entre paréntesis (entrada en °F)."""
    if t_f is None or (isinstance(t_f, float) and math.isnan(t_f)):
        return "—"
    c = (t_f - 32) / 1.8
    return f"{fmt(t_f, nd)} °F ({fmt(c, nd)} °C)" if U() == "°F" else f"{fmt(c, nd)} °C ({fmt(t_f, nd)} °F)"


def temp1(t_f, nd=1) -> str:
    """Solo la unidad elegida."""
    if t_f is None or (isinstance(t_f, float) and math.isnan(t_f)):
        return "—"
    return f"{fmt(t_f, nd)} °F" if U() == "°F" else f"{fmt((t_f - 32) / 1.8, nd)} °C"


def temp2(t_f, nd=1) -> str:
    """Solo la otra unidad."""
    if t_f is None or (isinstance(t_f, float) and math.isnan(t_f)):
        return "—"
    return f"{fmt((t_f - 32) / 1.8, nd)} °C" if U() == "°F" else f"{fmt(t_f, nd)} °F"


def temp_u(t_f):
    """Valor numérico en la unidad elegida."""
    return t_f if U() == "°F" else (t_f - 32) / 1.8


def intro(para_que: str, que_hacer: str) -> None:
    st.markdown(f"""<div class="intro"><div><span class="etq">¿Para qué sirve?</span>{para_que}</div>
<div><span class="etq">¿Qué hago aquí?</span>{que_hacer}</div></div>""", unsafe_allow_html=True)


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
<b class="t">¿Qué está pasando?</b><h4>{'🔴' if d['Gravedad'] == 2 else '🟡'} {html.escape(d['Falla'])}</h4><div class="ev">{html.escape(d['Evidencia'])}</div>
<div class="cols"><div><b class="t">¿Por qué puede estar pasando?</b><ul>{''.join(f'<li>{html.escape(c)}</li>' for c in d['Causas'])}</ul></div>
<div><b class="t">¿Qué hago?</b><ul>{''.join(f'<li>{html.escape(a)}</li>' for a in d['Acciones'])}</ul></div></div></div>""",
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
<p class="sub">{html.escape(eq.get('proyecto', ''))}. Motor {html.escape(eq['motor_marca'])} {html.escape(eq['motor_modelo'])}; temperaturas en °F y °C.</p></div>
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
    return {**N.DEF_EQUIPO, **(datos or {}), "version": 5,
            # integrantes y asignatura fijos
            "operadores": [{"Nombre": x, "Función": ""} for x in N.INTEGRANTES],
            "asignatura": N.ASIGNATURA, "nrc": N.NRC, "periodo": N.PERIODO}


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
    st.error("No se encontraron los datos recolectados en la carpeta «datos_prueba».")
    st.stop()
dbase = N.derivar(base, equipo)
modelos = N.entrenar_modelos(dbase, "v5")
dbase = N.completar_estado(dbase, None)
dreg = N.completar_estado(N.derivar(reg, equipo), modelos) if len(reg) else pd.DataFrame(columns=dbase.columns)
dtodo = pd.concat([dbase, dreg], ignore_index=True)


@st.cache_data(show_spinner=False)
def modelo_automatico(_d: pd.DataFrame, clave: str) -> dict | None:
    op = _d[_d["estado_bomba"] == 1]
    cand = [c for c in N.CANDIDATAS if c not in ("horas_trabajo_acum_h", "margen_NPSH_m") and op[c].std() > 0]
    corr = op[cand + ["T_F"]].astype(float).corr()
    orden = corr["T_F"].drop("T_F").abs().sort_values(ascending=False).index
    vars_x = []
    for v in orden:
        if all(abs(corr.at[v, u]) < 0.9 for u in vars_x):
            vars_x.append(v)
        if len(vars_x) == 3:
            break
    dm = op.dropna(subset=vars_x + ["T_F"]).sort_values("timestamp")
    corte = int(len(dm) * 0.7)
    r_val = N.regresion(dm[vars_x].iloc[:corte].values, dm["T_F"].iloc[:corte].values)
    pred = np.column_stack([np.ones(len(dm)), dm[vars_x].values]) @ r_val["beta"]
    rmse_v = math.sqrt(float(((dm["T_F"].values[corte:] - pred[corte:]) ** 2).mean()))
    r = N.regresion(dm[vars_x].values, dm["T_F"].values)
    return {"nombre": "Lineal (automático)", "objetivo": "T_F", "variables": vars_x, "terminos": vars_x,
            "intercepto": float(r["beta"][0]), "coeficientes": [float(b) for b in r["beta"][1:]],
            "ecuacion": N.ecuacion_texto("T(°F)", float(r["beta"][0]), r["beta"][1:], vars_x), "r2": r["r2"],
            "rmse_F": r["rmse"], "rmse_validacion_F": rmse_v, "n": len(dm), "fecha": "calculado con los datos recolectados"}


modelo_activo = modelo_temp or modelo_automatico(dbase, "v5")

_AYUDA = {
    "horas_trabajo_acum_h": ("Horas que ha funcionado la bomba con el rodamiento actual. Se lee en el horómetro o en el registro de operación.", "h"),
    "nivel_tanque_mm": ("Altura del agua en el tanque de succión. Se mide con la regla graduada o el sensor de nivel.", "mm"),
    "caudal_L_h": ("Cantidad de agua que entrega la bomba. Se lee en el caudalímetro.", "L/h"),
    "presion_succion_PSI": ("Presión del manómetro ANTES de la bomba (entrada). Normalmente marca vacío: escríbela con signo menos.", "psi"),
    "presion_descarga_PSI": ("Presión del manómetro DESPUÉS de la bomba (salida).", "psi"),
    "vibracion_succion_mm_s": ("Vibración medida con el vibrómetro sobre la carcasa de la bomba, lado de entrada, en velocidad RMS.", "mm/s"),
    "vibracion_descarga_mm_s": ("Vibración medida con el vibrómetro sobre la carcasa, lado de salida, en velocidad RMS.", "mm/s"),
    "temperatura_motor_C": ("Temperatura de la tapa del rodamiento medida con el sensor o termómetro infrarrojo (IR), apuntando siempre al mismo punto.", "°C"),
    "V_L1L2_V": ("Voltaje entre las fases L1 y L2, medido con multímetro o analizador de redes.", "V"),
    "V_L2L3_V": ("Voltaje entre las fases L2 y L3.", "V"), "V_L3L1_V": ("Voltaje entre las fases L3 y L1.", "V"),
    "I_L1_A": ("Corriente de la fase L1, medida con pinza amperimétrica. La nominal del motor es 3,0 A.", "A"),
    "I_L2_A": ("Corriente de la fase L2, medida con pinza amperimétrica.", "A"), "I_L3_A": ("Corriente de la fase L3, medida con pinza amperimétrica.", "A"),
    "potencia_activa_kW": ("Potencia que consume el motor, leída en el analizador de redes.", "kW"),
    "potencia_reactiva_kVAr": ("Potencia reactiva, leída en el analizador de redes.", "kVAr"),
}
_norm = dbase[dbase["estado"] == "NORMAL"]
AYUDA_CAMPO = {}
for _k, (_t, _u) in _AYUDA.items():
    _q = _norm[_k].dropna()
    _nd = 0 if _q.abs().max() > 100 else 2
    AYUDA_CAMPO[_k] = f"{_t} Valor normal en los datos recolectados: {fmt(_q.quantile(.05), _nd)} a {fmt(_q.quantile(.95), _nd)} {_u}."
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
    st.radio("Unidad de temperatura", ["°F", "°C"], horizontal=True, key="unidad",
             help="Cambia todas las pantallas. La otra unidad se sigue mostrando entre paréntesis.")
    filtro = st.radio("Datos a analizar", [N.ORIGEN_BASE, "Registros nuevos", "Todos"], index=0,
                      help="Datos recolectados: las 4320 h de operación de la bomba. Registros nuevos: los que ingresas tú.")
    st.metric("Datos recolectados", f"{len(dbase):,} h".replace(",", "."), f"{int((dbase['estado_bomba'] == 1).sum())} h en operación", delta_color="off")
    st.metric("Registros nuevos", len(dreg))

for _x in (dbase, dreg, dtodo):
    if len(_x):
        _x["T_U"] = _x["T_F"] if U() == "°F" else _x["temperatura_motor_C"]
d = {N.ORIGEN_BASE: dbase, "Registros nuevos": dreg, "Todos": dtodo}[filtro].copy()
dop = d[d["estado_bomba"] == 1].copy()
req_ir = N.requisitos_ir(dop if len(dop) else dbase, equipo)
tabla_ir = N.evaluar_catalogo(catalogo, req_ir)

SECCIONES = ["🏠 Inicio", "➕ Registro de datos", "🔍 Modelo", "🧮 Calculadora de temperatura", "🌡️ Transmisor IR", "📊 Gráficas",
             "🩺 Diagnóstico", "🧠 Estado y vida útil", "⚙️ Rodamientos", "💧 Cavitación", "🛠️ Mantenimiento", "▶️ Simulación",
             "📋 Datos", "🔔 Alertas", "⚙️ Configuración", "📄 Informe", "📖 Glosario"]
with st.container(key="nav"):
    if hasattr(st, "pills"):
        nav = st.pills("Sección", SECCIONES, selection_mode="single", default="🏠 Inicio", key="seccion", label_visibility="collapsed")
    else:
        nav = st.radio("Sección", SECCIONES, horizontal=True, label_visibility="collapsed", key="seccion")
    nav = nav or "🏠 Inicio"

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
    if f.get("estado_bomba") == 0:
        st.info(f"⏸️ En este registro la **bomba estaba detenida** ({N.NOMBRE_ESTADO.get(f.get('estado'), '')}). "
                "Sin operación no hay caudal ni vibración que evaluar.")
        return
    rul = f.get("RUL_h")
    zr = None if rul is None or pd.isna(rul) else (2 if rul <= equipo["rul_aviso_h"] / 4 else 1 if rul <= equipo["rul_aviso_h"] else 0)
    alarma_f = N.c_a_f(equipo["alarma_C"])
    tarjetas_semaforo([
        ("Estado del equipo", N.NOMBRE_ESTADO.get(f["estado"], f["estado"]), None, str(f.get("fuente_estado", ""))[:60], N.COLOR_ESTADO.get(f["estado"])),
        ("Temperatura del rodamiento", temp1(f.get("T_F")), f.get("zona_T"), f"= {temp2(f.get('T_F'))} · sensor IR · alarma {temp1(alarma_f, 0)}"),
        ("Vida útil restante", (f"{fmt(rul, 0)} h" + (" o más" if rul and rul >= N.RUL_TOPE_H - 1 else "")) if rul is not None and not pd.isna(rul) else "—",
         zr, "horas de operación antes de cambiar el rodamiento"),
        ("Margen contra cavitación", f"{fmt(f.get('margen_NPSH_m'), 2)} m", zona_margen(f.get("margen_NPSH_m")), f"NPSH; seguro sobre 0,82 m · en Latacunga {fmt(f.get('margen_lat_m'), 2)} m"),
        ("Vibración máxima", f"{fmt(f.get('Vib_max'), 2)} mm/s", f.get("zona_vib"), f"normal hasta {fmt(equipo['iso_B'])} mm/s"),
        ("Carga del motor", f"{fmt(f.get('carga_pct'), 0)} %", f.get("zona_carga"), f"{fmt(f.get('I_prom_A'), 2)} A de {equipo['motor_i']} A nominales"),
    ])


# =============================================================================
# 🏠 Inicio
# =============================================================================
if nav == "🏠 Inicio":
    intro("Resume el proyecto en tres pasos: se recolectan datos de la bomba, con ellos se construye un modelo matemático de la "
          "temperatura del rodamiento y, a partir de ambos, se elige el transmisor de temperatura infrarrojo (IR) adecuado. "
          "Debajo se ve cómo estaba el equipo en el último registro.",
          "Solo revisar. Entra a cada parte con los botones del menú. El selector °F / °C de la barra lateral cambia las unidades de toda la aplicación.")
    st.subheader("Ruta del proyecto")
    opb = dbase[dbase["estado_bomba"] == 1]
    ok_ir = tabla_ir[tabla_ir["Cumple todo"]] if len(tabla_ir) else tabla_ir
    sel = next((c for c in catalogo if len(ok_ir) and c["Modelo"] == ok_ir.iloc[0]["Modelo"]), None)
    eq_f, eq_c = N.ecuaciones(modelo_activo)
    err_u = modelo_activo["rmse_F"] if U() == "°F" else modelo_activo["rmse_F"] / 1.8
    st.markdown(f"""<div class="ruta">
<div class="paso"><span class="n">1</span><h4>Recolección de datos</h4>
<div class="big">{len(dbase)} horas registradas</div>
<p>{len(opb)} h con la bomba funcionando, del {dbase['timestamp'].min()[:10]} al {dbase['timestamp'].max()[:10]}.</p>
<p>17 variables medidas: proceso, vibración, temperatura del rodamiento (sensor IR) y eléctricas.</p></div>
<div class="paso"><span class="n">2</span><h4>Modelo matemático de la temperatura</h4>
<div class="big">Acierta el {fmt(modelo_activo['r2'] * 100, 0)} % · error ±{fmt(err_u, 1)} {U()}</div>
<p class="eq">{html.escape(eq_f)}<br>{html.escape(eq_c)}</p>
<p style="font-size:.8rem">{html.escape(N.leyenda_ecuacion(modelo_activo))}</p></div>
<div class="paso fin"><span class="n">3</span><h4>Transmisor IR seleccionado</h4>
<div class="big">{html.escape(sel['Marca'] + ' ' + sel['Modelo']) if sel else 'Ninguno cumple'}</div>
<p>{f"Mide de {sel['T_min_C']} a {sel['T_max_C']} °C · óptica {fmt(sel['DS'], 0)}:1 · salida {sel['Salidas'].split(';')[0]} · soporta {sel['Tcab_C']} °C en el cabezal" if sel else 'Revisar criterios'}</p>
<p>Temperatura máxima registrada: {temp(N.c_a_f(req_ir['t_max_obs_C'])) if req_ir['t_max_obs_C'] else '—'}.</p></div>
</div>""", unsafe_allow_html=True)
    st.subheader("Estado actual del equipo")
    if dop.empty:
        st.info("No hay registros en operación en el conjunto seleccionado. Registra mediciones en «➕ Registro de datos».")
    else:
        ult = dop.sort_values("timestamp").iloc[-1].to_dict()
        st.caption(f"Último registro con la bomba funcionando: {ult['timestamp']} · horas acumuladas: {fmt(ult.get('horas_trabajo_acum_h'), 0)} h.")
        tarjetas_estado(ult)
        diags = N.diagnosticar(ult, equipo)
        if mant_venc:
            diags.append({"Falla": f"Mantenimiento vencido ({len(mant_venc)})", "Gravedad": 1, "Evidencia": "; ".join(t["Tarea"] for t in mant_venc[:3]),
                          "Causas": ["Tareas preventivas no registradas a tiempo"], "Acciones": ["Revisar «🛠️ Mantenimiento»"]})
        if diags:
            tarjetas_diagnostico(diags[:1])
        else:
            st.success("✅ El último registro no presenta fallas.")
        c = st.columns([3, 2])
        serie = muestra(dop.sort_values("timestamp"), 900).assign(Fecha=lambda x: pd.to_datetime(x["timestamp"]))
        c[0].markdown(f"**Temperatura del rodamiento ({U()}) en el tiempo, coloreada por estado**")
        c[0].altair_chart(alt.Chart(serie).mark_circle(size=14).encode(
            x=alt.X("Fecha:T", title=None), y=alt.Y("T_U:Q", title=U(), scale=alt.Scale(zero=False)),
            color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado"), tooltip=["timestamp", alt.Tooltip("T_U:Q", format=".1f", title=U()), "estado_txt"]
        ).properties(height=300), width="stretch")
        cuenta = d["estado_txt"].value_counts().reset_index()
        cuenta.columns = ["Estado", "Horas"]
        c[1].markdown("**Horas en cada estado**")
        c[1].altair_chart(alt.Chart(cuenta).mark_bar().encode(
            x="Horas:Q", y=alt.Y("Estado:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)), color=alt.Color("Estado:N", scale=ESCALA_EST, legend=None),
            tooltip=["Estado", "Horas"]).properties(height=300), width="stretch")
        st.caption("Se ve claramente que la temperatura sube cuando el rodamiento se degrada (naranja y rojo): por eso un transmisor IR sirve para vigilarlo.")

# =============================================================================
# ➕ Registrar
# =============================================================================
CAMPOS_REG = [  # (clave, etiqueta, paso)
    ("horas_trabajo_acum_h", "Horas de trabajo acumuladas (h)", 1.0), ("nivel_tanque_mm", "Nivel del tanque (mm)", 1.0),
    ("caudal_L_h", "Caudal (L/h)", 10.0), ("presion_succion_PSI", "Presión de succión (psi, negativa si hay vacío)", 0.1),
    ("presion_descarga_PSI", "Presión de descarga (psi)", 0.1), ("vibracion_succion_mm_s", "Vibración en succión (mm/s RMS)", 0.01),
    ("vibracion_descarga_mm_s", "Vibración en descarga (mm/s RMS)", 0.01), ("temperatura_motor_C", "Temperatura del rodamiento (sensor IR)", 0.1),
    ("V_L1L2_V", "Voltaje L1-L2 (V)", 0.1), ("V_L2L3_V", "Voltaje L2-L3 (V)", 0.1), ("V_L3L1_V", "Voltaje L3-L1 (V)", 0.1),
    ("I_L1_A", "Corriente L1 (A)", 0.01), ("I_L2_A", "Corriente L2 (A)", 0.01), ("I_L3_A", "Corriente L3 (A)", 0.01),
    ("potencia_activa_kW", "Potencia activa (kW)", 0.001), ("potencia_reactiva_kVAr", "Potencia reactiva (kVAr)", 0.001),
]

def tabla_valores(pares, columnas=3) -> str:
    celdas = "".join(f'<div class="kv"><span>{html.escape(k)}</span><b>{html.escape(v)}</b></div>' for k, v in pares)
    return f'<div class="kvgrid" style="grid-template-columns:repeat(auto-fit,minmax({220 if columnas == 3 else 180}px,1fr))">{celdas}</div>'


if nav == "➕ Registro de datos":
    st.subheader("Registro de datos")
    intro("Muestra las mediciones de la bomba y lo que la aplicación calcula con ellas: temperatura esperada, estado del equipo, vida útil restante y diagnóstico.",
          "En «📄 Prueba con datos recolectados» recorre las pruebas ya llenas con ◀ ▶. En «✏️ Nuevo registro» escribe tus propias mediciones; "
          "pasa el cursor sobre el ícono (?) de cada casilla para ver qué va ahí y cuál es su valor normal.")
    modo = st.radio("Modo", ["📄 Prueba con datos recolectados", "✏️ Nuevo registro"], horizontal=True, key="modo_reg", label_visibility="collapsed")
    if modo.startswith("📄"):
        st.caption("Cada prueba es una hora de operación de la recolección de datos, con todos los campos llenos. Los resultados se calculan "
                   "al instante; esta vista no guarda nada. Para ingresar una medición propia usa «✏️ Nuevo registro».")
        op_b = dbase[dbase["estado_bomba"] == 1].sort_values("timestamp")
        c = st.columns([2, 1, 1, 1])
        est_f = c[0].selectbox("Pruebas a mostrar", ["Todos"] + [e for e in N.ESTADOS if e not in ("DETENIDA", "MANTENIMIENTO")],
                               format_func=lambda e: "Todas las pruebas" if e == "Todos" else f"Solo: {N.NOMBRE_ESTADO[e]}")
        lista = op_b if est_f == "Todos" else op_b[op_b["estado"] == est_f]
        n = len(lista)
        if st.session_state.get("prueba_filtro") != est_f:
            st.session_state["prueba_filtro"], st.session_state["prueba_i"] = est_f, 1
        st.session_state.setdefault("prueba_i", 1)
        if c[1].button("◀ Anterior", width="stretch") and st.session_state["prueba_i"] > 1:
            st.session_state["prueba_i"] -= 1
        if c[2].button("Siguiente ▶", width="stretch") and st.session_state["prueba_i"] < n:
            st.session_state["prueba_i"] += 1
        i = c[3].number_input(f"Prueba N° (1 a {n})", min_value=1, max_value=max(n, 1), step=1, key="prueba_i")
        f = lista.iloc[int(i) - 1].to_dict()
        st.markdown(f"#### Prueba N° {int(i)} de {n} &nbsp; {chip(f['estado'])}", unsafe_allow_html=True)
        st.caption(f"Fecha y hora: {f['timestamp']} | Horas de trabajo acumuladas: {fmt(f['horas_trabajo_acum_h'], 0)} h | Bomba operando")
        c = st.columns(3)
        c[0].markdown('<div class="caja"><h4>Proceso</h4>' + tabla_valores([
            ("Nivel del tanque", f"{fmt(f['nivel_tanque_mm'])} mm"), ("Caudal", f"{fmt(f['caudal_L_h'], 0)} L/h"),
            ("Presión de succión", f"{fmt(f['presion_succion_PSI'], 3)} psi"), ("Presión de descarga", f"{fmt(f['presion_descarga_PSI'], 3)} psi")], 1)
            + "</div>", unsafe_allow_html=True)
        c[1].markdown('<div class="caja"><h4>Vibración y temperatura</h4>' + tabla_valores([
            ("Vibración en succión", f"{fmt(f['vibracion_succion_mm_s'], 3)} mm/s"), ("Vibración en descarga", f"{fmt(f['vibracion_descarga_mm_s'], 3)} mm/s"),
            ("Temperatura del rodamiento (sensor IR)", temp(f['T_F'], 1))], 1) + "</div>", unsafe_allow_html=True)
        c[2].markdown('<div class="caja"><h4>Eléctricas</h4>' + tabla_valores([
            ("Voltajes L1-L2 / L2-L3 / L3-L1", f"{fmt(f['V_L1L2_V'])} / {fmt(f['V_L2L3_V'])} / {fmt(f['V_L3L1_V'])} V"),
            ("Corrientes L1 / L2 / L3", f"{fmt(f['I_L1_A'], 3)} / {fmt(f['I_L2_A'], 3)} / {fmt(f['I_L3_A'], 3)} A"),
            ("Potencia activa / reactiva", f"{fmt(f['potencia_activa_kW'], 3)} kW / {fmt(f['potencia_reactiva_kVAr'], 3)} kVAr")], 1) + "</div>", unsafe_allow_html=True)
        st.markdown('<div class="caja"><h4>Calculado automáticamente</h4>' + tabla_valores([
            ("Caudal", f"{fmt(f['caudal_GPM'], 2)} GPM"), ("Altura total", f"{fmt(f['head_total_m'], 2)} m"),
            ("Presión disponible / requerida en la entrada (NPSH)", f"{fmt(f['NPSHa_m'], 2)} / {fmt(f['NPSHr_m'], 2)} m"), ("Margen contra cavitación", f"{fmt(f['margen_NPSH_m'], 2)} m (en Latacunga: {fmt(f['margen_lat_m'], 2)} m)"),
            ("Potencia aparente / FP", f"{fmt(f['potencia_aparente_kVA'], 3)} kVA / {fmt(f['factor_potencia'], 3)}"),
            ("Carga del motor", f"{fmt(f['carga_pct'], 0)} % ({fmt(f['I_prom_A'], 2)} A)"),
            ("Desbalance corriente / tensión", f"{fmt(f['desb_corriente_pct'], 2)} % / {fmt(f['desb_tension_pct'], 2)} %"),
            ("Vibración máxima", f"{fmt(f['Vib_max'], 2)} mm/s ({({0: 'normal', 1: 'alarma', 2: 'crítica'}).get(f['zona_vib'], '—')})")]) + "</div>",
            unsafe_allow_html=True)
        st.markdown("#### Resultados")
        p_ia = N.predecir(modelos, lista.iloc[[int(i) - 1]]).iloc[0]
        est_app = p_ia["estado_ia"] or "NORMAL"
        m = f["margen_NPSH_m"]
        if not pd.isna(m) and m <= N.REGLAS["margen_incipiente"]:
            rod = est_app in ("DEGRADACION_RODAMIENTO", "RODAMIENTO_CRITICO", "FALLA_COMBINADA")
            est_app = ("FALLA_COMBINADA" if rod else "CAVITACION_SEVERA") if m <= N.REGLAS["margen_severa"] else (est_app if rod else "CAVITACION_INCIPIENTE")
        t_est = N.evaluar_modelo(modelo_activo, pd.DataFrame([f])) if modelo_activo else None
        err = f["T_F"] - t_est if t_est is not None else None
        rul_r, rul_p = f.get("RUL_rodamiento_h"), p_ia["RUL_ia_h"]
        tarjetas_semaforo([
            ("Temperatura medida (sensor IR)", temp1(f['T_F']), f.get("zona_T"), f"= {temp2(f['T_F'])} · lo que mide el transmisor"),
            ("Temperatura según el modelo", temp1(t_est), None, f"= {temp2(t_est)} · diferencia {fmt(temp_u(f['T_F']) - temp_u(t_est), 1)} {U()}", "#0D3B8C"),
            ("Estado registrado", N.NOMBRE_ESTADO[f["estado"]], None, "recolección de datos", N.COLOR_ESTADO[f["estado"]]),
            ("Estado estimado por la app", N.NOMBRE_ESTADO.get(est_app, est_app), None,
             ("✔ coincide" if est_app == f["estado"] else "✘ difiere") + f" | confianza {fmt(p_ia['prob_ia'] * 100, 0)} %", N.COLOR_ESTADO.get(est_app)),
            ("Vida útil restante", f"{fmt(min(rul_r, N.RUL_TOPE_H), 0)} h" + (" o más" if rul_r >= N.RUL_TOPE_H else ""), None,
             f"calculada por la IA: {fmt(rul_p, 0)} h", "#5B8DEF"),
        ])
        k_u = 1 if U() == "°F" else 1 / 1.8
        texto_tarjeta("La temperatura que mediría el transmisor IR en esta prueba, la que calcula el modelo matemático y el estado del equipo.",
                      f"Si la medición supera a lo calculado en más de {fmt(2 * modelo_activo['rmse_F'] * k_u, 1)} {U()} (dos veces el error típico), el rodamiento "
                      "o el sensor requieren revisión. El «estado estimado por la app» lo calcula la inteligencia artificial solo con variables que se miden.",
                      f"En esta prueba la diferencia es de {fmt(err * k_u if err is not None else None, 1)} {U()}. {html.escape(N.lectura_ecuacion(modelo_activo, U()))}")
        diags = N.diagnosticar(f, equipo)
        if diags:
            tarjetas_diagnostico(diags)
        else:
            st.success("Prueba sin fallas: operación normal.")
    else:
        st.write("Solo se piden las variables que se miden en la bomba. El caudal en GPM, la altura, el margen contra cavitación (con la presión de "
                 "Latacunga), el factor de potencia, los desbalances, el **estado del equipo** y la **vida útil restante** se calculan solos.")
        for k, *_ in CAMPOS_REG:
            st.session_state.setdefault(f"r_{k}", None)
        if st.session_state.pop("limpiar_reg", False):
            for k, *_ in CAMPOS_REG:
                st.session_state[f"r_{k}"] = None
        with st.expander("¿No tienes una medición a mano? Carga un ejemplo real de los datos recolectados"):
            c = st.columns([2, 1])
            est_ej = c[0].selectbox("Estado del ejemplo", [e for e in N.ESTADOS if e not in ("DETENIDA", "MANTENIMIENTO")], format_func=lambda e: N.NOMBRE_ESTADO[e])
            if c[1].button("Cargar ejemplo", width="stretch", help="Llena el formulario con una hora real de los datos recolectados en el estado elegido."):
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
                    cols[j % 4].number_input(etq + (f" ({u_t})" if k == "temperatura_motor_C" else ""), step=paso, key=f"r_{k}", format="%.3f" if paso < 0.01 else None,
                                         help=AYUDA_CAMPO.get(k, ""))
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
    intro("Revisa cualquier registro y explica, en lenguaje sencillo, qué le pasa al equipo, por qué puede estar pasando y qué hacer.",
          "Elige un registro de la lista (por defecto, el último con la bomba funcionando). Si quieres ver solo fallas, filtra por estado.")
    if dop.empty:
        st.info("No hay registros en operación en el conjunto seleccionado.")
    else:
        c = st.columns([2, 3])
        estados_f = c[0].multiselect("Filtrar por estado", [e for e in N.ESTADOS if e not in ("DETENIDA", "MANTENIMIENTO")], default=[],
                                     format_func=lambda e: N.NOMBRE_ESTADO[e], placeholder="Todos los estados")
        dd = (dop[dop["estado"].isin(estados_f)] if estados_f else dop).sort_values("timestamp")
        if dd.empty:
            st.info("No hay registros con ese estado.")
        else:
            opciones = list(dd.index[::-1][:800])
            sel = c[1].selectbox("Registro (del más reciente al más antiguo)", opciones,
                                 format_func=lambda i: f"{d.at[i, 'timestamp']} · {d.at[i, 'estado_txt']}")
            f = d.loc[sel].to_dict()
            st.markdown(f"Estado de este registro: {chip(f['estado'])}", unsafe_allow_html=True)
            tarjetas_estado(f)
            diags = N.diagnosticar(f, equipo)
            if diags:
                tarjetas_diagnostico(diags)
            else:
                st.success("✅ Sin fallas en este registro: el equipo funcionaba normalmente.")
        st.subheader("¿Cuánto tiempo estuvo el equipo en cada estado?")
        t = d["estado"].value_counts().reindex(N.ESTADOS).fillna(0).astype(int).reset_index()
        t.columns = ["estado", "Horas"]
        t["Estado"] = t["estado"].map(N.NOMBRE_ESTADO)
        t["% del tiempo"] = (t["Horas"] / max(len(d), 1) * 100).round(1)
        t["Qué hacer en este estado"] = t["estado"].map(lambda e: N.SOLUCIONES.get(e, {}).get("acciones", ["Nada: seguir vigilando"])[0])
        st.dataframe(t[["Estado", "Horas", "% del tiempo", "Qué hacer en este estado"]], hide_index=True, width="stretch")

# =============================================================================
# ⚙️ Rodamientos
# =============================================================================
if nav == "⚙️ Rodamientos":
    st.subheader("Análisis de vibraciones en rodamientos")
    intro("Calcula las frecuencias a las que vibra un rodamiento cuando tiene un daño (en la jaula, en las pistas o en las bolas) y las compara "
          "con el pico de vibración medido para indicar qué parte podría estar dañada.",
          "Elige el rodamiento (6203 lado bomba, 6202 lado ventilador), deja los datos del motor y escribe lo que mide el vibrómetro: "
          "vibración en mm/s y, si el equipo lo da, el pico de frecuencia en Hz.")
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
                              help="Por defecto, la última vibración en descarga de los datos recolectados")
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
<p style="font-size:.8rem;color:#5A6B88">El diagnóstico final solo sube de nivel con alarma o crítico en mm/s, o con un pico que coincida con una frecuencia de falla; «Atención» por sí sola sigue siendo condición normal. La frecuencia identifica una posible fuente; confirme con tendencia, armónicos, bandas laterales y condiciones de montaje/lubricación.</p></div>""",
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
        st.altair_chart(alt.Chart(h).mark_line(point=True).encode(x=alt.X("Fecha:O", title="Fecha"), y=alt.Y("mm/s:Q"), color=alt.Color("Serie:N", scale=alt.Scale(range=PALETA)),
                                                                  tooltip=list(h.columns)).properties(height=240), width="stretch")
    with st.expander("Notas sobre las fórmulas utilizadas"):
        st.markdown("- **FTF** = ½·fr·(1 − d/D·cos α), con el ángulo convertido a radianes.\n"
                    "- **BPFO** = n/2·fr·(1 − d/D·cos α);  **BPFI** = n/2·fr·(1 + d/D·cos α).\n"
                    "- **BSF** = D/(2d)·fr·(1 − (d/D·cos α)²).\n"
                    "- Las fórmulas se verificaron frente a la hoja de cálculo de referencia; se corrigieron el uso de radianes en FTF, "
                    "el intercambio entre BSF y BPFI y la referencia del 4×. Valores por defecto del motor real: 2 polos, 3450 rpm.")

# =============================================================================
# 💧 Cavitación
# =============================================================================
if nav == "💧 Cavitación":
    st.subheader("Diagnóstico automático de cavitación – bomba centrífuga")
    intro("Detecta cavitación: burbujas de vapor que se forman en la entrada de la bomba cuando llega poca presión y que, al reventar, "
          "dañan el impulsor y hacen vibrar la bomba. Usa la frecuencia de paso de álabes (BPF = álabes × rpm / 60) y la vibración medida.",
          "Deja los datos de placa y escribe lo que mide el vibrómetro: la vibración global y la amplitud en la frecuencia BPF (en condición "
          "normal y ahora). Abajo verás también cómo afecta la altitud de Latacunga.")
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
                             help="Por defecto, la última vibración en succión de los datos recolectados")
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
    st.subheader("Margen NPSH: datos recolectados (nivel del mar) vs presión real de Latacunga")
    patm = N.p_atm_kpa(equipo)
    op_b = dbase[dbase["estado_bomba"] == 1].copy()
    op_b["Estado en Latacunga"] = [N.NOMBRE_ESTADO[N.estado_por_reglas(m, h, True)] for m, h in zip(op_b["margen_lat_m"], op_b["health_index_rodamiento"])]
    cambian = int((op_b["Estado en Latacunga"] != op_b["estado_txt"]).sum())
    tarjetas_semaforo([("Presión atmosférica de la data", "101,3 kPa", None, "nivel del mar", "#5B8DEF"),
                       ("Presión en Latacunga", f"{fmt(patm)} kPa", None, f"{fmt(equipo['altitud_m'], 0)} m s.n.m.", "#0D3B8C"),
                       ("Pérdida de NPSH disponible", f"{fmt((op_b['margen_mar_m'] - op_b['margen_lat_m']).mean(), 2)} m", 1, "por la altitud"),
                       ("Horas que cambiarían de estado", str(cambian), 2 if cambian else 0, f"de {len(op_b)} en operación")])
    pasan = op_b[(op_b["estado"] == "NORMAL") & (op_b["Estado en Latacunga"] != "Normal")]
    inc_sev = op_b[(op_b["estado"] == "CAVITACION_INCIPIENTE") & (op_b["Estado en Latacunga"] == "Cavitación severa")]
    st.info(f"**En palabras:** a la altura de Latacunga llega casi 3 m menos de presión a la entrada de la bomba. Por eso, {len(pasan)} horas que eran "
            f"«Normales» pasarían a tener cavitación y {len(inc_sev)} horas de cavitación incipiente pasarían a ser severas.")
    with st.expander("Ver la tabla completa de cambios de estado"):
        st.dataframe(pd.crosstab(op_b["estado_txt"], op_b["Estado en Latacunga"]).rename_axis(index="Estado a nivel del mar ↓ / en Latacunga →"), width="stretch")
    m = muestra(op_b, 800)
    ch = alt.Chart(m).mark_circle(size=16, opacity=.5).encode(x=alt.X("caudal_GPM:Q", title="Caudal (GPM)", scale=alt.Scale(zero=False)))
    capa = (ch.encode(y=alt.Y("NPSHa_m:Q", title="NPSH (m)"), color=alt.value("#1F6FEB"))
            + ch.encode(y="NPSHa_lat_m:Q", color=alt.value("#F28C28"))
            + alt.Chart(N.CURVA[N.CURVA["Q_gpm"].between(20, 40)]).mark_line(color="#D64545", strokeWidth=3).encode(x="Q_gpm:Q", y="NPSHr_m:Q"))
    st.altair_chart(capa.properties(height=320), width="stretch")
    texto_tarjeta("NPSH disponible de los datos recolectados (azul, nivel del mar) y el mismo cálculo con la presión de Latacunga (naranja), "
                  "frente al NPSH requerido del fabricante (rojo).",
                  "Mientras los puntos estén sobre la línea roja con margen, no hay cavitación. La altitud baja todos los puntos casi 3 m.",
                  f"Con la presión de Latacunga, {cambian} horas de operación cambiarían de estado. Las mediciones nuevas de esta app ya "
                  "usan la presión local; los datos recolectados se conservan como vienen para respetar sus estados registrados.")

# =============================================================================
# 🧠 Estado y RUL
# =============================================================================
if nav == "🧠 Estado y vida útil":
    intro("Explica los estados en los que puede estar el equipo y cuánto tiempo de vida le queda al rodamiento antes de que falle. "
          "Para los registros nuevos, la aplicación reconoce el estado con inteligencia artificial (una red neuronal).",
          "Solo revisar. Primero lee qué significa cada estado; luego mira las gráficas de vida útil.")
    st.markdown("**¿Qué significa cada estado?**")
    st.dataframe(pd.DataFrame([
        ("Normal", "La bomba funciona bien: agua suficiente en la succión y rodamiento sano.", "Seguir vigilando."),
        ("Cavitación incipiente", "Empiezan a formarse burbujas de vapor en la entrada de la bomba porque llega poca presión.", "Revisar el nivel del tanque y el filtro de succión."),
        ("Cavitación severa", "Las burbujas revientan dentro de la bomba: hace ruido como de grava y daña el impulsor.", "Corregir la succión de inmediato; si hay ruido, detener."),
        ("Degradación de rodamiento", "El rodamiento empieza a desgastarse: sube su temperatura y la vibración.", "Programar el cambio de rodamiento."),
        ("Rodamiento crítico", "El rodamiento está por fallar.", "Cambiarlo cuanto antes."),
        ("Falla combinada", "Cavitación y rodamiento dañado al mismo tiempo.", "Detener, corregir la succión y cambiar el rodamiento."),
        ("Detenida", "La bomba está apagada (paradas nocturnas o programadas).", "Nada."),
        ("Mantenimiento", "Parada para cambiar el rodamiento.", "Registrar el trabajo realizado.")],
        columns=["Estado", "Qué significa", "Qué hacer"]), hide_index=True, width="stretch")
    with st.expander("¿Cómo se decide el estado? (reglas)"):
        st.markdown("Se usan dos indicadores:\n\n- **Margen contra cavitación (NPSH):** cuánta presión sobra en la entrada de la bomba para que no se formen burbujas. "
                    "Sobre 0,82 m es seguro; entre 0,107 y 0,82 m hay cavitación incipiente; bajo 0,107 m, severa.\n"
                    "- **Índice de salud del rodamiento:** de 1 (nuevo) a 0 (fallado). Bajo 0,672 hay degradación; bajo 0,385, estado crítico.\n\n"
                    "Estos dos indicadores no se miden directamente en una planta real. Por eso, para los registros nuevos, una **red neuronal (MLP)** "
                    "reconoce el estado a partir de 19 variables que sí se miden (presiones, caudal, vibración, temperatura, corrientes...).")
    st.markdown("**Línea de tiempo de los datos recolectados**")
    tl = muestra(dbase.sort_values("timestamp"), 1500).assign(Fecha=lambda x: pd.to_datetime(x["timestamp"]))
    st.altair_chart(alt.Chart(tl).mark_tick(thickness=2).encode(x=alt.X("Fecha:T", title=None),
                    y=alt.Y("estado_txt:N", sort=DOM_EST, title=None, axis=alt.Axis(labelLimit=220)),
                    color=alt.Color("estado_txt:N", scale=ESCALA_EST, legend=None)).properties(height=240), width="stretch")
    st.subheader("Vida útil restante del rodamiento")
    hi = dbase[dbase["estado_bomba"] == 1][["horas_trabajo_acum_h", "health_index_rodamiento"]]
    c = st.columns(2)
    c[0].markdown("**Índice de salud (1 = nuevo, 0 = fallado)**")
    c[0].altair_chart(alt.Chart(muestra(hi, 800)).mark_line(color="#0D3B8C").encode(
        x=alt.X("horas_trabajo_acum_h:Q", title="Horas de funcionamiento"), y=alt.Y("health_index_rodamiento:Q", title="Índice de salud")).properties(height=230), width="stretch")
    cr = modelos["curva_rul"].rename(columns={"RUL real": "Vida útil real", "RUL MLP": "Calculada por la IA"}).melt("horas", var_name="Serie", value_name="Horas restantes")
    c[1].markdown("**Horas de vida útil restantes: real vs calculada por la IA**")
    c[1].altair_chart(alt.Chart(muestra(cr, 1200)).mark_line().encode(
        x=alt.X("horas:Q", title="Horas de funcionamiento"), y="Horas restantes:Q",
        color=alt.Color("Serie:N", scale=alt.Scale(range=["#F28C28", "#1F6FEB"]), title=None)).properties(height=230), width="stretch")
    texto_tarjeta("Izquierda: cómo se desgasta el rodamiento original. Derecha: las horas que le quedaban de vida y las que calcula la inteligencia artificial.",
                  "Mientras el rodamiento está sano solo se puede decir que le quedan «800 h o más». Cuando empieza a desgastarse (unas 800–900 h antes "
                  "de fallar), la temperatura y la vibración suben y la IA puede calcular cuánto le queda.",
                  f"La IA calcula la vida útil restante con un error promedio de ±{fmt(modelos['mae'], 0)} horas.")
    st.subheader("¿Qué tan bien reconoce la IA los estados?")
    acc = float(np.trace(modelos["matriz"]) / modelos["matriz"].sum())
    st.markdown(f"Se probó la red neuronal con **{modelos['n_test']} horas que no vio durante el entrenamiento**: acertó el estado en el "
                f"**{fmt(acc * 100, 1)} %** de los casos.")
    cm = pd.DataFrame(modelos["matriz"], index=[N.NOMBRE_ESTADO[x] for x in modelos["clases"]], columns=[N.NOMBRE_ESTADO[x] for x in modelos["clases"]])
    cml = cm.rename_axis("Estado real").reset_index().melt("Estado real", var_name="Estado según la IA", value_name="Horas")
    bm = alt.Chart(cml).encode(x=alt.X("Estado según la IA:N", sort=None, axis=alt.Axis(labelLimit=200, labelAngle=-35)),
                               y=alt.Y("Estado real:N", sort=None, axis=alt.Axis(labelLimit=200)))
    st.altair_chart((bm.mark_rect().encode(color=alt.Color("Horas:Q", scale=alt.Scale(scheme="blues"), legend=None))
                     + bm.mark_text(fontSize=13).encode(text="Horas:Q")).properties(height=340), width="stretch")
    st.caption("Cada fila es el estado real y cada columna lo que dijo la IA. Los números en la diagonal son aciertos; fuera de ella, confusiones.")
    with st.expander("Detalle técnico de las métricas"):
        rep_ = pd.DataFrame(modelos["reporte"]).T
        rep_ = rep_[rep_.index.isin(modelos["clases"])].rename(index=N.NOMBRE_ESTADO)
        st.dataframe(rep_.rename(columns={"precision": "Precisión", "recall": "Sensibilidad", "f1-score": "F1", "support": "Casos"}).round(3), width="stretch")
        st.dataframe(pd.DataFrame([("MLP de referencia (TensorFlow)", 0.966, 15.4, 0.962), ("LSTM de referencia (TensorFlow)", 0.646, 6.9, 0.993),
                                   ("MLP de esta aplicación", round(modelos["f1"], 3), round(modelos["mae"], 1), round(modelos["r2"], 3))],
                                  columns=["Modelo", "F1 macro (estado)", "Error medio vida útil (h)", "R² vida útil"]), hide_index=True, width="stretch")
        st.markdown("- Hay un solo ciclo de desgaste hasta la falla, por lo que las métricas de vida útil son optimistas.\n"
                    "- Los estados con pocas horas (cavitación, falla combinada) dan métricas menos estables.")

# =============================================================================
# 🛠️ Mantenimiento
# =============================================================================
if nav == "🛠️ Mantenimiento":
    intro("Indica cuándo cambiar el rodamiento (según su vida útil restante) y lleva el control de las tareas de mantenimiento preventivo.",
          "Revisa la vida útil restante. Cuando realices una tarea, regístrala abajo para que el sistema calcule la próxima fecha.")
    horo_ef = float(mant.get("horometro_h") or 0) or float(dbase["horas_trabajo_acum_h"].max())
    if len(dop):
        u = dop.sort_values("timestamp").iloc[-1]
        rul = u.get("RUL_h")
        horas_dia = (dbase["estado_bomba"] == 1).sum() / max(pd.to_datetime(dbase["timestamp"]).dt.date.nunique(), 1)
        dias = rul / horas_dia if rul is not None and not pd.isna(rul) else None
        tarjetas_semaforo([
            ("Vida útil restante del rodamiento", f"{fmt(rul, 0)} h" if dias is not None else "—",
             None if dias is None else 2 if rul <= equipo["rul_aviso_h"] / 4 else 1 if rul <= equipo["rul_aviso_h"] else 0,
             f"≈ {fmt(dias, 0)} días trabajando {fmt(horas_dia, 0)} h al día"),
            ("Horas de funcionamiento", f"{fmt(horo_ef, 0)} h", None, "horómetro de la bomba", "#0D3B8C"),
            ("Estado actual", N.NOMBRE_ESTADO.get(u["estado"], u["estado"]), None, "último registro en operación", N.COLOR_ESTADO.get(u["estado"]))])
        if rul is not None and not pd.isna(rul) and rul <= equipo["rul_aviso_h"]:
            st.warning(f"Programar el cambio de rodamiento ({equipo['rod_DE']} lado bomba / {equipo['rod_NDE']} lado ventilador) en los próximos {fmt(dias, 0)} días.")
        ev = dbase[dbase["evento_mantenimiento"].notna()][["timestamp", "horas_trabajo_acum_h", "evento_mantenimiento"]]
        if len(ev):
            st.caption("Mantenimientos en los datos recolectados: " + "; ".join(f"{r.timestamp[:10]}: cambio de rodamiento a las {r.horas_trabajo_acum_h:.0f} h" for r in ev.itertuples()))
    st.subheader("Plan de mantenimiento preventivo")
    c = st.columns(3)
    c[0].metric("Tareas vencidas", int((mant_estado["nivel"] == 2).sum()))
    c[1].metric("Próximas a vencer", int((mant_estado["nivel"] == 1).sum()))
    c[2].metric("Aún sin registrar", int((mant_estado["nivel"] == 3).sum()))
    if len(mant_estado):
        v = mant_estado.copy()
        v["Situación"] = v["nivel"].map({0: "🟢 Al día", 1: "🟡 Próxima", 2: "🔴 Vencida", 3: "⚪ Sin registro previo"})
        st.dataframe(v[["Situación", "Tarea", "Frecuencia", "Última vez", "Estado"]], hide_index=True, width="stretch")
    with st.form("form_mant", clear_on_submit=True):
        st.markdown("**Registrar un mantenimiento realizado**")
        c = st.columns([3, 1, 1])
        tarea = c[0].selectbox("Tarea realizada", [t["Tarea"] for t in mant["tareas"]] + ["Cambio de rodamiento", "Otra (correctiva)"])
        fecha = c[1].date_input("Fecha", value=datetime.now().date())
        resp = c[2].selectbox("Responsable", [o["Nombre"] for o in equipo.get("operadores", []) if o.get("Nombre")] or ["—"])
        obs = st.text_input("Observaciones (qué se encontró, repuestos usados)")
        if st.form_submit_button("Guardar mantenimiento", type="primary"):
            for t in mant["tareas"]:
                if t["Tarea"] == tarea:
                    t["Ultima_fecha"], t["Ultima_horas"] = str(fecha), horo_ef
            mant["historial"] = [{"Fecha": str(fecha), "Tarea": tarea, "Responsable": resp, "Horas": horo_ef, "Observaciones": obs}] + mant.get("historial", [])
            N.guardar_json(N.ARCH_MANT, mant)
            st.session_state["msg"] = "Mantenimiento registrado"
            st.rerun()
    c = st.columns([2, 1])
    horo = c[0].number_input("Horómetro de la bomba (h)", value=horo_ef, step=1.0,
                             help="Horas totales de funcionamiento. Por defecto se toman de los datos recolectados.")
    if c[1].button("Actualizar horómetro"):
        mant["horometro_h"] = horo
        N.guardar_json(N.ARCH_MANT, mant)
        st.rerun()
    if mant.get("historial"):
        st.dataframe(pd.DataFrame(mant["historial"]), hide_index=True, width="stretch")

# =============================================================================
# 📊 Gráficas
# =============================================================================
if nav == "📊 Gráficas":
    st.subheader("Gráficas con interpretación")
    intro("Muestra los datos recolectados en gráficas, cada una con su explicación: qué muestra, cómo se lee y qué dicen los datos.",
          "Elige un tema (hidráulica, temperatura, vibraciones, eléctrico o mapas de calor) y lee el recuadro debajo de cada gráfica.")
    if dop.empty:
        st.info("No hay datos en operación en el conjunto seleccionado.")
    else:
        sec = st.radio("Sección", ["💧 Hidráulica", "🌡️ Térmico", "📳 Vibraciones", "⚡ Eléctrico", "🟥 Mapas de calor"], horizontal=True, label_visibility="collapsed")
        if len(dop) > 600:
            st.caption(f"Las gráficas de puntos muestran 600 de {len(dop)} registros en operación; los cálculos usan todos.")
        m = muestra(dop.sort_values("timestamp")).assign(Fecha=lambda x: pd.to_datetime(x["timestamp"]))
        if sec == "💧 Hidráulica":
            q = np.linspace(0, 80, 321)
            q_lo, q_hi = max(0.0, float(dop["caudal_GPM"].min()) - 3), float(dop["caudal_GPM"].max()) + 3
            st.altair_chart((alt.Chart(pd.DataFrame({"Q": q, "H": N.h_ref(q)}).query("Q >= @q_lo and Q <= @q_hi")).mark_line(color="#0A1F44", strokeWidth=3).encode(x=alt.X("Q:Q", title="Caudal (GPM)", scale=alt.Scale(domain=[q_lo, q_hi])), y=alt.Y("H:Q", title="Altura (m)", scale=alt.Scale(zero=False)))
                             + alt.Chart(m).mark_circle(size=25, opacity=.6).encode(x="caudal_GPM:Q", y="head_total_m:Q", color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado"))).properties(height=330), width="stretch")
            texto_tarjeta("Curva H–Q del fabricante (negra) y los puntos de operación de la data, coloreados por estado.",
                          "Los puntos sobre la curva indican desempeño normal; por debajo, pérdida de altura por desgaste o cavitación.",
                          f"Error de altura medio: {fmt(dop['E_H_pct'].mean())} %. Caudal entre {fmt(dop['caudal_GPM'].min())} y {fmt(dop['caudal_GPM'].max())} GPM.")
            st.altair_chart(alt.Chart(m).mark_circle(size=20).encode(x=alt.X("Fecha:T", title=None), y=alt.Y("margen_NPSH_m:Q", title="Margen contra cavitación (m)"),
                                                                     color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado")).properties(height=260)
                            + alt.Chart(pd.DataFrame({"y": [N.REGLAS["margen_incipiente"], N.REGLAS["margen_severa"]]})).mark_rule(strokeDash=[6, 4], color="#D64545").encode(y="y:Q"), width="stretch")
            texto_tarjeta("Margen NPSH (NPSHa − NPSHr) en el tiempo, con los umbrales de estado (0,82 m incipiente; 0,107 m severa).",
                          "Las caídas bruscas son los episodios de cavitación inducidos por nivel bajo o restricción en la succión.",
                          f"{int((dop['margen_NPSH_m'] <= N.REGLAS['margen_incipiente']).sum())} horas bajo 0,82 m.")
        if sec == "🌡️ Térmico":
            st.altair_chart(alt.Chart(m).mark_boxplot(extent="min-max").encode(x=alt.X("estado_txt:N", sort=DOM_EST, title=None), y=alt.Y("T_U:Q", title=f"Temperatura del rodamiento ({U()})", scale=alt.Scale(zero=False)),
                                                                              color=alt.Color("estado_txt:N", scale=ESCALA_EST, legend=None)).properties(height=320), width="stretch")
            med = dop.groupby("estado_txt")["T_U"].median()
            texto_tarjeta("Cómo varía la temperatura del rodamiento en cada estado del equipo.",
                          "Si las cajas de los estados de rodamiento están más arriba que la de Normal, la temperatura es un buen indicador para el transmisor IR.",
                          " | ".join(f"{k}: {fmt(v)} {U()}" for k, v in med.items()))
            cuenta, bordes = np.histogram(dop["T_U"].dropna(), bins=30)
            hb = pd.DataFrame({"x0": bordes[:-1], "x1": bordes[1:], "n": cuenta})
            st.altair_chart((alt.Chart(hb).mark_rect(color="#1F6FEB").encode(x=alt.X("x0:Q", title=f"Temperatura del rodamiento ({U()})", scale=alt.Scale(zero=False)), x2="x1:Q", y=alt.Y("n:Q", title="Horas"), y2=alt.datum(0))
                             + alt.Chart(pd.DataFrame({"x": [temp_u(N.c_a_f(equipo["alarma_C"])), temp_u(N.c_a_f(equipo["disparo_C"]))]})).mark_rule(strokeDash=[6, 4], color="#D64545", strokeWidth=2).encode(x="x:Q")).properties(height=250), width="stretch")
            texto_tarjeta("Cuántas horas se midió cada temperatura, con la alarma y el disparo.", "Define el rango que debe cubrir el transmisor.",
                          f"Mínimo {temp(dop['T_F'].min())}, máximo {temp(dop['T_F'].max())}; el 95 % de las horas estuvo bajo {temp(np.percentile(dop['T_F'].dropna(), 95))}.")
            sc = alt.Chart(m).mark_circle(size=20, opacity=.6).encode(x=alt.X("vibracion_descarga_mm_s:Q", title="Vibración en descarga (mm/s)"), y=alt.Y("T_U:Q", title=U(), scale=alt.Scale(zero=False)),
                                                                      color=alt.Color("estado_txt:N", scale=ESCALA_EST, title="Estado"))
            st.altair_chart((sc + sc.transform_regression("vibracion_descarga_mm_s", "T_U").mark_line(color="#0A1F44")).properties(height=280), width="stretch")
            r = dop["T_F"].corr(dop["vibracion_descarga_mm_s"])
            texto_tarjeta("Temperatura frente a vibración.", "Un rodamiento que se degrada vibra y se calienta a la vez.", f"Correlación r = {fmt(r, 2)}.")
        if sec == "📳 Vibraciones":
            lv = m.melt(id_vars=["Fecha", "estado_txt"], value_vars=["vibracion_succion_mm_s", "vibracion_descarga_mm_s"], var_name="Punto", value_name="mm/s")
            lv["Punto"] = lv["Punto"].map({"vibracion_succion_mm_s": "Succión", "vibracion_descarga_mm_s": "Descarga"})
            zonas = pd.DataFrame({"y0": [0, equipo["iso_A"], equipo["iso_B"], equipo["iso_C"]], "y1": [equipo["iso_A"], equipo["iso_B"], equipo["iso_C"], max(8, lv["mm/s"].max())], "Zona": ["Normal", "Atención", "Alarma", "Crítico"]})
            st.altair_chart((alt.Chart(zonas).mark_rect(opacity=.13).encode(y="y0:Q", y2="y1:Q", color=alt.Color("Zona:N", scale=alt.Scale(domain=["Normal", "Atención", "Alarma", "Crítico"], range=["#2E9E5B", "#F2B705", "#F28C28", "#D64545"])))
                             + alt.Chart(lv).mark_circle(size=12).encode(x=alt.X("Fecha:T", title=None), y=alt.Y("mm/s:Q"), shape="Punto:N", color=alt.value("#0A1F44"))).properties(height=320), width="stretch")
            texto_tarjeta("Vibración global en succión y descarga sobre las zonas de severidad (1,4 / 2,8 / 4,5 mm/s).", "Verde: normal; amarillo: atención; naranja: alarma; rojo: crítico.",
                          f"{int((dop['zona_vib'] >= 1).sum())} horas sobre el límite de alarma. Para el espectro y las frecuencias de falla usa «⚙️ Rodamientos» y «💧 Cavitación».")
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
            dm = dop.dropna(subset=[vx, vy, "T_U"])
            cel = dm.groupby([pd.cut(dm[vx], 18), pd.cut(dm[vy], 18)], observed=True)["T_U"].agg(["mean", "count"]).reset_index()
            cel = pd.DataFrame({"x0": cel[vx].map(lambda i: i.left), "x1": cel[vx].map(lambda i: i.right), "y0": cel[vy].map(lambda i: i.left),
                                "y1": cel[vy].map(lambda i: i.right), "T": cel["mean"], "n": cel["count"]}).astype(float)
            st.altair_chart(alt.Chart(cel).mark_rect().encode(x=alt.X("x0:Q", title=N.ETIQUETAS.get(vx, vx), scale=alt.Scale(zero=False)), x2="x1:Q",
                                                              y=alt.Y("y0:Q", title=N.ETIQUETAS.get(vy, vy), scale=alt.Scale(zero=False)), y2="y1:Q",
                                                              color=alt.Color("T:Q", scale=alt.Scale(scheme="turbo"), title=f"T media ({U()})"),
                                                              tooltip=[alt.Tooltip("T:Q", format=".1f"), "n:Q"]).properties(height=360), width="stretch")
            texto_tarjeta("Temperatura media del rodamiento en cada combinación de dos variables.", "Las celdas rojas son las condiciones que más calientan el rodamiento.",
                          f"La temperatura media va de {fmt(cel['T'].min())} a {fmt(cel['T'].max())} {U()}.")
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
    intro("Construye la <b>ecuación matemática</b> que calcula la temperatura del rodamiento a partir de otras variables que se miden en la bomba "
          "(vibración, eficiencia, nivel del tanque...). Con ella se sabe qué temperatura es «normal» para cada condición de trabajo, "
          "y se definen los requisitos del transmisor IR.",
          "Normalmente nada: la aplicación ya eligió las mejores variables. Si quieres probar otras, cámbialas en «Variables del modelo» "
          "y pulsa «Usar este modelo en toda la aplicación».")
    if len(dop) < 10:
        st.info("Se necesitan al menos 10 registros en operación.")
    else:
        num = dop[[c for c in N.CANDIDATAS if dop[c].std() > 0] + ["T_F"]].astype(float)
        corr = num.corr()
        rk = pd.DataFrame({"Variable": [c for c in num.columns if c != "T_F"]})
        rk["Variable medida"] = rk["Variable"].map(lambda v: N.ETIQUETAS.get(v, v))
        rk["r"] = rk["Variable"].map(corr["T_F"])
        rk["Relación con la temperatura"] = rk["r"].map(lambda r: ("Fuerte" if abs(r) >= .7 else "Moderada" if abs(r) >= .4 else "Débil" if abs(r) >= .2 else "Casi nula")
                                                          + (", sube con ella" if r > 0 else ", baja cuando ella sube"))
        rk = rk.reindex(rk["r"].abs().sort_values(ascending=False).index).reset_index(drop=True)
        st.markdown("**Paso 1. ¿Qué variables se relacionan con la temperatura del rodamiento?**")
        c = st.columns([3, 2])
        c[0].altair_chart(alt.Chart(rk).mark_bar().encode(x=alt.X("r:Q", title="Coeficiente de correlación r (−1 a +1)", scale=alt.Scale(domain=[-1, 1])),
                                                          y=alt.Y("Variable medida:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
                                                          color=alt.condition(alt.datum.r > 0, alt.value("#1F6FEB"), alt.value("#D64545"))).properties(height=420), width="stretch")
        c[1].dataframe(rk[["Variable medida", "Relación con la temperatura"]], hide_index=True, width="stretch", height=420)
        st.caption("Barras azules: cuando esa variable sube, la temperatura también. Rojas: cuando sube, la temperatura baja. Cuanto más larga la barra, más útil para el modelo.")
        st.markdown("**Paso 2. Variables elegidas para la ecuación**")
        vars_x = st.multiselect("Variables del modelo", list(rk["Variable"]), default=modelo_activo["variables"],
                                format_func=lambda v: N.ETIQUETAS.get(v, v), placeholder="Elige al menos una variable",
                                help="Se eligen las de barra más larga que no repitan información entre sí.")
        poli = st.toggle("Opción avanzada: agregar términos al cuadrado (modelo polinómico)", value=False,
                         help="Puede ajustar curvas, pero la ecuación es más difícil de interpretar. Úsalo solo si baja el error en datos nuevos.")
        if vars_x:
            terms = vars_x + ([f"{v}^2" for v in vars_x] if poli else [])
            dm = dop.dropna(subset=vars_x + ["T_F"]).sort_values("timestamp")
            X = N.matriz_terminos(dm, terms)
            r_all = N.regresion(X.values, dm["T_F"].values)
            corte = int(len(dm) * 0.7)
            r_70 = N.regresion(X.iloc[:corte].values, dm["T_F"].iloc[:corte].values)
            pred_val = np.column_stack([np.ones(len(dm) - corte), X.iloc[corte:].values]) @ r_70["beta"]
            rmse_val = math.sqrt(float(((dm["T_F"].values[corte:] - pred_val) ** 2).mean()))
            mod = {"nombre": "Polinómico" if poli else "Lineal", "objetivo": "T_F", "variables": vars_x, "terminos": terms,
                   "intercepto": float(r_all["beta"][0]), "coeficientes": [float(b) for b in r_all["beta"][1:]], "r2": r_all["r2"],
                   "rmse_F": r_all["rmse"], "rmse_validacion_F": rmse_val, "n": len(dm), "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")}
            mod["ecuacion"] = N.ecuaciones(mod)[0]
            eq_f, eq_c = N.ecuaciones(mod)
            st.markdown("**Paso 3. La ecuación obtenida (en las dos unidades)**")
            st.code(eq_f + "\n" + eq_c, language=None)
            st.caption("Donde: " + N.leyenda_ecuacion(mod))
            st.info(N.lectura_ecuacion(mod, U()))
            k = 1 if U() == "°F" else 1 / 1.8
            tarjetas_semaforo([("¿Cuánto explica el modelo?", f"{fmt(r_all['r2'] * 100, 0)} %", None, "de los cambios de temperatura (R²)", "#0D3B8C"),
                               ("Error típico", f"±{fmt(r_all['rmse'] * k, 1)} {U()}", None, "con todos los datos (RMSE)", "#1F6FEB"),
                               ("Error con datos nuevos", f"±{fmt(rmse_val * k, 1)} {U()}", None, "entrenado con el 70 %, probado con el 30 % restante", "#5B8DEF")])
            st.caption("R² cerca de 100 % = el modelo explica casi todo. El error típico indica cuántos grados se equivoca en promedio. "
                       "El error con datos nuevos es mayor porque las fallas ocurren al final del período y el modelo no las vio al aprender.")
            pred = np.column_stack([np.ones(len(dm)), X.values]) @ r_all["beta"]
            cp = muestra(pd.DataFrame({"Medida": temp_u(dm["T_F"].values), "Calculada": temp_u(pred), "Estado": dm["estado_txt"].values}))
            lo, hi = float(cp[["Medida", "Calculada"]].min().min()), float(cp[["Medida", "Calculada"]].max().max())
            st.altair_chart((alt.Chart(cp).mark_circle(size=25, opacity=.6).encode(
                x=alt.X("Medida:Q", title=f"Temperatura medida por el sensor IR ({U()})", scale=alt.Scale(domain=[lo, hi])),
                y=alt.Y("Calculada:Q", title=f"Temperatura calculada por la ecuación ({U()})", scale=alt.Scale(domain=[lo, hi])),
                color=alt.Color("Estado:N", scale=ESCALA_EST))
                + alt.Chart(pd.DataFrame({"a": [lo, hi]})).mark_line(color="gray", strokeDash=[5, 5]).encode(x="a:Q", y="a:Q")).properties(height=340), width="stretch")
            st.caption("Cada punto es una hora de operación. Si la ecuación fuera perfecta, todos los puntos estarían sobre la línea punteada.")
            with st.expander("Detalle estadístico (avanzado)"):
                tc = pd.DataFrame({"Término": ["Constante"] + [N.ETIQUETAS.get(t, t) for t in terms], "Coeficiente (°F)": r_all["beta"],
                                   "p-valor": r_all["p"], "VIF": [np.nan] + N.vif(X)})
                st.dataframe(tc.round(5), hide_index=True, width="stretch")
                st.caption("p-valor < 0,05: la variable sí aporta. VIF < 5: no repite información de otra variable.")
            if st.button("Usar este modelo en toda la aplicación", type="primary"):
                N.guardar_json(N.ARCH_MODELO, mod)
                st.session_state["msg"] = "Modelo guardado"
                st.rerun()

# =============================================================================
# 🎯 Estimador
# =============================================================================
if nav == "🧮 Calculadora de temperatura":
    intro("Calcula la temperatura que <b>debería tener</b> el rodamiento según cómo está trabajando la bomba, usando la ecuación del modelo. "
          "Sirve para comprobar la lectura del transmisor IR: si el sensor marca mucho más de lo calculado, hay un problema en el rodamiento "
          "(o en el sensor).",
          "Escribe los valores actuales de la bomba (vienen llenos con el último registro). Opcionalmente, escribe lo que marca el sensor IR "
          "para compararlo.")
    if not modelo_activo:
        st.info("Primero guarda un modelo en «🔍 Modelo».")
    else:
        eq_f, eq_c = N.ecuaciones(modelo_activo)
        st.code(eq_f + "\n" + eq_c, language=None)
        st.caption("Donde: " + N.leyenda_ecuacion(modelo_activo))
        nec = []
        for v in modelo_activo["variables"]:
            for x in N.DEPENDE.get(v, [v]):
                if x not in nec:
                    nec.append(x)
        ent = {c: np.nan for c in N.COLS}
        ent.update({"timestamp": "", "Origen": N.ORIGEN_NUEVO, "Operador": "", "Observaciones": "", "estado_bomba": 1})
        ult = dop.sort_values("timestamp").iloc[-1] if len(dop) else dbase.iloc[-1]
        cols = st.columns(3)
        for i, v in enumerate(nec):
            ent[v] = cols[i % 3].number_input(N.ETIQUETAS.get(v, v), value=float(ult[v]), key=f"e_{v}", help=AYUDA_CAMPO.get(v, ""))
        f = N.derivar(N.normalizar(pd.DataFrame([ent])), equipo)
        t = N.evaluar_modelo(modelo_activo, f)
        z = 0 if N.f_a_c(t) < equipo["alarma_C"] else 1 if N.f_a_c(t) < equipo["disparo_C"] else 2
        tarjetas_semaforo([("Temperatura calculada del rodamiento", temp1(t), z, f"= {temp2(t)} · alarma a {temp1(N.c_a_f(equipo['alarma_C']), 0)}")])
        lect = st.number_input(f"Lectura del sensor IR ({U()}), opcional", value=None, step=0.1,
                               help="Escribe lo que marca el transmisor o termómetro infrarrojo en la tapa del rodamiento.")
        if lect is not None:
            lect_f = lect if U() == "°F" else N.c_a_f(lect)
            dif = lect_f - t
            k = 1 if U() == "°F" else 1 / 1.8
            if abs(dif) > 2 * modelo_activo["rmse_F"]:
                st.warning(f"El sensor marca {fmt(dif * k, 1)} {U()} {'más' if dif > 0 else 'menos'} de lo esperado (más de 2 veces el error típico). "
                           "Revisa el rodamiento (lubricación, desgaste) o el sensor (emisividad, lente sucio, alineación).")
            else:
                st.success(f"La lectura es coherente con lo esperado (diferencia {fmt(dif * k, 1)} {U()}).")

# =============================================================================
# 🌡️ Transmisor IR
# =============================================================================
if nav == "🌡️ Transmisor IR":
    intro("Elige el transmisor de temperatura infrarrojo que se debe comprar para vigilar los rodamientos. Compara los modelos de los catálogos "
          "con los requisitos que salen de los datos recolectados y de la instalación.",
          "Revisa los criterios (si no sabes qué poner, deja los valores recomendados) y mira el resultado en «2. Evaluación del catálogo» "
          "y el transmisor recomendado con su hoja de datos.")
    st.subheader("1. Criterios de selección")
    st.dataframe(pd.DataFrame([
        ("Rango de medición", "Temperaturas mínima y máxima que puede leer el sensor.", "Debe cubrir la temperatura más alta del rodamiento con margen.", "0 a 150 °C"),
        ("Relación óptica D:S", "Distancia ÷ diámetro de la zona que mide. 15:1 = a 15 cm mide un círculo de 1 cm.", "La tapa del rodamiento es pequeña; si el círculo es más grande, mide también el fondo.", "15:1 o más"),
        ("T. ambiente del cabezal", "Temperatura máxima que soporta la cabeza del sensor junto al motor.", "El motor es abierto y expulsa aire caliente.", "85 °C o más"),
        ("Tiempo de respuesta", "Cuánto tarda el sensor en mostrar un cambio.", "El rodamiento se calienta en minutos; cualquier sensor rápido sirve.", "150 ms o menos"),
        ("Exactitud", "Cuántos grados puede equivocarse el sensor.", "Debe ser menor que la diferencia entre operación normal y desgaste.", "±2 °C"),
        ("Salida", "Tipo de señal eléctrica que entrega el sensor al PLC.", "4–20 mA no se afecta por el largo del cable.", "4–20 mA"),
        ("Diámetro de la tapa y distancia", "Tamaño de la zona útil del rodamiento y a qué distancia se montará el sensor.", "Con ellos se calcula el tamaño del círculo que mide.", "30 mm a 120 mm")],
        columns=["Criterio", "Qué significa", "Por qué importa", "Valor recomendado"]), hide_index=True, width="stretch")
    with st.form("form_ir"):
        st.caption("Si no sabes qué poner, deja los valores recomendados.")
        c = st.columns(4)
        e = {}
        e["ir_rango_max_C"] = c[0].number_input("Temperatura máxima a medir (°C)", value=float(equipo["ir_rango_max_C"]), help="Recomendado: 150 °C.")
        e["ir_ds_min"] = c[1].number_input("Relación óptica D:S mínima", value=float(equipo["ir_ds_min"]), help="Recomendado: 15 (es decir 15:1).")
        e["ir_cabezal_min_C"] = c[2].number_input("Temperatura que debe soportar el cabezal (°C)", value=float(equipo["ir_cabezal_min_C"]), help="Recomendado: 85 °C.")
        e["ir_resp_max_ms"] = c[3].number_input("Tiempo de respuesta máximo (ms)", value=float(equipo["ir_resp_max_ms"]), help="Recomendado: 150 ms.")
        c = st.columns(4)
        e["ir_salida"] = c[0].selectbox("Tipo de salida", ["4–20 mA", "0–10 V"], index=["4–20 mA", "0–10 V"].index(equipo["ir_salida"]),
                                        help="4–20 mA (recomendado) necesita el módulo SM 1231 en el PLC; 0–10 V entra directo a la CPU 1214C.")
        e["ir_exactitud_C"] = c[1].number_input("Exactitud mínima (± °C)", value=float(equipo["ir_exactitud_C"]), step=0.5, help="Recomendado: 2 °C.")
        e["ir_d_objetivo_mm"] = c[2].number_input("Diámetro útil de la tapa del rodamiento (mm)", value=float(equipo["ir_d_objetivo_mm"]),
                                                  help="Mídelo con un calibrador o regla en la tapa del motor. Recomendado: 30 mm.")
        e["ir_distancia_mm"] = c[3].number_input("Distancia de montaje del sensor (mm)", value=float(equipo["ir_distancia_mm"]),
                                                 help="A qué distancia de la tapa se colocará el sensor. Recomendado: 100 a 150 mm.")
        if st.form_submit_button("Guardar criterios", type="primary"):
            N.guardar_json(N.ARCH_EQUIPO, {**equipo, **e})
            st.session_state["msg"] = "Criterios guardados"
            st.rerun()
    r = req_ir
    st.caption(f"Con estos criterios: rango de {fmt(r['rango_min_C'], 0)} a {fmt(r['rango_max_C'], 0)} °C (la máxima registrada fue {temp(N.c_a_f(r['t_max_obs_C'])) if r['t_max_obs_C'] else '—'}); "
               f"el círculo medido debe ser de {fmt(r['spot_max_mm'])} mm o menos a {fmt(r['distancia_mm'], 0)} mm, por eso se pide D:S ≥ {fmt(r['ds_req'])}:1.")
    st.subheader("2. Evaluación del catálogo")
    st.caption("✔ = cumple el criterio · ✘ = no cumple. «Punto medido» es el diámetro del círculo que mide el sensor a la distancia de montaje.")
    st.dataframe(tabla_ir.drop(columns=["Marca"]), hide_index=True, width="stretch",
                 column_config={"Puntaje": st.column_config.ProgressColumn("Puntaje", min_value=0, max_value=100, format="%.0f")})
    ok = tabla_ir[tabla_ir["Cumple todo"]]
    if len(ok):
        el = next(c for c in catalogo if c["Modelo"] == ok.iloc[0]["Modelo"])
        st.markdown(f"""<div class="recomendado"><div class="k">Transmisor recomendado</div><h2>{html.escape(el['Marca'])} {html.escape(el['Modelo'])}</h2>
<span class="badge">Puntaje {fmt(ok.iloc[0]['Puntaje'], 0)}</span><span class="badge">D:S {fmt(el['DS'], 0)}:1</span><span class="badge">Cabezal {el['Tcab_C']} °C</span>
<p style="margin:.7rem 0 0;color:#E3EEFF">Cumple todos los criterios de selección; mide un punto de {fmt(ok.iloc[0]['Punto medido (mm)'])} mm a {fmt(r['distancia_mm'], 0)} mm.
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
# ▶️ Simulación en vivo (reproduce los datos recolectados hora por hora)
# =============================================================================
if nav == "▶️ Simulación":
    st.subheader("Monitoreo simulado en tiempo real")
    intro("Reproduce los datos recolectados hora por hora, como si llegaran en vivo desde el PLC, para ver cómo reacciona el sistema cuando aparece una falla.",
          "Elige un evento (por ejemplo, una cavitación), las horas a reproducir y pulsa «▶️ Reproducir». Si activas Telegram, llegará la alerta al celular.")
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
                x=alt.X("Fecha:T", title=None), y=alt.Y("T_U:Q", title=U(), scale=alt.Scale(zero=False)),
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
    intro("Muestra todas las mediciones: las recolectadas (4320 horas, solo lectura) y las que tú registras (se pueden corregir o borrar).",
          "Elige qué ver. En los registros nuevos puedes editar una celda, agregar filas con + o borrar filas con Supr; se guarda solo.")
    vista = st.radio("Ver", ["Datos recolectados (solo lectura)", "Registros nuevos (editable)"], horizontal=True)
    if vista.startswith("Datos recolectados"):
        cols = ["timestamp", "estado_txt", "horas_trabajo_acum_h", "caudal_GPM", "presion_succion_PSI", "presion_descarga_PSI", "margen_NPSH_m",
                "margen_lat_m", "vibracion_succion_mm_s", "vibracion_descarga_mm_s", "temperatura_motor_C", "T_F", "I_prom_A", "potencia_activa_kW",
                "factor_potencia", "health_index_rodamiento", "RUL_rodamiento_h", "evento_mantenimiento"]
        est = st.multiselect("Filtrar por estado", N.ESTADOS, format_func=lambda e: N.NOMBRE_ESTADO[e], placeholder="Todos los estados")
        v = dbase[dbase["estado"].isin(est)] if est else dbase
        st.dataframe(v[cols].round(3).rename(columns=lambda c: N.ETIQUETAS.get(c, c)), hide_index=True, width="stretch", height=420)
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
        sub = st.file_uploader("Cargar mediciones desde CSV o Excel (mismos nombres de columna que los datos recolectados)", type=["csv", "xlsx"])
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
    intro("Envía un mensaje al celular (Telegram) cada vez que se registra una falla, con la causa probable y qué hacer.",
          "Crea un bot con @BotFather, pega su token, pulsa «Buscar mi chat ID», activa las alertas y envía un mensaje de prueba.")
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
    st.subheader("Datos del proyecto")
    intro("Muestra los datos del grupo y guarda los límites que usa la aplicación para dar alarmas.",
          "Los integrantes y la asignatura ya están fijos. Los límites técnicos tienen valores recomendados; cámbialos solo si es necesario.")
    st.markdown(f"""<div class="caja"><h4>Grupo de trabajo</h4>{tabla_valores([
        ("Docente responsable", N.DOCENTE), ("Asignatura", N.ASIGNATURA), ("NRC", N.NRC), ("Período", N.PERIODO)], 2)}
<p style="margin:.6rem 0 .2rem;color:#5A6B88">Integrantes</p><ul style="margin:0 0 0 1.2rem">{"".join(f"<li><b>{html.escape(x)}</b></li>" for x in N.INTEGRANTES)}</ul></div>""",
                unsafe_allow_html=True)
    with st.form("form_cfg"):
        e = dict(equipo)
        e["proyecto"] = st.text_area("Título del proyecto", e.get("proyecto", ""), height=70)
        st.markdown("**Límites y datos técnicos**")
        c = st.columns(4)
        e["alarma_C"] = c[0].number_input("Alarma de temperatura del rodamiento (°C)", value=float(e["alarma_C"]), help="Sobre este valor se da aviso. Recomendado: 75 °C (167 °F).")
        e["disparo_C"] = c[1].number_input("Temperatura para detener la bomba (°C)", value=float(e["disparo_C"]), help="Sobre este valor hay que parar. Recomendado: 90 °C (194 °F).")
        e["rul_aviso_h"] = c[2].number_input("Avisar cuando la vida útil restante sea menor a (h)", value=float(e["rul_aviso_h"]), help="Recomendado: 200 h (unos 11 días de trabajo).")
        e["altitud_m"] = c[3].number_input("Altitud del laboratorio (m s.n.m.)", value=float(e["altitud_m"]), help="Latacunga: 2750 m. Se usa para calcular la presión del aire.")
        c = st.columns(4)
        e["motor_i"] = c[0].number_input("Corriente nominal (A)", value=float(e["motor_i"]))
        e["motor_i_sf"] = c[1].number_input("Corriente con SF (A)", value=float(e["motor_i_sf"]))
        e["bomba_alabes"] = c[2].number_input("Álabes del impulsor Z", value=int(e["bomba_alabes"]), min_value=1)
        e["t_agua_C"] = c[3].number_input("Temperatura del agua (°C)", value=float(e["t_agua_C"]))
        c = st.columns(4)
        e["rod_DE"] = c[0].selectbox("Rodamiento DE", list(N.BD_RODAMIENTOS), index=list(N.BD_RODAMIENTOS).index(e["rod_DE"]))
        e["rod_NDE"] = c[1].selectbox("Rodamiento NDE", list(N.BD_RODAMIENTOS), index=list(N.BD_RODAMIENTOS).index(e["rod_NDE"]))
        e["iso_B"] = c[2].number_input("Vibración: alarma sobre (mm/s)", value=float(e["iso_B"]))
        e["iso_C"] = c[3].number_input("Vibración: crítico sobre (mm/s)", value=float(e["iso_C"]))
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
    ax.set_ylabel("°F"), ax.legend(fontsize=6, markerscale=3), ax.grid(alpha=.3), ax.set_title("Temperatura del rodamiento (sensor IR) por estado")
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
    ax.plot(cr["horas"], cr["RUL real"], label="Vida útil real (recortada a 800 h)"), ax.plot(cr["horas"], cr["RUL MLP"], alpha=.7, label="Calculada por la IA")
    ax.set_xlabel("Horas de operación"), ax.set_ylabel("h"), ax.legend(), ax.grid(alpha=.3), ax.set_title("Vida remanente del rodamiento")
    figs.append(("La vida útil restante solo se puede calcular cuando empieza el desgaste.", fig_png(fig)))

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
    p.add_run(f"Departamento de Eléctrica y Electrónica | Ingeniería Electromecánica\nDocente responsable: {N.DOCENTE}\n"
              f"Asignatura: {N.ASIGNATURA} | NRC {N.NRC} | Período: {N.PERIODO}\n")
    p.add_run("Operadores: " + (", ".join(o["Nombre"] for o in equipo.get("operadores", []) if o.get("Nombre")) or "—") + "\n")
    p.add_run(f"Fecha: {datetime.now():%Y-%m-%d %H:%M}")
    tit("1. Datos analizados")
    doc.add_paragraph(f"Datos recolectados de la bomba Goulds 3642: {len(dbase)} registros horarios, {int((dbase['estado_bomba'] == 1).sum())} h en operación. "
                      f"Registros nuevos: {len(dreg)}.")
    cnt = dbase["estado_txt"].value_counts()
    tabla([(k, v, f"{v / len(dbase) * 100:.1f} %") for k, v in cnt.items()], ["Estado", "Horas", "%"])
    tit("2. Resultados")
    for i, (txt, img) in enumerate(figs, 1):
        doc.add_picture(BytesIO(img), width=Cm(15 if i != 3 else 11))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Figura {i}. {txt}").runs[0].italic = True
    tit("3. Modelos")
    tabla([("MLP estado (esta app)", f"F1 macro {modelos['f1']:.3f}"), ("MLP vida útil (esta app)", f"MAE {modelos['mae']:.1f} h; R² {modelos['r2']:.3f}"),
           ("MLP / LSTM de referencia (TensorFlow)", "F1 0,966 / 0,646; RUL R² 0,962 / 0,993")], ["Modelo", "Resultado"])
    if modelo_activo:
        _ef, _ec = N.ecuaciones(modelo_activo)
        pe = doc.add_paragraph("Modelo matemático de la temperatura del rodamiento:\n")
        pe.add_run(_ef + "\n" + _ec).bold = True
        doc.add_paragraph("Donde: " + N.leyenda_ecuacion(modelo_activo) + ". " + N.lectura_ecuacion(modelo_activo))
        doc.add_paragraph(f"R² = {modelo_activo['r2']:.3f}; RMSE = {modelo_activo['rmse_F']:.2f} °F.")
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
    intro("Genera un documento Word con los resultados: datos, gráficas, modelo matemático, inteligencia artificial y transmisor recomendado.",
          "Pulsa «Generar informe» y luego «Descargar informe».")
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

# =============================================================================
# 📖 Glosario
# =============================================================================
if nav == "📖 Glosario":
    st.subheader("Glosario: los términos en palabras sencillas")
    busca = st.text_input("Buscar un término", placeholder="Ejemplo: cavitación")
    G = [
        ("Rodamiento", "Pieza con bolas que permite que el eje del motor gire con poca fricción. Este motor tiene dos: 6203 (lado bomba, DE) y 6202 (lado ventilador, NDE)."),
        ("DE / NDE", "Drive End / Non Drive End: lado del motor que mueve la bomba (DE) y lado opuesto, del ventilador (NDE)."),
        ("Transmisor de temperatura infrarrojo (IR)", "Sensor que mide la temperatura de una superficie sin tocarla, captando el calor que emite, y la envía al PLC como señal eléctrica."),
        ("Escudo o tapa del rodamiento", "La parte metálica del motor que cubre el rodamiento; es donde apunta el sensor IR."),
        ("Emisividad", "Qué tan bien emite calor una superficie (de 0 a 1). La pintura mate es ≈ 0,95; el metal brillante es muy bajo y engaña al sensor. Por eso se pega cinta negra mate."),
        ("Relación óptica D:S", "Distancia ÷ diámetro del círculo que mide el sensor. Con 15:1, a 15 cm mide un círculo de 1 cm."),
        ("4–20 mA", "Señal eléctrica estándar: 4 mA = temperatura mínima, 20 mA = máxima. Menos de 4 mA indica cable roto."),
        ("Modelo matemático", "Ecuación que calcula la temperatura del rodamiento a partir de otras variables medidas."),
        ("Coeficiente de correlación (r)", "Número de −1 a +1 que dice si dos variables suben juntas (+), una sube cuando la otra baja (−) o no se relacionan (≈ 0)."),
        ("R²", "Porcentaje de los cambios de temperatura que explica el modelo. 100 % sería perfecto."),
        ("Error típico (RMSE)", "Cuántos grados se equivoca el modelo en promedio."),
        ("Validación", "Probar el modelo con datos que no usó para aprender, para saber cómo funcionará con datos nuevos."),
        ("Inteligencia artificial / red neuronal MLP", "Programa que aprende de los datos recolectados a reconocer el estado del equipo y a calcular la vida útil restante."),
        ("Vida útil restante (RUL)", "Horas que puede seguir funcionando el rodamiento antes de fallar (Remaining Useful Life)."),
        ("Índice de salud del rodamiento", "Número de 1 (nuevo) a 0 (fallado) que resume el desgaste del rodamiento."),
        ("Cavitación", "Burbujas de vapor que se forman en la entrada de la bomba cuando llega poca presión; al reventar dañan el impulsor y suenan como grava."),
        ("NPSH", "Presión disponible en la entrada de la bomba (NPSHa) y la que la bomba necesita (NPSHr), expresadas en metros de agua."),
        ("Margen contra cavitación", "NPSH disponible − NPSH requerido. Sobre 0,82 m es seguro; bajo 0,107 m hay cavitación severa."),
        ("Altitud y presión atmosférica", "A 2750 m (Latacunga) el aire pesa menos (72,4 kPa frente a 101,3 kPa a nivel del mar), así que llega menos presión a la bomba."),
        ("Vibración RMS (mm/s)", "Valor promedio de la velocidad de vibración. Hasta 2,8 mm/s es normal en esta bomba; sobre 4,5 mm/s es crítico."),
        ("Aceleración (g)", "Vibración medida como aceleración; ayuda a detectar daños pequeños en rodamientos."),
        ("FTF, BPFO, BPFI, BSF", "Frecuencias a las que vibra un rodamiento con daño en la jaula (FTF), pista exterior (BPFO), pista interior (BPFI) o bolas (BSF)."),
        ("BPF", "Frecuencia de paso de álabes = número de álabes × rpm / 60. Si su amplitud sube, puede haber cavitación."),
        ("Curva H–Q", "Curva del fabricante que dice cuánta altura (presión) entrega la bomba para cada caudal."),
        ("Carga del motor", "Corriente medida dividida para la nominal (3,0 A). Sobre 100 % el motor trabaja forzado."),
        ("Desbalance", "Diferencia entre las tres fases de corriente o voltaje. Un desbalance alto calienta el motor."),
        ("Factor de potencia (FP)", "Qué parte de la energía que toma el motor se convierte en trabajo útil (de 0 a 1)."),
        ("PLC S7-1200 / SM 1231", "Controlador que leerá el transmisor. Su CPU 1214C solo lee 0–10 V; para 4–20 mA se agrega el módulo SM 1231."),
        ("PT100", "Sensor de temperatura de contacto, muy exacto; sirve como referencia para comprobar el sensor IR."),
    ]
    for t, dfn in G:
        if not busca or busca.lower() in (t + dfn).lower():
            st.markdown(f'<div class="kv" style="display:block"><b>{html.escape(t)}</b><br><span>{html.escape(dfn)}</span></div>', unsafe_allow_html=True)

st.markdown("""<div class="pie"><b>Universidad de las Fuerzas Armadas ESPE – Sede Latacunga</b><br>
Departamento de Eléctrica y Electrónica | Carrera de Ingeniería Electromecánica</div>""", unsafe_allow_html=True)
