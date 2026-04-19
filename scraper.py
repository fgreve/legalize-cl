#!/usr/bin/env python3
"""
LeyChile Git Scraper
====================
Fetches Chilean laws from the BCN XML API, converts them to Markdown,
and creates a git repository where each reform appears as a dated commit.

Usage:
    python scraper.py --id-norma 61438              # Fetch by idNorma
    python scraper.py --id-ley 19496                # Fetch by ley number
    python scraper.py --id-norma 61438 --output-dir ./leyes-chile
"""

import argparse
import os
import re
import subprocess
import sys
import time
import html
from datetime import datetime
from pathlib import Path

import requests
import lxml.etree as ET

# ── Config ──────────────────────────────────────────────────────────────────

BASE_URL = "https://www.leychile.cl/Consulta/obtxml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
NS = {"n": "http://www.leychile.cl/esquemas"}
DELAY_BETWEEN_REQUESTS = 1.5  # Be polite to BCN servers


# ── XML Fetching ────────────────────────────────────────────────────────────

def fetch_xml(id_norma: int, id_version: str = None) -> ET._Element:
    """Fetch a law's XML from the LeyChile API."""
    params = {"opt": 7, "idNorma": id_norma}
    if id_version:
        params["idVersion"] = id_version
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    if len(resp.content) == 0:
        raise ValueError(f"Empty response for idNorma={id_norma}, idVersion={id_version}")
    return ET.fromstring(resp.content)


def fetch_xml_by_ley(id_ley: int) -> ET._Element:
    """Fetch by ley number (uses idLey param)."""
    params = {"opt": 7, "idLey": id_ley}
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def get_version_dates(root: ET._Element) -> list[str]:
    """Extract all unique fechaVersion values from the XML, sorted chronologically."""
    dates = set()
    for elem in root.iter():
        fv = elem.get("fechaVersion")
        if fv:
            dates.add(fv)
    return sorted(dates)


def get_norma_metadata(root: ET._Element) -> dict:
    """Extract law metadata from the XML root."""
    meta = {}
    meta["id_norma"] = root.get("normaId", "")
    meta["derogado"] = root.get("derogado", "")

    ident = root.find("n:Identificador", NS)
    if ident is not None:
        meta["fecha_promulgacion"] = ident.get("fechaPromulgacion", "")
        meta["fecha_publicacion"] = ident.get("fechaPublicacion", "")
        tipo_num = ident.find(".//n:TipoNumero", NS)
        if tipo_num is not None:
            tipo = tipo_num.findtext("n:Tipo", "", NS)
            numero = tipo_num.findtext("n:Numero", "", NS)
            meta["tipo"] = tipo
            meta["numero"] = numero
            meta["nombre_archivo"] = f"{tipo.lower()}-{numero}"
        organismos = ident.findall(".//n:Organismo", NS)
        meta["organismos"] = [o.text for o in organismos if o.text]

    meta_node = root.find("n:Metadatos", NS)
    if meta_node is not None:
        meta["titulo"] = meta_node.findtext("n:TituloNorma", "", NS)
        materias = meta_node.findall(".//n:Materia", NS)
        meta["materias"] = [m.text.strip() for m in materias if m.text]

    return meta


