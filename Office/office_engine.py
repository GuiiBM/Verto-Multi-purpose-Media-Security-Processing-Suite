"""Motor de conversão e recuperação de arquivos do pacote Office.

Conversão: usa o LibreOffice headless (soffice --convert-to) como motor de
renderização real - é ele quem sabe desenhar fontes, layouts e estilos
corretamente, então nunca tentamos redesenhar texto manualmente. Para exportar
imagens (ex: pptx -> png), primeiro convertemos para PDF via LibreOffice e
depois rasterizamos cada página com PyMuPDF, evitando qualquer problema de
fonte/acentuação que apareceria se tentássemos desenhar o texto nós mesmos.

Recuperação: cascata de 5 níveis (mesmo espírito das estratégias de reparo de
PDF já usadas no app), da mais conservadora para a mais agressiva:
  1. Detecção do formato real pelo conteúdo (ignora a extensão enviada)
  2. Reconstrução do contêiner ZIP (OOXML/ODF) a partir das partes legíveis
  3. Validação/reparo abrindo com a biblioteca nativa (python-docx/openpyxl/pptx)
  4. Reparo via motor de importação do LibreOffice (mais tolerante a corrupção)
  5. Recuperação bruta de texto e remontagem em um arquivo novo
"""

import html
import io
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
import zlib
from pathlib import Path


class OfficeError(Exception):
    pass


FAMILY_EXTS = {
    'document': {'doc', 'docx', 'odt', 'rtf', 'txt', 'fodt'},
    'spreadsheet': {'xls', 'xlsx', 'ods', 'csv', 'fods'},
    'presentation': {'ppt', 'pptx', 'odp', 'fodp'},
}

CONTENT_TYPE_FAMILY = {
    'wordprocessingml': 'document',
    'spreadsheetml': 'spreadsheet',
    'presentationml': 'presentation',
}

ODF_MIME_FAMILY = {
    'application/vnd.oasis.opendocument.text': 'document',
    'application/vnd.oasis.opendocument.spreadsheet': 'spreadsheet',
    'application/vnd.oasis.opendocument.presentation': 'presentation',
}

DEFAULT_EXT_FOR_FAMILY = {
    'document': 'docx',
    'spreadsheet': 'xlsx',
    'presentation': 'pptx',
}

FAMILY_LABEL = {
    'document': 'documento de texto (Word)',
    'spreadsheet': 'planilha (Excel)',
    'presentation': 'apresentação (PowerPoint)',
}

CONTENT_TYPES_XML = {
    'document': (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    ),
    'spreadsheet': (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '</Types>'
    ),
    'presentation': (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        '</Types>'
    ),
}

