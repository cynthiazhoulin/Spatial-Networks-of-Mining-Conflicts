import ast
import pandas as pd
import numpy as np
import networkx as nx
import folium
import streamlit as st
from folium.features import DivIcon
from streamlit_folium import st_folium


st.set_page_config(
    page_title="Mapa de conflictos mineros",
    layout="wide"
)


def to_list(x):
    if isinstance(x, list):
        return [str(s).strip() for s in x if str(s).strip()]

    if isinstance(x, str):
        x = x.strip()
        try:
            parsed = ast.literal_eval(x)
            if isinstance(parsed, (list, tuple)):
                return [str(s).strip() for s in parsed if str(s).strip()]
        except Exception:
            pass

        return [s.strip() for s in x.split(",") if s.strip()]

    return []


@st.cache_data
def cargar_datos():
    df = pd.read_csv("df_mapa.csv")
    df_localizacion = pd.read_csv("df_localizacion.csv")

    try:
        df_minas = pd.read_csv("minas_light.csv")
    except Exception:
        df_minas = None

    return df, df_localizacion, df_minas


def coords_dict(df_localizacion):
    base = df_localizacion.dropna(subset=["lat", "lon"]).copy()
    base = base.drop_duplicates(subset=["Pueblos_actualizados"], keep="first")

    return base.set_index("Pueblos_actualizados")[["lat", "lon"]].to_dict("index")


def grafo_por_semestre(df, semestre):
    use = df.copy()
    use["Pueblos_actualizados"] = use["Pueblos_actualizados"].apply(to_list)
    use = use[use["Semestre"].astype(str) == str(semestre)].reset_index(drop=True)

    G = nx.Graph()

    for _, row in use.iterrows():
        pueblos = row["Pueblos_actualizados"]
        mina = str(row.get("Minas", "Desconocida"))

        for p in pueblos:
            G.add_node(p, tipo="pueblo_actualizado")

        for i in range(len(pueblos)):
            for j in range(i + 1, len(pueblos)):
                u, v = pueblos[i], pueblos[j]

                if G.has_edge(u, v):
                    G[u][v]["peso"] += 1
                    G[u][v]["minas"].add(mina)
                else:
                    G.add_edge(u, v, peso=1, minas={mina})

    return G, use


