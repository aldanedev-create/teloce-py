# Teloce data story

This is a small but real Flask application that exercises the data features
in Teloce-Py: imported components, `$attrs`, CSV loading, `v-virtual-for`,
`v-memo`, `v-scrolly`, chart annotations, URL state, polling, `use:` actions,
the sortable/filterable table primitive, and the shared runtime.

Run it from a checkout of Teloce-Py (editable mode):

```powershell
python -m pip install -r requirements.txt
python build.py
python app.py
```

Open <http://127.0.0.1:5060>. The Flask API returns live summary data and the
browser loads `static/data/report.csv` through the shared Teloce runtime.