# ── XML to Markdown Conversion ─────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Clean up raw text from XML."""
    if not text:
        return ""
    text = html.unescape(text)
    # Normalize whitespace but preserve line breaks
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned.append(line)
    # Remove excessive blank lines
    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def estructura_to_md(elem: ET._Element, depth: int = 2) -> str:
    """Recursively convert an EstructuraFuncional element to Markdown."""
    parts = []
    tipo_parte = elem.get("tipoParte", "")
    derogado = elem.get("derogado", "")
    fecha_version = elem.get("fechaVersion", "")
    art_label = ""

    # Get the title/heading for this structural element
    meta = elem.find("n:Metadatos", NS)
    titulo = ""
    numero = ""
    if meta is not None:
        titulo_elem = meta.find("n:TituloParte", NS)
        if titulo_elem is not None and titulo_elem.text:
            titulo = clean_text(titulo_elem.text)
        nombre_elem = meta.find("n:NombreParte", NS)
        if nombre_elem is not None and nombre_elem.text:
            nombre = clean_text(nombre_elem.text)
            if nombre and nombre != "\xa0":
                titulo = nombre if not titulo else titulo
        numero_elem = meta.find("n:NumeroParte", NS)
        if numero_elem is not None and numero_elem.text:
            numero = numero_elem.text.strip()

    # Build heading
    heading_text = ""
    if tipo_parte in ("Libro", "Título", "Capítulo", "Párrafo"):
        heading_text = titulo if titulo else f"{tipo_parte} {numero}".strip()
        md_depth = min(depth, 6)
        parts.append(f"\n{'#' * md_depth} {heading_text}\n")
        # Flag to skip duplicate text in Texto element
        skip_texto = True
    elif tipo_parte == "Artículo":
        # Article number is in NombreParte (e.g., "1", "2 BIS", "3 TER")
        nombre_parte = ""
        if meta is not None:
            np_elem = meta.find("n:NombreParte", NS)
            if np_elem is not None and np_elem.text and np_elem.text.strip() != "\xa0":
                nombre_parte = np_elem.text.strip()
        art_num = nombre_parte or numero or ""
        art_label = f"Artículo {art_num}" if art_num else "Artículo"
        md_depth = min(depth, 6)
        parts.append(f"\n{'#' * md_depth} {art_label}\n")

    # Derogation notice
    if derogado == "derogado":
        parts.append(f"\n*[Derogado]*\n")

    # Main text
    texto_elem = elem.find("n:Texto", NS)
    if texto_elem is not None and tipo_parte not in ("Libro", "Título", "Capítulo", "Párrafo"):
        raw = texto_elem.text or ""
        # Also get tail text and child elements (mixed content)
        for child in texto_elem:
            if child.tag.endswith("}Imagen") or child.tag == "Imagen":
                raw += "\n[Imagen]\n"
            if child.tail:
                raw += child.tail
        text = clean_text(raw)
        if text:
            # Strip duplicate heading/article labels from beginning of text
            for prefix in [heading_text, art_label]:
                if prefix:
                    # Case-insensitive prefix removal
                    stripped = text
                    # Remove "Artículo Nº.-" style prefixes
                    stripped = re.sub(
                        r"^Artículo\s+\d+[\s°º]*(?:bis|ter|quáter|quinquies|sexies)?\.?\s*-?\s*",
                        "", stripped, flags=re.IGNORECASE
                    )
                    if stripped != text:
                        text = stripped.strip()
                        break
            parts.append(f"\n{text}\n")

    # Recurse into child structures
    hijas = elem.find("n:EstructurasFuncionales", NS)
    if hijas is not None:
        for child_ef in hijas.findall("n:EstructuraFuncional", NS):
            next_depth = depth + 1 if tipo_parte in ("Libro", "Título", "Capítulo") else depth
            parts.append(estructura_to_md(child_ef, next_depth))

    return "\n".join(parts)