def mapa_grafo(
    G,
    coords,
    titulo="Red de pueblos conectados por conflictos mineros",
    df_minas=None,
    edge_base=0.6,
    edge_scale=0.7,
    edge_max_mult=6,
    edge_color="#8B0000",
    opacity=0.5,
    color_activo="#d32f2f",
    color_inactivo="#9aa0a6",
    radio_inactivo=4,
    radio_activo=6,
):
    m = folium.Map(
        location=[-9.19, -75.0152],
        zoom_start=6,
        tiles="CartoDB positron"
    )

    layer_nodos_base = folium.FeatureGroup(
        name="Todos los pueblos con coordenadas",
        show=True
    )
    layer_nodos_activo = folium.FeatureGroup(
        name="Pueblos del semestre seleccionado",
        show=True
    )
    layer_aristas = folium.FeatureGroup(
        name="Conexiones del semestre",
        show=True
    )

    for n, c in coords.items():
        folium.CircleMarker(
            location=[c["lat"], c["lon"]],
            radius=radio_inactivo,
            color=color_inactivo,
            fill=True,
            fill_color=color_inactivo,
            fill_opacity=0.8,
            opacity=0.8,
            tooltip=n
        ).add_to(layer_nodos_base)

    active_bounds = []

    for u, v, data in G.edges(data=True):
        if u in coords and v in coords:
            pts = [
                (coords[u]["lat"], coords[u]["lon"]),
                (coords[v]["lat"], coords[v]["lon"])
            ]

            peso = data.get("peso", 1)
            minas = ", ".join(sorted(map(str, data.get("minas", []))))

            folium.PolyLine(
                pts,
                weight=edge_base + edge_scale * min(peso, edge_max_mult),
                opacity=opacity,
                color=edge_color,
                tooltip=f"{u} — {v} | Conflictos: {peso} | Minas: {minas}"
            ).add_to(layer_aristas)

            active_bounds.extend(pts)

    for n in G.nodes:
        if n in coords:
            la, lo = coords[n]["lat"], coords[n]["lon"]

            folium.CircleMarker(
                location=[la, lo],
                radius=radio_activo,
                color=color_activo,
                fill=True,
                fill_color=color_activo,
                fill_opacity=0.95,
                opacity=0.95,
                tooltip=f"{n} activo"
            ).add_to(layer_nodos_activo)

            active_bounds.append((la, lo))

    if df_minas is not None:
        layer_minas = folium.FeatureGroup(name="Minas", show=True)

        for _, row in df_minas.dropna(subset=["lat", "lon"]).iterrows():
            lat = row["lat"]
            lon = row["lon"]
            size = int(row.get("radius", 10))

            popup_html = f"""
            <b>Proyecto:</b> {row.get("PROYECTO", "N/A")}<br>
            <b>Empresa:</b> {row.get("EMPRESA", "N/A")}<br>
            <b>Área km²:</b> {row.get("AREAKM2", "N/A")}<br>
            <b>Has:</b> {row.get("HAS", "N/A")}<br>
            <b>Zona:</b> {row.get("ZONA", "N/A")}<br>
            <b>ID:</b> {row.get("ID", "N/A")}<br>
            <b>Capa:</b> {row.get("CAPA", "N/A")}
            """

            triangle_icon = f"""
            <div style="
                width: 0;
                height: 0;
                border-left: {size}px solid transparent;
                border-right: {size}px solid transparent;
                border-top: {size * 1.5}px solid #FFD700;
            "></div>
            """

            folium.Marker(
                location=[lat, lon],
                icon=DivIcon(html=triangle_icon),
                popup=folium.Popup(popup_html, max_width=260),
            ).add_to(layer_minas)

        layer_minas.add_to(m)

    layer_nodos_base.add_to(m)
    layer_aristas.add_to(m)
    layer_nodos_activo.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    leyenda_html = f"""
    <div style="
        position: fixed;
        bottom: 18px;
        right: 18px;
        z-index: 9999;
        background: rgba(255,255,255,0.95);
        padding: 10px 12px;
        border: 1px solid #ccc;
        border-radius: 10px;
        font-size: 13px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        pointer-events: none;
    ">
      <div style="font-weight:700; margin-bottom:6px">{titulo}</div>

      <div style="display:flex; gap:8px; align-items:center; margin-bottom:4px;">
        <span style="width:10px; height:10px; background:{color_inactivo}; border-radius:50%; display:inline-block;"></span>
        <span>Todos los pueblos con coordenadas</span>
      </div>

      <div style="display:flex; gap:8px; align-items:center; margin-bottom:4px;">
        <span style="width:10px; height:10px; background:{color_activo}; border-radius:50%; display:inline-block;"></span>
        <span>Pueblos del semestre seleccionado</span>
      </div>

      <div style="display:flex; gap:8px; align-items:center; margin-bottom:4px;">
        <span style="width:20px; height:2px; background:{edge_color}; display:inline-block;"></span>
        <span>Conexiones del semestre</span>
      </div>

      <div style="display:flex; gap:8px; align-items:center;">
        <span style="
            width: 0;
            height: 0;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 10px solid #FFD700;
            display:inline-block;
        "></span>
        <span>Minas</span>
      </div>
    </div>
    """

    folium.map.Marker(
        [-17.8, -81.3],
        icon=DivIcon(icon_size=(0, 0), icon_anchor=(0, 0), html=leyenda_html)
    ).add_to(m)

    if active_bounds:
        m.fit_bounds(active_bounds)

    return m


df, df_localizacion, df_minas = cargar_datos()
coords = coords_dict(df_localizacion)

st.title("Mapa de conflictos mineros por semestre")

st.sidebar.header("Filtros")

semestres = sorted(df["Semestre"].dropna().astype(str).unique())

semestre = st.sidebar.selectbox(
    "Semestre",
    semestres
)

mostrar_minas = st.sidebar.checkbox(
    "Mostrar minas",
    value=True
)

edge_base = st.sidebar.slider(
    "Grosor base",
    min_value=0.1,
    max_value=2.0,
    value=0.6,
    step=0.1
)

edge_scale = st.sidebar.slider(
    "Escala por peso",
    min_value=0.1,
    max_value=2.0,
    value=0.7,
    step=0.1
)

G, df_sem = grafo_por_semestre(df, semestre)

m = mapa_grafo(
    G,
    coords,
    titulo=f"Red por semestre: {semestre}",
    df_minas=df_minas if mostrar_minas else None,
    edge_base=edge_base,
    edge_scale=edge_scale,
)

col1, col2, col3 = st.columns(3)

col1.metric("Pueblos activos", len(G.nodes))
col2.metric("Conexiones", len(G.edges))
col3.metric("Registros del semestre", len(df_sem))

st.subheader(f"Semestre: {semestre}")

st_folium(
    m,
    width=None,
    height=720
)
