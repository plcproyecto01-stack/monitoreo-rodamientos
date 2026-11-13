# -*- coding: utf-8 -*-
"""Estilos visuales (colores de Ingeniería Electromecánica)."""
CSS = """
<style>
:root { --marino:#0A1F44; --marino-2:#0D3B8C; --electrico:#1F6FEB; --celeste:#00A3FF; --rayo:#F2B705; --fondo:#F4F7FC; }
.block-container { padding-top: 1.2rem; max-width: 1450px; }
.hero { border-radius: 14px; overflow: hidden; margin-bottom: 1.1rem; box-shadow: 0 6px 24px rgba(10,31,68,.18); background:#fff; }
.hero-logos { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:.9rem 1.6rem; background:#fff; flex-wrap:wrap; }
.hero-logos img.espe { height:74px; max-width:100%; object-fit:contain; }
.hero-logos img.em { height:92px; object-fit:contain; }
.hero-rayo { height:6px; background:linear-gradient(90deg, var(--rayo) 0 18%, var(--electrico) 18% 100%); }
.hero-banda { position:relative; padding:1.5rem 1.8rem 1.4rem; color:#fff; overflow:hidden;
  background: radial-gradient(circle at 92% 20%, rgba(0,163,255,.45), transparent 42%),
              linear-gradient(120deg, var(--marino) 0%, var(--marino-2) 58%, var(--electrico) 100%); }
.hero-banda::after { content:"⚡"; position:absolute; right:1.6rem; bottom:-1.6rem; font-size:7.5rem; opacity:.12; }
.hero-carrera { font-size:.95rem; color:#CFE1FF; margin:0 0 .35rem; }
.hero-banda h1 { color:#fff !important; font-size:2.05rem; line-height:1.15; margin:0 0 .45rem; padding:0; font-weight:800; }
.hero-banda p.sub { color:#E3EEFF; margin:0; font-size:1.02rem; max-width:75ch; }
.hero-fichas { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px,1fr)); gap:.8rem; padding:1rem 1.6rem 1.2rem; background:var(--fondo); }
.ficha { background:#fff; border-radius:10px; padding:.75rem 1rem; border-left:5px solid var(--electrico); }
.ficha.docente { border-left-color:var(--rayo); }
.ficha .titulo { font-size:.8rem; color:#5A6B88; margin-bottom:.2rem; }
.ficha .valor { font-size:1.02rem; font-weight:700; color:var(--marino); }
.ficha ul { margin:.1rem 0 0 1rem; padding:0; color:var(--marino); font-weight:600; }
.ficha .vacio { color:#8A9BB8; font-style:italic; }
.stTabs [data-baseweb="tab-list"] { gap:.3rem; background:#fff; padding:.35rem; border-radius:12px; box-shadow:0 2px 10px rgba(10,31,68,.08);
  flex-wrap:wrap !important; overflow:visible !important; height:auto !important; }
.stTabs [data-baseweb="tab-list"] > div, .stTabs [role="tablist"] { flex-wrap:wrap !important; }
.stTabs [data-baseweb="tab"] { border-radius:9px; padding:.5rem .85rem; font-weight:600; color:var(--marino); }
.stTabs [aria-selected="true"] { background:linear-gradient(120deg, var(--marino-2), var(--electrico)); color:#fff !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display:none; }
h2, h3 { color:var(--marino) !important; }
h3 { border-left:5px solid var(--electrico); padding-left:.6rem !important; }
[data-testid="stMetric"] { background:#fff; border-radius:10px; padding:.7rem .9rem; border-top:4px solid var(--electrico); box-shadow:0 2px 10px rgba(10,31,68,.07); }
[data-testid="stMetricValue"] { color:var(--marino); }
[data-testid="stForm"] { background:#fff; border:1px solid #D5E2F5; border-radius:12px; }
[data-testid="stSidebar"] { background:linear-gradient(180deg, var(--marino) 0%, var(--marino-2) 100%); }
[data-testid="stSidebar"] * { color:#EAF2FF; }
[data-testid="stSidebar"] [data-testid="stMetric"] { background:rgba(255,255,255,.08); border-top-color:var(--rayo); box-shadow:none; }
[data-testid="stSidebar"] [data-testid="stMetricValue"] { color:#fff; }
[data-testid="stSidebar"] code { background:rgba(255,255,255,.12); color:#fff; }
.lateral-titulo { font-size:.78rem; color:#9FC0FF !important; margin:.6rem 0 .15rem; }
.lateral-valor { font-weight:700; color:#fff !important; }
.explica { background:#fff; border:1px solid #D5E2F5; border-radius:12px; padding:.9rem 1.1rem; margin:.2rem 0 1.4rem;
  display:grid; gap:.55rem; font-size:.95rem; color:#24324d; }
.explica .etq { display:block; font-size:.74rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--electrico); margin-bottom:.1rem; }
.explica .datos { background:#EEF4FF; border-radius:8px; padding:.6rem .8rem; border-left:4px solid var(--rayo); }
.semaforo { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px,1fr)); gap:.7rem; margin:.4rem 0 1rem; }
.luz { border-radius:12px; padding:.8rem 1rem; color:#fff; box-shadow:0 2px 10px rgba(10,31,68,.12); }
.luz .t { font-size:.78rem; opacity:.9; } .luz .v { font-size:1.35rem; font-weight:800; } .luz .s { font-size:.85rem; }
.recomendado { border-radius:14px; padding:1.2rem 1.4rem; color:#fff; margin:.5rem 0 1rem;
  background:linear-gradient(120deg, var(--marino) 0%, var(--marino-2) 60%, var(--electrico) 100%); box-shadow:0 6px 20px rgba(10,31,68,.2); }
.recomendado h2 { color:#fff !important; margin:.1rem 0 .3rem; font-size:1.7rem; }
.recomendado .k { color:#CFE1FF; font-size:.85rem; letter-spacing:.04em; text-transform:uppercase; }
.recomendado .badge { display:inline-block; background:var(--rayo); color:var(--marino); font-weight:800; border-radius:20px; padding:.15rem .7rem; margin-right:.4rem; font-size:.85rem; }
.ds { width:100%; border-collapse:collapse; background:#fff; border-radius:10px; overflow:hidden; font-size:.93rem; }
.ds th { text-align:left; background:#E4ECF8; color:var(--marino); padding:.45rem .7rem; width:38%; }
.ds td { padding:.45rem .7rem; border-bottom:1px solid #EDF2FA; color:#24324d; }
.st-key-nav [role="radiogroup"] { gap:.35rem; flex-wrap:wrap; background:#fff; padding:.45rem; border-radius:12px; box-shadow:0 2px 10px rgba(10,31,68,.08); }
.st-key-nav [role="radiogroup"] > label { margin:0 !important; padding:.38rem .85rem !important; border-radius:20px; border:1px solid #D5E2F5; background:#F4F7FC; cursor:pointer; }
.st-key-nav [role="radiogroup"] > label > div:first-child { display:none !important; }
.st-key-nav [role="radiogroup"] > label:has(input:checked) { background:linear-gradient(120deg, var(--marino-2), var(--electrico)); border-color:transparent; }
.st-key-nav [role="radiogroup"] > label:has(input:checked) * { color:#fff !important; }
.st-key-nav [role="radiogroup"] > label p { font-weight:600; color:var(--marino); font-size:.9rem; margin:0; }
[data-testid="stSidebar"] button { background:rgba(255,255,255,.12) !important; border:1px solid rgba(255,255,255,.35) !important; }
[data-testid="stSidebar"] button:hover { background:rgba(255,255,255,.22) !important; border-color:#F2B705 !important; }
[data-testid="stSidebar"] button * { color:#fff !important; }
.diag { background:#fff; border-radius:12px; padding:.9rem 1.1rem; margin:.5rem 0 .9rem; border-left:6px solid var(--rayo); box-shadow:0 2px 10px rgba(10,31,68,.07); }
.diag.critico { border-left-color:#D64545; }
.diag h4 { margin:0 0 .2rem; color:var(--marino); font-size:1.05rem; }
.diag .ev { color:#5A6B88; font-size:.9rem; margin-bottom:.4rem; }
.diag .cols { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px,1fr)); gap:.4rem 1.2rem; }
.diag b.t { font-size:.75rem; text-transform:uppercase; letter-spacing:.04em; color:var(--electrico); }
.diag ul { margin:.2rem 0 0 1.1rem; padding:0; font-size:.92rem; }
.login { max-width:420px; margin:3rem auto 1rem; text-align:center; }
@media (max-width: 640px) {
  .block-container { padding-left:.6rem; padding-right:.6rem; padding-top:.6rem; }
  .hero-logos { padding:.5rem .8rem; }
  .hero-logos img.espe { height:40px; } .hero-logos img.em { height:50px; }
  .hero-banda { padding:1rem 1rem .9rem; } .hero-banda h1 { font-size:1.3rem; } .hero-banda p.sub { font-size:.85rem; }
  .hero-banda::after { font-size:4rem; bottom:-1rem; }
  .hero-fichas { padding:.6rem .8rem .8rem; gap:.5rem; }
  .st-key-nav [role="radiogroup"] > label { padding:.3rem .6rem !important; } .st-key-nav [role="radiogroup"] > label p { font-size:.8rem; }
  .luz .v { font-size:1.1rem; }
}
.kvgrid { display:grid; gap:.35rem .9rem; }
.kv { display:flex; justify-content:space-between; gap:.6rem; border-bottom:1px dashed #E1E8F4; padding:.25rem 0; font-size:.92rem; }
.kv span { color:#5A6B88; } .kv b { color:var(--marino); text-align:right; }
.ruta { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px,1fr)); gap:.8rem; margin:.4rem 0 1rem; }
.paso { background:#fff; border-radius:12px; padding:1rem 1.1rem; border-top:5px solid var(--electrico); box-shadow:0 2px 10px rgba(10,31,68,.08); }
.paso .n { display:inline-block; background:var(--marino); color:#fff; border-radius:50%; width:1.7rem; height:1.7rem; text-align:center; line-height:1.7rem; font-weight:800; margin-right:.4rem; }
.paso h4 { display:inline; color:var(--marino); font-size:1.02rem; }
.paso .big { font-size:1.3rem; font-weight:800; color:var(--marino); margin:.5rem 0 .2rem; }
.paso p { margin:.2rem 0 0; color:#3B4A66; font-size:.9rem; }
.paso.fin { border-top-color:var(--rayo); background:linear-gradient(160deg,#fff 60%,#FFF7DD); }
.chip { display:inline-block; padding:.2rem .7rem; border-radius:20px; color:#fff; font-weight:700; font-size:.85rem; }
.caja { background:#fff; border:1px solid #D5E2F5; border-radius:12px; padding:.8rem 1rem; margin:.3rem 0 .8rem; }
.caja h4 { margin:0 0 .4rem; color:var(--marino); font-size:1rem; }
.grande { font-size:1.25rem; font-weight:800; color:var(--marino); }
.pie { margin-top:2rem; padding:1rem 1.4rem; border-radius:12px; text-align:center; background:var(--marino); color:#CFE1FF; font-size:.85rem; }
.pie b { color:#fff; }
</style>
"""