def xml_to_markdown(root: ET._Element) -> str:
    """Convert the full XML law to a Markdown document."""
    meta = get_norma_metadata(root)
    parts = []

    # YAML frontmatter
    id_norma = meta.get('id_norma', '')
    tipo = meta.get('tipo', '')
    numero = meta.get('numero', '')
    fecha_pub = meta.get('fecha_publicacion', '')
    fecha_version = root.get('fechaVersion', fecha_pub)
    derogado = meta.get('derogado', '')
    estado = 'derogado' if derogado == 'derogado' else 'vigente'
    organismo = meta['organismos'][0] if meta.get('organismos') else ''

    parts.append("---")
    parts.append(f'titulo: "{meta.get("titulo", "")}"')
    parts.append(f'identificador: "BCN-{id_norma}"')
    parts.append(f'pais: "cl"')
    parts.append(f'rango: "{tipo.lower()}"')
    parts.append(f'numero: "{numero}"')
    parts.append(f'fecha_publicacion: "{fecha_pub}"')
    parts.append(f'ultima_actualizacion: "{fecha_version}"')
    parts.append(f'estado: "{estado}"')
    parts.append(f'organismo: "{organismo}"')
    parts.append(f'fuente: "https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"')
    parts.append("---")
    parts.append("")

    # Title
    parts.append(f"# {meta.get('tipo', '')} {meta.get('numero', '')}")
    parts.append("")

    # Encabezado (preamble)
    encabezado = root.find("n:Encabezado", NS)
    if encabezado is not None:
        texto = encabezado.find("n:Texto", NS)
        if texto is not None and texto.text:
            text = clean_text(texto.text)
            parts.append(text)
            parts.append("")

    # Main body (EstructurasFuncionales)
    ef_root = root.find("n:EstructurasFuncionales", NS)
    if ef_root is not None:
        for ef in ef_root.findall("n:EstructuraFuncional", NS):
            parts.append(estructura_to_md(ef, depth=2))

    # Promulgación
    prom = root.find("n:Promulgacion", NS)
    if prom is not None:
        texto = prom.find("n:Texto", NS)
        if texto is not None and texto.text:
            text = clean_text(texto.text)
            parts.append(f"\n---\n\n{text}\n")

    # Clean up
    result = "\n".join(parts)
    result = re.sub(r"\n{4,}", "\n\n\n", result)
    return result


# ── Git Operations ──────────────────────────────────────────────────────────

