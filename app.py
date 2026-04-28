import ast
import pandas as pd
import networkx as nx
import folium
import streamlit as st
from folium.features import DivIcon
from streamlit_folium import st_folium


st.set_page_config(page_title="Mining Conflict Map", layout="wide")

ACTIVE_COLOR = "#d32f2f"
INACTIVE_COLOR = "#9aa0a6"
EDGE_COLOR = "#8B0000"
MINE_COLOR = "#FFD700"


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
def load_data():
    df = pd.read_csv("df_mapa.csv")
    df_location = pd.read_csv("df_localizacion.csv")

    try:
        df_mines = pd.read_csv("minas_light.csv")
    except Exception:
        df_mines = None

    return df, df_location, df_mines


def get_coords(df_location):
    base = df_location.dropna(subset=["lat", "lon"]).copy()
    base = base.drop_duplicates(subset=["Pueblos_actualizados"], keep="first")
    return base.set_index("Pueblos_actualizados")[["lat", "lon"]].to_dict("index")


def graph_by_semester(df, semester):
    use = df.copy()
    use["Pueblos_actualizados"] = use["Pueblos_actualizados"].apply(to_list)
    use = use[use["Semestre"].astype(str) == str(semester)].reset_index(drop=True)

    G = nx.Graph()

    for _, row in use.iterrows():
        towns = row["Pueblos_actualizados"]
        mine = str(row.get("Minas", "Unknown"))

        for town in towns:
            G.add_node(town)

        for i in range(len(towns)):
            for j in range(i + 1, len(towns)):
                u, v = towns[i], towns[j]

                if G.has_edge(u, v):
                    G[u][v]["weight"] += 1
                    G[u][v]["mines"].add(mine)
                else:
                    G.add_edge(u, v, weight=1, mines={mine})

    return G, use


def make_map(
    G,
    coords,
    df_mines=None,
    edge_base=0.6,
    edge_scale=0.7,
    edge_max_mult=6,
    opacity=0.5,
):
    m = folium.Map(
        location=[-9.19, -75.0152],
        zoom_start=6,
        tiles=None
    )

    # 🔥 Tile SIN nombre visible
    folium.TileLayer(
        tiles="CartoDB positron",
        name="",
        control=True
    ).add_to(m)

    layer_all = folium.FeatureGroup(name="Inactive nodes", show=True)
    layer_active = folium.FeatureGroup(name="Active nodes", show=True)
    layer_edges = folium.FeatureGroup(name="Connections", show=True)

    # nodos grises
    for town, c in coords.items():
        folium.CircleMarker(
            location=[c["lat"], c["lon"]],
            radius=4,
            color=INACTIVE_COLOR,
            fill=True,
            fill_color=INACTIVE_COLOR,
            fill_opacity=0.8,
        ).add_to(layer_all)

    bounds = []

    # aristas
    for u, v, data in G.edges(data=True):
        if u in coords and v in coords:
            pts = [
                (coords[u]["lat"], coords[u]["lon"]),
                (coords[v]["lat"], coords[v]["lon"])
            ]

            w = data.get("weight", 1)

            folium.PolyLine(
                pts,
                weight=edge_base + edge_scale * min(w, edge_max_mult),
                color=EDGE_COLOR,
                opacity=opacity,
            ).add_to(layer_edges)

            bounds.extend(pts)

    # nodos activos rojos
    for town in G.nodes:
        if town in coords:
            lat, lon = coords[town]["lat"], coords[town]["lon"]

            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color=ACTIVE_COLOR,
                fill=True,
                fill_color=ACTIVE_COLOR,
                fill_opacity=0.95,
            ).add_to(layer_active)

            bounds.append((lat, lon))

    # minas
    if df_mines is not None:
        layer_mines = folium.FeatureGroup(name="Mines", show=True)

        for _, row in df_mines.dropna(subset=["lat", "lon"]).iterrows():
            lat = row["lat"]
            lon = row["lon"]
            size = int(row.get("radius", 10))

            triangle = f"""
            <div style="
                width:0;height:0;
                border-left:{size}px solid transparent;
                border-right:{size}px solid transparent;
                border-top:{size*1.5}px solid {MINE_COLOR};
            "></div>
            """

            folium.Marker(
                location=[lat, lon],
                icon=DivIcon(html=triangle),
            ).add_to(layer_mines)

        layer_mines.add_to(m)

    layer_all.add_to(m)
    layer_edges.add_to(m)
    layer_active.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    if bounds:
        m.fit_bounds(bounds)

    return m


# ===== APP =====

df, df_location, df_mines = load_data()
coords = get_coords(df_location)

st.title("Mining conflict map by semester")

st.sidebar.header("Filters")

semesters = sorted(df["Semestre"].dropna().astype(str).unique())

semester = st.sidebar.selectbox("Semester", semesters)

show_mines = st.sidebar.checkbox("Show mines", True)

edge_base = st.sidebar.slider("Base thickness", 0.1, 2.0, 0.6, 0.1)
edge_scale = st.sidebar.slider("Weight scale", 0.1, 2.0, 0.7, 0.1)

# ===== LEYENDA LIMPIA =====
st.sidebar.markdown("---")
st.sidebar.subheader("Legend")

st.sidebar.markdown(
    f'<span style="color:{ACTIVE_COLOR}; font-size:20px;">●</span> Active nodes (red circles)',
    unsafe_allow_html=True
)

st.sidebar.markdown(
    f'<span style="color:{INACTIVE_COLOR}; font-size:20px;">●</span> Inactive nodes (gray circles)',
    unsafe_allow_html=True
)

st.sidebar.markdown(
    f'<span style="color:{MINE_COLOR}; font-size:20px;">▼</span> Mines (yellow triangles)',
    unsafe_allow_html=True
)

st.sidebar.markdown(
    f'<span style="color:{EDGE_COLOR}; font-size:20px;">━</span> Connections (shared conflicts)',
    unsafe_allow_html=True
)

# ===== MAP =====

G, df_sem = graph_by_semester(df, semester)

m = make_map(
    G,
    coords,
    df_mines=df_mines if show_mines else None,
    edge_base=edge_base,
    edge_scale=edge_scale,
)

col1, col2, col3 = st.columns(3)
col1.metric("Active nodes", len(G.nodes))
col2.metric("Connections", len(G.edges))
col3.metric("Records", len(df_sem))

st.subheader(f"Semester: {semester}")

st_folium(m, height=720)
