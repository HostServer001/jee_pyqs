import streamlit as st
import tempfile
import shutil
from pathlib import Path
from zipfile import ZipFile
import json

from jee_data_base import DataBase, Filter, pdfy
#import components as components


st.html("""
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-VMLMXMCJLK"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-VMLMXMCJLK');
</script>""", height=0)
# -------------------------------
# Init session state
# -------------------------------
def init_state():
    if "page" not in st.session_state:
        st.session_state.page = "zip_exporter"   # MAIN PAGE
    if "db" not in st.session_state:
        st.session_state.db = None
    if "filter" not in st.session_state:
        st.session_state.filter = None
    if "clusters" not in st.session_state:
        st.session_state.clusters = None
    if "status" not in st.session_state:
        st.session_state.status = "Ready"


init_state()
st.set_page_config(page_title="ExamGoal Tool", layout="wide")


# ============================================================
# ===============  PAGE 1 → ZIP EXPORTER (MAIN) ==============
# ============================================================
def page_zip_exporter():
    st.title("📦 Last 5 Years Chapter ZIP Exporter")

    # Load DB
    @st.cache_resource
    def load_db():
        db = DataBase()
        return db, Filter(db.chapters_dict)

    db, f = load_db()

    # -------------------
    # UI
    # -------------------
    chapters = sorted(db.chapters_dict.keys())
    chapter = st.selectbox("Select Chapter", chapters)

    skim = st.checkbox("Enable Skim Mode", value=False)

    st.markdown("Generates a folder → Zips it → Lets you download ZIP.")

    if st.button("Generate ZIP", use_container_width=True):
        with st.spinner("Generating..."):
            temp_root = Path(tempfile.mkdtemp())
            out_folder = temp_root / chapter

            # Step 1 → Call your module method
            f.render_chap_last5yrs(str(temp_root), chapter, skim)

            # Step 2 → Zip the folder
            zip_path = temp_root / f"{chapter.replace(' ', '_')}.zip"
            with ZipFile(zip_path, "w") as zipf:
                for file in out_folder.rglob("*"):
                    zipf.write(file, file.relative_to(out_folder.parent))

        st.success("ZIP generated!")

        st.download_button(
            "⬇️ Download ZIP",
            data=zip_path.read_bytes(),
            file_name=f"{chapter.replace(' ', '_')}.zip",
            mime="application/zip",
            use_container_width=True
        )

    st.markdown("---")
    if st.button("➡️ Go to Advanced Explorer"):
        st.session_state.page = "advanced"
        st.rerun()


# ============================================================
# =============== PAGE 2 → ADVANCED EXPLORER =================
# ============================================================
def page_advanced_explorer():
    st.title("🧭 Advanced ExamGoal Explorer")

    # Load DB lazily
    if st.button("Load Database"):
        with st.spinner("Loading DB..."):
            try:
                db = DataBase()
                f = Filter(db.chapters_dict)
                st.session_state.db = db
                st.session_state.filter = f
                st.session_state.status = f"Loaded {len(f.current_set)} questions."
            except Exception as e:
                st.error(f"Load failed: {e}")

    st.caption(f"Status: {st.session_state.status}")
    st.markdown("---")

    f = st.session_state.filter
    if not f:
        st.info("Click 'Load Database' first.")
        if st.button("⬅️ Back to ZIP Exporter"):
            st.session_state.page = "zip_exporter"
            st.rerun()
        return

    # -------------------
    # Filters
    # -------------------
    st.subheader("Filters")

    try:
        possible = f.get_possible_filter_values()
        params = sorted(possible.keys())
    except:
        params = sorted(list(getattr(f, "filterable_param", [])))

    field = st.selectbox("Field", [""] + params)
    if field:
        raw_vals = possible.get(field, [])
        # Format like your Tk app
        vals = []
        for v in raw_vals:
            if v is None:
                vals.append("None")
            else:
                try:
                    vals.append(json.dumps(v, sort_keys=True, default=str))
                except:
                    vals.append(str(v))
        # dedupe
        vals = list(dict.fromkeys(vals))
    else:
        vals = []

    value = st.selectbox("Value", [""] + vals)

    colA, colB = st.columns(2)
    with colA:
        if st.button("Apply Filter"):
            with st.spinner("Filtering..."):
                try:
                    # Convert string back to python object
                    if value == "None":
                        target_val = None
                    else:
                        try:
                            target_val = json.loads(value)
                        except:
                            try:
                                target_val = int(value)
                            except:
                                target_val = value

                    new_set = []
                    for q in f.current_set:
                        attr = getattr(q, field, None)

                        # Compare complex types
                        if isinstance(attr, (dict, list, tuple)):
                            a = json.dumps(attr, sort_keys=True, default=str)
                            b = json.dumps(target_val, sort_keys=True, default=str)
                            if a == b:
                                new_set.append(q)
                        else:
                            if attr == target_val:
                                new_set.append(q)

                    f.current_set = new_set
                    st.session_state.status = f"Filtered to {len(new_set)} questions."
                except Exception as e:
                    st.error(f"Filtering failed: {e}")

    with colB:
        if st.button("Reset Filters"):
            with st.spinner("Resetting..."):
                try:
                    st.session_state.filter = Filter(st.session_state.db.chapters_dict)
                    st.session_state.status = f"Reset — {len(st.session_state.filter.current_set)} questions."
                except Exception as e:
                    st.error(f"Reset failed: {e}")

    st.markdown("---")

    # -------------------
    # Table
    # -------------------
    st.subheader("Questions")

    rows = []
    for q in f.current_set:
        rows.append({
            "ID": getattr(q, "question_id", ""),
            "Exam": getattr(q, "exam", ""),
            "Year": getattr(q, "year", ""),
            "Subject": getattr(q, "subject", ""),
            "Chapter": getattr(q, "chapter", "")
        })

    st.dataframe(rows, use_container_width=True)
    st.caption(f"Showing {len(rows)} questions.")

    # -------------------
    # Clustering + Export HTML
    # -------------------
    st.markdown("---")
    c1, c2 = st.columns(2)

    with c1:
        if st.button("Run Clustering"):
            with st.spinner("Clustering..."):
                try:
                    clusters = f.cluster()
                    st.session_state.clusters = clusters
                    st.session_state.status = f"Clustered into {len(clusters)} groups."
                except Exception as e:
                    st.error(f"Clustering failed: {e}")

    with c2:
        if st.button("Export Clusters to HTML"):
            clusters = st.session_state.get("clusters")
            if not clusters:
                st.warning("Run clustering first.")
            else:
                with st.spinner("Exporting HTML..."):
                    tmp = Path(tempfile.mktemp(suffix=".html"))
                    pdfy.render_cluster_to_html(clusters, str(tmp))

                st.download_button(
                    "⬇️ Download HTML",
                    data=tmp.read_bytes(),
                    file_name="clusters.html",
                    mime="text/html"
                )

    st.markdown("---")

    if st.button("⬅️ Back to ZIP Exporter"):
        st.session_state.page = "zip_exporter"
        st.rerun()


# ============================================================
# =============== PAGE ROUTER (ONE FILE ONLY) ================
# ============================================================
if st.session_state.page == "zip_exporter":
    page_zip_exporter()
else:
    page_advanced_explorer()