def git_init(repo_dir: Path):
    """Initialize a git repository."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "bot@legalize.cl"],
        cwd=repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Legalize CL"],
        cwd=repo_dir, check=True, capture_output=True
    )


def _git_run(args, cwd, retries=5, **kwargs):
    """Run a git command with retries for Windows file locking issues."""
    for attempt in range(retries):
        result = subprocess.run(args, cwd=cwd, capture_output=True, **kwargs)
        if result.returncode == 0:
            return result
        if attempt < retries - 1:
            time.sleep(1)
    # Show stderr for debugging
    stderr = result.stderr.decode('utf-8', errors='replace') if isinstance(result.stderr, bytes) else (result.stderr or '')
    print(f"  ⚠ git error after {retries} retries: {stderr.strip()}")
    result.check_returncode()
    return result


def git_commit(repo_dir: Path, message: str, date: str, files: list[str] = None):
    """Create a git commit with a specific date."""
    if files:
        for f in files:
            _git_run(["git", "add", f], cwd=repo_dir)
    else:
        _git_run(["git", "add", "-A"], cwd=repo_dir)

    # Check if there are changes to commit
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_dir, capture_output=True
    )
    if result.returncode == 0:
        print(f"  ⏭ No changes for {date}, skipping commit")
        return False

    # Git on Windows doesn't support dates before 1970
    if date < "1970-01-01":
        iso_date = "1970-01-02T00:00:00+0000"
    else:
        iso_date = f"{date}T12:00:00+0000"
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": iso_date,
        "GIT_COMMITTER_DATE": iso_date,
    }
    # Write message to temp file to avoid shell escaping issues on Windows
    msg_file = repo_dir / ".commitmsg"
    msg_file.write_text(message, encoding="utf-8")
    try:
        _git_run(["git", "commit", "-F", str(msg_file.resolve())],
                 cwd=repo_dir, env=env)
    finally:
        msg_file.unlink(missing_ok=True)
    print(f"  ✓ Commit: {date} — {message[:70]}")
    return True


# ── Main Pipeline ───────────────────────────────────────────────────────────

def get_filepath(id_norma: int) -> str:
    """Return the repo-relative path for a law file."""
    return f"cl/BCN-{id_norma}.md"


def scrape_law(id_norma: int = None, id_ley: int = None, output_dir: str = "./leyes-chile"):
    """Main pipeline: fetch all versions, convert to MD, create git commits."""

    repo_dir = Path(output_dir)

    # Step 1: Fetch current (latest) version to get metadata & version dates
    print("🔍 Fetching latest version...")
    if id_ley:
        root = fetch_xml_by_ley(id_ley)
        id_norma = int(root.get("normaId"))
        print(f"  idNorma resolved: {id_norma}")
    else:
        root = fetch_xml(id_norma)

    meta = get_norma_metadata(root)
    version_dates = get_version_dates(root)
    filepath = get_filepath(id_norma)

    print(f"  📜 {meta.get('tipo', '')} {meta.get('numero', '')}: {meta.get('titulo', '')}")
    print(f"  📁 → {filepath}")
    print(f"  📅 {len(version_dates)} versiones: {', '.join(version_dates)}")

    # Step 2: Init git repo
    git_init(repo_dir)
    (repo_dir / "cl").mkdir(parents=True, exist_ok=True)

    # Step 3: Fetch each version, convert, and commit
    print(f"\n📥 Descargando {len(version_dates)} versiones...")
    for i, date in enumerate(version_dates):
        print(f"\n  [{i+1}/{len(version_dates)}] Versión {date}...")

        try:
            versioned_root = fetch_xml(id_norma, id_version=date)
        except Exception as e:
            print(f"  ⚠ Error fetching version {date}: {e}")
            continue

        # Convert to markdown
        md = xml_to_markdown(versioned_root)

        # Determine which articles changed (for commit message)
        versioned_meta = get_norma_metadata(versioned_root)

        # Write file
        full_path = repo_dir / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(md, encoding="utf-8")

        # Build commit message with trailers
        tipo = meta.get('tipo', '')
        numero = meta.get('numero', '')
        titulo_corto = meta.get('titulo', '')[:80].replace('"', "'")
        fuente = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"
        if date != version_dates[0]:
            fuente += f"&idVersion={date}"

        if i == 0:
            subject = f"[publicación] {tipo} {numero} — {titulo_corto}"
        else:
            subject = f"[reforma] Modifica {tipo} {numero} ({date})"

        trailers = f"\nNorma: BCN-{id_norma}\nFecha: {date}\nFuente: {fuente}"
        msg = f"{subject}\n{trailers}"

        git_commit(repo_dir, msg, date, [filepath])

        if i < len(version_dates) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # Final summary
    print(f"\n✅ Repositorio creado en: {repo_dir}")
    print(f"   {len(version_dates)} commits con versiones históricas")
    print(f"\n   Comandos útiles:")
    print(f"   git -C {repo_dir} log --oneline")
    print(f"   git -C {repo_dir} log --oneline --follow {filepath}")
    print(f"   git -C {repo_dir} diff HEAD~1 -- {filepath}")


def scrape_multiple(norma_ids: list[int], output_dir: str = "./leyes-chile"):
    """Scrape multiple laws into the same repository."""
    for nid in norma_ids:
        try:
            scrape_law(id_norma=nid, output_dir=output_dir)
        except Exception as e:
            print(f"\n❌ Error processing idNorma={nid}: {e}")
            continue


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Chilean laws from LeyChile and create a git repository"
    )
    parser.add_argument("--id-norma", type=int, help="BCN norma ID (e.g., 61438)")
    parser.add_argument("--id-ley", type=int, help="Law number (e.g., 19496)")
    parser.add_argument("--output-dir", default="./leyes-chile", help="Output git repo dir")
    parser.add_argument(
        "--batch", type=str,
        help="Comma-separated list of idNorma values for batch processing"
    )
    args = parser.parse_args()

    if args.batch:
        ids = [int(x.strip()) for x in args.batch.split(",")]
        scrape_multiple(ids, args.output_dir)
    elif args.id_norma:
        scrape_law(id_norma=args.id_norma, output_dir=args.output_dir)
    elif args.id_ley:
        scrape_law(id_ley=args.id_ley, output_dir=args.output_dir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
