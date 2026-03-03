try:
    with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_split_new.html', 'r', encoding='utf-8') as f:
        PDFS_SPLIT_HTML = f.read()
except:
    PDFS_SPLIT_HTML = "<h1>Error loading split template</h1>"

try:
    with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_convert_final.html', 'r', encoding='utf-8') as f:
        PDFS_CONVERT_HTML = f.read()
except:
    PDFS_CONVERT_HTML = "<h1>Error loading convert template</h1>"
