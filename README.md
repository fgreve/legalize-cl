# Legalize CL

### Legislación chilena consolidada en Markdown, versionada con Git.

Cada ley es un fichero. Cada reforma es un commit.

**17 normas** · **357 commits** · **Fuente: Biblioteca del Congreso Nacional**

Parte del proyecto [Legalize](https://github.com/legalize-dev) · Inspirado en [legalize-es](https://github.com/legalize-dev/legalize-es)

## Inicio rápido

```bash
# Clonar la legislación chilena
git clone https://github.com/legalize-dev/legalize-cl.git

# ¿Qué dice el artículo 1 de la Ley de Protección del Consumidor?
grep -A 5 "Artículo 1" cl/BCN-61438.md

# ¿Cuántas veces se ha reformado el Código Civil?
git log --oneline -- cl/BCN-172986.md

# Ver el diff exacto de una reforma
git show <commit> -- cl/BCN-172986.md

# Comparar dos versiones de una ley
git diff <commit1> <commit2> -- cl/BCN-1984.md
```

## Estructura

```
cl/                              ← todas las normas en carpeta plana
  BCN-172986.md                  — Código Civil
  BCN-1984.md                    — Código Penal
  BCN-207436.md                  — Código del Trabajo
  BCN-22740.md                   — Código de Procedimiento Civil
  BCN-176595.md                  — Código Procesal Penal
  BCN-5605.md                    — Código de Aguas
  BCN-61438.md                   — Ley 19.496 · Protección del Consumidor
  BCN-141599.md                  — Ley 19.628 · Datos Personales
  BCN-276363.md                  — Ley 20.285 · Acceso a Información Pública
  BCN-29472.md                   — Ley 18.045 · Mercado de Valores
  BCN-29473.md                   — Ley 18.046 · Sociedades Anónimas
  BCN-1058072.md                 — Ley 20.720 · Reorganización y Liquidación
  BCN-1008668.md                 — Ley 20.393 · Resp. Penal Personas Jurídicas
  BCN-1048718.md                 — Ley 20.659 · Simplificación Constitución Empresas
  BCN-1127890.md                 — Ley 21.131 · Pago a 30 Días
  BCN-258377.md                  — Ley 20.169 · Competencia Desleal
  BCN-29597.md                   — Ley 18.175 · Quiebras
```

El rango normativo (ley, código, decreto, DFL) va en el frontmatter YAML de cada fichero, no en la estructura de directorios.

## Formato

Cada fichero contiene:

- **Frontmatter YAML** — metadatos: título, identificador, país, rango, número, fecha de publicación, última actualización, estado, organismo, fuente
- **Cuerpo Markdown** — texto consolidado con estructura jerárquica (libros, títulos, capítulos, artículos)

```markdown
---
titulo: "Establece normas sobre protección de los derechos de los consumidores"
identificador: "BCN-61438"
pais: "cl"
rango: "ley"
numero: "19496"
fecha_publicacion: "1997-03-07"
ultima_actualizacion: "2021-04-20"
estado: "vigente"
organismo: "Ministerio de Economía, Fomento y Reconstrucción"
fuente: "https://www.bcn.cl/leychile/navegar?idNorma=61438"
---

# Ley 19.496

## Título I — Ámbito de aplicación y definiciones básicas

### Artículo 1

La presente ley tiene por objeto normar las relaciones entre
proveedores y consumidores...
```

## Commits

Los commits usan la fecha histórica de publicación o reforma en `GIT_AUTHOR_DATE` y `GIT_COMMITTER_DATE`. Cada commit incluye trailers con los metadatos de la norma:

```
[publicación] Ley 19.496 — Protección del Consumidor

Norma: BCN-61438
Fecha: 1997-03-07
Fuente: https://www.bcn.cl/leychile/navegar?idNorma=61438
```

```
[reforma] Modifica Ley 19.496 (2004-07-14)

Norma: BCN-61438
Disposición: Ley-19955
Fecha: 2004-07-14
Fuente: https://www.bcn.cl/leychile/navegar?idNorma=61438&idVersion=2004-07-14
```

Los commits están ordenados cronológicamente (todas las leyes mezcladas por fecha), lo que permite reconstruir el historial legislativo completo con `git log`.

## Notas

- La versión original (publicación) de la Ley 20.720 (BCN-1058072) no está disponible en la API de BCN (error 500 del servidor). El historial incluye las 4 reformas posteriores a partir de 2014-10-10.

## Fuente

Datos obtenidos de la API XML de la [Biblioteca del Congreso Nacional de Chile](https://www.bcn.cl/leychile/) (BCN), el servicio oficial de consulta de legislación chilena.

## Acerca de

Las leyes cambian constantemente. Cada año se publican decenas de reformas que modifican, derogan o agregan artículos a las normas vigentes. Sin embargo, no existe una herramienta pública que permita ver exactamente qué cambió entre una versión y otra de una ley.

Git resuelve este problema de forma natural: cada reforma es un commit con fecha real, y cualquier persona puede hacer `git diff` para ver qué artículos se modificaron, `git log` para ver el historial completo de una ley, o `git blame` para saber cuándo se modificó por última vez cada línea.

**Legalize CL** convierte la legislación chilena en un repositorio Git navegable, buscable y comparable.

## Licencia

Los textos legislativos son de dominio público. La estructuración y el formato están bajo licencia [MIT](LICENSE).

## Autor

**Fernando Greve** — [fernandogreve.com](https://www.fernandogreve.com/) · [GitHub](https://github.com/fgreve) · [LinkedIn](https://www.linkedin.com/in/fgreve/) · [fgreve@gmail.com](mailto:fgreve@gmail.com)

---

Inspirado en [legalize-es](https://github.com/legalize-dev/legalize-es) · Parte del proyecto [Legalize](https://github.com/legalize-dev)
