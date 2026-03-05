import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Encontrar e substituir TEMPO_HTML
start_marker = 'TEMPO_HTML = """'
end_marker = 'PURPLEFLIX_HTML = """'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Markers not found!")
    exit(1)

# Salvar backup
with open('app.py.backup', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Backup created: app.py.backup")
print(f"Start: {start_idx}, End: {end_idx}")
print("Ready to update")