ROOT_RELS_XML = {
    'document': (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdMain" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    ),
    'spreadsheet': (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdMain" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    ),
    'presentation': (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdMain" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="ppt/presentation.xml"/></Relationships>'
    ),
}

TEXT_NODE_PATTERNS = {
    'document': re.compile(rb'<w:t[^>]*>(.*?)</w:t>', re.S),
    'spreadsheet': re.compile(rb'<t[^>]*>(.*?)</t>', re.S),
    'presentation': re.compile(rb'<a:t[^>]*>(.*?)</a:t>', re.S),
}


def _family_for_ext(ext):
    ext = (ext or '').lower().lstrip('.')
    for family, exts in FAMILY_EXTS.items():
        if ext in exts:
            return family
    return None


def _downloads_output_path(desired_filename):
    downloads_dir = str(Path.home() / "Downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    base_name, ext = os.path.splitext(desired_filename)
    output_path = os.path.join(downloads_dir, desired_filename)
    counter = 1
    while os.path.exists(output_path):
        output_path = os.path.join(downloads_dir, f"{base_name}_{counter}{ext}")
        counter += 1
    return output_path


def soffice_available():
    return shutil.which("soffice") is not None or shutil.which("libreoffice") is not None


def _soffice_binary():
    return shutil.which("soffice") or shutil.which("libreoffice") or "soffice"


def run_soffice(input_path, target_ext, outdir, timeout=180):
    """Roda o LibreOffice headless em um perfil de usuário isolado (evita travar
    por causa de outra instância/lock quando várias conversões acontecem em
    sequência) e com timeout, já que o soffice pode travar em arquivos ruins."""
    profile_dir = tempfile.mkdtemp(prefix="office_soffice_profile_")
    try:
        cmd = [
            _soffice_binary(), "--headless", "--norestore", "--nolockcheck", "--nodefault",
            f"-env:UserInstallation=file://{profile_dir}",
            "--convert-to", target_ext, "--outdir", outdir, input_path,
        ]
        try:
            return subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise OfficeError(
                "O LibreOffice demorou demais para processar o arquivo (tempo limite excedido)."
            ) from e
        except FileNotFoundError as e:
            raise OfficeError(
                "LibreOffice não está instalado neste sistema. Instale com "
                "'sudo apt install libreoffice' (Linux) ou baixe em libreoffice.org (Windows)."
            ) from e
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def _find_produced_file(outdir, ext):
    ext = ext.lower().lstrip('.')
    if not os.path.isdir(outdir):
        return None
    for name in os.listdir(outdir):
        if name.lower().endswith('.' + ext):
            return os.path.join(outdir, name)
    return None


def _soffice_error_message(result):
    if result is None:
        return "O LibreOffice não conseguiu converter o arquivo."
    stderr = result.stderr.decode('utf-8', 'ignore').strip()
    stdout = result.stdout.decode('utf-8', 'ignore').strip()
    detail = stderr or stdout
    last_line = detail.splitlines()[-1] if detail else "erro desconhecido"
    return f"O LibreOffice não conseguiu converter o arquivo: {last_line}"


# ---------------------------------------------------------------------------
# Detecção de formato real (independente da extensão enviada)
# ---------------------------------------------------------------------------

def sniff_family(data):
    """Retorna (family, container, notes) a partir dos bytes do arquivo.
    family é 'document'/'spreadsheet'/'presentation' ou None se não identificado.
    container é 'ooxml'/'odf'/'ole2'/'rtf'/'zip-corrompido'/None."""
    if data[:4] == b'PK\x03\x04' or data[:4] == b'PK\x05\x06' or data[:4] == b'PK\x07\x08':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                if '[Content_Types].xml' in names:
                    try:
                        ct = zf.read('[Content_Types].xml').decode('utf-8', 'ignore')
                    except Exception:
                        ct = ''
                    for key, fam in CONTENT_TYPE_FAMILY.items():
                        if key in ct:
                            return fam, 'ooxml'
                if 'mimetype' in names:
                    try:
                        mt = zf.read('mimetype').decode('utf-8', 'ignore').strip()
                    except Exception:
                        mt = ''
                    for key, fam in ODF_MIME_FAMILY.items():
                        if key in mt:
                            return fam, 'odf'
                if any(n.startswith('word/') for n in names):
                    return 'document', 'ooxml'
                if any(n.startswith('xl/') for n in names):
                    return 'spreadsheet', 'ooxml'
                if any(n.startswith('ppt/') for n in names):
                    return 'presentation', 'ooxml'
        except zipfile.BadZipFile:
            return None, 'zip-corrompido'
        return None, 'zip-corrompido'

    if data[:8] == b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1':
        return sniff_ole_subtype(data), 'ole2'

    if data[:5] == b'{\\rtf':
        return 'document', 'rtf'

    return None, None


def sniff_ole_subtype(data):
    """Heurística leve para arquivos binários legados (.doc/.xls/.ppt): procura
    pelos nomes de stream conhecidos, gravados em UTF-16LE dentro do compound
    file, sem precisar de um parser OLE2 completo."""
    def u16(s):
        return s.encode('utf-16-le')

    if u16('WordDocument') in data:
        return 'document'
    if u16('Workbook') in data or u16('Book') in data:
        return 'spreadsheet'
    if u16('PowerPoint Document') in data:
        return 'presentation'
    return None


# ---------------------------------------------------------------------------
# Reconstrução tolerante de ZIP (nível 2 do reparo)
# ---------------------------------------------------------------------------

def tolerant_zip_extract(data):
    """Varre o arquivo em busca de assinaturas de local file header (PK\\x03\\x04)
    e infla cada stream manualmente. Diferente do módulo zipfile, não depende de
    uma central directory íntegra no final do arquivo - por isso consegue
    recuperar partes de um ZIP truncado ou com o rodapé corrompido."""
    entries = {}
    pos = 0
    sig = b'PK\x03\x04'
    while True:
        idx = data.find(sig, pos)
        if idx == -1:
            break
        header = data[idx:idx + 30]
        if len(header) < 30:
            break
        try:
            method = struct.unpack('<H', header[8:10])[0]
            comp_size = struct.unpack('<I', header[18:22])[0]
            name_len = struct.unpack('<H', header[26:28])[0]
            extra_len = struct.unpack('<H', header[28:30])[0]
            name_start = idx + 30
            name = data[name_start:name_start + name_len].decode('utf-8', 'ignore')
            body_start = name_start + name_len + extra_len

            content = b''
            if method == 0:
                content = data[body_start:body_start + comp_size]
            elif method == 8:
                chunk = data[body_start:body_start + max(comp_size, 20_000_000)]
                decomp = zlib.decompressobj(-15)
                try:
                    content = decomp.decompress(chunk)
                except Exception:
                    content = b''

            if name and content:
                entries[name] = content
        except Exception:
            pass
        pos = idx + 4
    return entries


def ensure_essential_parts(entries, family):
    if family not in CONTENT_TYPES_XML:
        return entries
    if '[Content_Types].xml' not in entries:
        entries['[Content_Types].xml'] = CONTENT_TYPES_XML[family].encode('utf-8')
    if '_rels/.rels' not in entries:
        entries['_rels/.rels'] = ROOT_RELS_XML[family].encode('utf-8')
    return entries


def rebuild_zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            try:
                zf.writestr(name, content)
            except Exception:
                continue
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Recuperação bruta de texto (nível 5 do reparo)
# ---------------------------------------------------------------------------

def extract_texts_from_parts(entries, family):
    pattern = TEXT_NODE_PATTERNS.get(family)
    if not pattern:
        return []
    blob = b'\n'.join(entries.values()) if isinstance(entries, dict) else entries
    texts = []
    for m in pattern.finditer(blob):
        fragment = re.sub(rb'<[^>]+>', b'', m.group(1))
        try:
            s = html.unescape(fragment.decode('utf-8', 'ignore'))
        except Exception:
            continue
        if s.strip():
            texts.append(s)
    return texts


def extract_ascii_text_runs(data, min_len=6, limit=500):
    """Último recurso para binários OLE2 que nem o LibreOffice conseguiu abrir:
    procura sequências de texto legível em UTF-16LE (como o Word grava strings
    em arquivos .doc antigos) e devolve os trechos encontrados."""
    pattern = re.compile(rb'(?:[\x20-\x7e]\x00){%d,}' % min_len)
    texts = []
    for m in pattern.finditer(data):
        s = m.group(0).decode('utf-16-le', 'ignore').strip()
        if s and any(c.isalnum() for c in s):
            texts.append(s)
        if len(texts) >= limit:
            break
    return texts


def rebuild_document_from_text(texts, family, output_path):
    if family == 'document':
        from docx import Document
        doc = Document()
        for t in texts:
            doc.add_paragraph(t)
        doc.save(output_path)
    elif family == 'spreadsheet':
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        for i, t in enumerate(texts, 1):
            ws.cell(row=i, column=1, value=t)
        wb.save(output_path)
    elif family == 'presentation':
        from pptx import Presentation
        from pptx.util import Inches
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(6.6))
        tf = box.text_frame
        tf.word_wrap = True
        first = True
        for t in texts:
            if first:
                tf.text = t
                first = False
            else:
                tf.add_paragraph().text = t
        prs.save(output_path)
    else:
        raise OfficeError("Formato desconhecido para recriar o documento.")


def try_native_open_and_resave(path, family, outdir, base_name):
    """Nível 3: valida abrindo com a biblioteca nativa e resalva (o round-trip
    já normaliza boa parte dos problemas estruturais residuais)."""
    try:
        if family == 'document':
            from docx import Document
            doc = Document(path)
            n = len(doc.paragraphs)
            out = os.path.join(outdir, f"{base_name}_reparado.docx")
            doc.save(out)
            return out, f"{n} parágrafo(s) recuperado(s)."
        if family == 'spreadsheet':
            from openpyxl import load_workbook
            wb = load_workbook(path)
            n = len(wb.sheetnames)
            out = os.path.join(outdir, f"{base_name}_reparado.xlsx")
            wb.save(out)
            return out, f"{n} planilha(s) recuperada(s): {', '.join(wb.sheetnames)}."
        if family == 'presentation':
            from pptx import Presentation
            prs = Presentation(path)
            n = len(prs.slides)
            out = os.path.join(outdir, f"{base_name}_reparado.pptx")
            prs.save(out)
            return out, f"{n} slide(s) recuperado(s)."
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# API pública: conversão
# ---------------------------------------------------------------------------

def convert_office_file(file_storage, output_format, dpi=200):
    """Converte um arquivo de Office (ou PDF) para o formato pedido. Retorna a
    lista de nomes de arquivo salvos em Downloads."""
    if not soffice_available():
        raise OfficeError(
            "LibreOffice não está instalado neste sistema. Instale com "
            "'sudo apt install libreoffice' (Linux) ou baixe em libreoffice.org (Windows)."
        )

    filename = file_storage.filename
    in_ext = os.path.splitext(filename)[1].lower().lstrip('.')
    base_name = os.path.splitext(filename)[0] or "arquivo"
    output_format = (output_format or '').lower().lstrip('.')
    if not output_format:
        raise OfficeError("Escolha um formato de saída.")

    file_storage.stream.seek(0)
    data = file_storage.stream.read()
    if not data:
        raise OfficeError("O arquivo enviado está vazio.")

    tmpdir = tempfile.mkdtemp(prefix="office_convert_")
    try:
        input_path = os.path.join(tmpdir, f"input.{in_ext or 'bin'}")
        with open(input_path, 'wb') as f:
            f.write(data)

        if output_format in ('png', 'jpg', 'jpeg'):
            if in_ext == 'pdf':
                pdf_path = input_path
            else:
                pdf_outdir = os.path.join(tmpdir, "pdf_out")
                os.makedirs(pdf_outdir, exist_ok=True)
                result = run_soffice(input_path, 'pdf', pdf_outdir, timeout=180)
                pdf_path = _find_produced_file(pdf_outdir, 'pdf')
                if not pdf_path:
                    raise OfficeError(_soffice_error_message(result))

            import fitz
            doc = fitz.open(pdf_path)
            try:
                if len(doc) == 0:
                    raise OfficeError("O documento convertido não tem nenhuma página.")
                zoom = dpi / 72.0
                matrix = fitz.Matrix(zoom, zoom)
                saved = []
                multi_page = len(doc) > 1
                for i, page in enumerate(doc, 1):
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    name = f"{base_name}_pagina_{i}.{output_format}" if multi_page else f"{base_name}.{output_format}"
                    out_path = _downloads_output_path(name)
                    pix.save(out_path)
                    saved.append(os.path.basename(out_path))
                return saved
            finally:
                doc.close()

        out_outdir = os.path.join(tmpdir, "out")
        os.makedirs(out_outdir, exist_ok=True)
        result = run_soffice(input_path, output_format, out_outdir, timeout=180)
        produced = _find_produced_file(out_outdir, output_format)
        if not produced:
            raise OfficeError(_soffice_error_message(result))
        out_path = _downloads_output_path(f"{base_name}.{output_format}")
        shutil.copy(produced, out_path)
        return [os.path.basename(out_path)]
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# API pública: reparo/recuperação
# ---------------------------------------------------------------------------

def repair_office_file(file_storage):
    """Cascata de 5 níveis de recuperação. Retorna (nome_arquivo_salvo, notas)."""
    filename = file_storage.filename
    claimed_ext = os.path.splitext(filename)[1].lower().lstrip('.')
    base_name = os.path.splitext(filename)[0] or "arquivo"

    file_storage.stream.seek(0)
    data = file_storage.stream.read()
    if not data:
        raise OfficeError("O arquivo enviado está vazio.")

    notes = []

    # Nível 1: detecção do formato real, ignorando a extensão enviada.
    real_family, container = sniff_family(data)
    claimed_family = _family_for_ext(claimed_ext)

    if real_family and claimed_family and real_family != claimed_family:
        notes.append(
            f"⚠️ O arquivo veio com extensão .{claimed_ext} (esperado: "
            f"{FAMILY_LABEL.get(claimed_family, claimed_family)}), mas o conteúdo real é de "
            f"{FAMILY_LABEL.get(real_family, real_family)}. Tratando pelo formato real."
        )
        family = real_family
    elif real_family:
        family = real_family
    elif claimed_family:
        family = claimed_family
        notes.append(
            "⚠️ Não foi possível confirmar o formato pelo conteúdo (arquivo muito "
            "danificado); seguindo pela extensão enviada."
        )
    else:
        family = 'document'
        notes.append(
            "⚠️ Não foi possível identificar o tipo de documento; assumindo Word como padrão."
        )

    target_ext = DEFAULT_EXT_FOR_FAMILY[family]
    tmpdir = tempfile.mkdtemp(prefix="office_repair_")
    try:
        input_path = os.path.join(tmpdir, f"input.{claimed_ext or 'bin'}")
        with open(input_path, 'wb') as f:
            f.write(data)

        # Níveis 2 e 3: reconstrução do contêiner ZIP + validação nativa.
        if container in ('ooxml', 'odf', 'zip-corrompido'):
            rebuilt_bytes = None
            is_intact = False
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    is_intact = zf.testzip() is None
            except zipfile.BadZipFile:
                is_intact = False

            if is_intact:
                rebuilt_bytes = data
            else:
                entries = tolerant_zip_extract(data)
                if entries:
                    entries = ensure_essential_parts(entries, family)
                    rebuilt_bytes = rebuild_zip_bytes(entries)
                    notes.append(
                        f"🔧 Contêiner ZIP reconstruído a partir de {len(entries)} "
                        "parte(s) legível(is) do arquivo original."
                    )

            if rebuilt_bytes:
                candidate_path = os.path.join(tmpdir, f"candidate.{target_ext}")
                with open(candidate_path, 'wb') as f:
                    f.write(rebuilt_bytes)
                result = try_native_open_and_resave(candidate_path, family, tmpdir, base_name)
                if result:
                    out_path, summary = result
                    notes.append(f"✅ Reparado com a biblioteca nativa. {summary}")
                    final_path = _downloads_output_path(os.path.basename(out_path))
                    shutil.copy(out_path, final_path)
                    return os.path.basename(final_path), notes

        # Nível 4: motor de importação do LibreOffice (mais tolerante).
        if soffice_available():
            try:
                lo_outdir = os.path.join(tmpdir, "lo_out")
                os.makedirs(lo_outdir, exist_ok=True)
                result = run_soffice(input_path, target_ext, lo_outdir, timeout=150)
                produced = _find_produced_file(lo_outdir, target_ext)
                if produced and os.path.getsize(produced) > 0:
                    notes.append(
                        "🔧 Recuperado pelo motor de importação do LibreOffice, que "
                        "tolera corrupções que as bibliotecas nativas rejeitam."
                    )
                    final_path = _downloads_output_path(f"{base_name}_reparado.{target_ext}")
                    shutil.copy(produced, final_path)
                    return os.path.basename(final_path), notes
            except OfficeError as e:
                notes.append(f"ℹ️ LibreOffice não conseguiu abrir o arquivo original: {e}")

        # Nível 5: recuperação bruta de texto.
        entries = tolerant_zip_extract(data)
        texts = extract_texts_from_parts(entries, family) if entries else []
        if not texts and container == 'ole2':
            texts = extract_ascii_text_runs(data)
        if not texts:
            texts = extract_ascii_text_runs(data)

        if texts:
            out_path = os.path.join(tmpdir, f"recovered.{target_ext}")
            rebuild_document_from_text(texts, family, out_path)
            notes.append(
                f"🧩 Recuperação bruta: {len(texts)} trecho(s) de texto extraído(s) e "
                f"remontado(s) em um novo arquivo {target_ext.upper()} "
                "(a formatação original não pôde ser preservada)."
            )
            final_path = _downloads_output_path(f"{base_name}_recuperado.{target_ext}")
            shutil.copy(out_path, final_path)
            return os.path.basename(final_path), notes

        raise OfficeError(
            "Arquivo danificado demais - nenhuma estratégia de recuperação funcionou.\n"
            + "\n".join(notes)
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
