try:
    with open('/opt/lampp/htdocs/Verto/Office/office_hub.html', 'r', encoding='utf-8') as f:
        OFFICE_HUB_HTML = f.read()
except Exception:
    OFFICE_HUB_HTML = "<h1>Error loading Office hub template</h1>"

try:
    with open('/opt/lampp/htdocs/Verto/Office/office_convert.html', 'r', encoding='utf-8') as f:
        OFFICE_CONVERT_HTML = f.read()
except Exception:
    OFFICE_CONVERT_HTML = "<h1>Error loading Office convert template</h1>"

try:
    with open('/opt/lampp/htdocs/Verto/Office/office_repair.html', 'r', encoding='utf-8') as f:
        OFFICE_REPAIR_HTML = f.read()
except Exception:
    OFFICE_REPAIR_HTML = "<h1>Error loading Office repair template</h1>"
