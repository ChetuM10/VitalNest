"""Parse saved WHO fact-sheet pages (see docs/sources.md).

Only the article body of each fact sheet is read. Page furniture, tables and figures are dropped on
purpose (third-party figures and tables need separate permission), and so is the References list.
"""
import re
from html import unescape
from pathlib import Path

from vitalnest_ingest.cleaning import html_to_text
from vitalnest_ingest.models import Document
from vitalnest_ingest.pages import PATH_PREFIX, HOST, fact_sheet_url

SOURCE_NAME = "WHO"
LICENCE = (
    "CC BY-NC-SA 3.0 IGO. Adapted by VitalNest from a World Health Organization fact sheet; "
    "not endorsed by WHO."
)
# The label on a source card is built from the text after "from" (see frontend SourceCards).
ATTRIBUTION = "Adapted from the World Health Organization"
MIN_TEXT_CHARS = 400

_ARTICLE = re.compile(r'<article class="sf-detail-body-wrapper".*?</article>', re.S)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_CANONICAL = re.compile(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"')
_THIRD_PARTY = re.compile(r"<(table|figure)\b.*?</\1>", re.S | re.I)
_IMAGE = re.compile(r"<img\b[^>]*>", re.I)
# "References", "References:" on its own line, or a line that starts "References: ..." (WHO varies).
_REFERENCES_HEADING = re.compile(r"^references:?$|^references:\s", re.I)

# WHO topics by category (the categories were chosen by the project owner). Each name is the last part
# of https://www.who.int/news-room/fact-sheets/detail/<name>. A name that no longer exists is reported
# by `fetch-who` and skipped; it does not stop the run.
TOPICS: dict[str, list[str]] = {
    "Noncommunicable diseases": [
        "diabetes", "cancer", "cardiovascular-diseases-(cvds)", "noncommunicable-diseases", "hypertension",
        "stroke", "heart-attack", "chronic-obstructive-pulmonary-disease-(copd)", "asthma", "breast-cancer",
        "cervical-cancer", "colorectal-cancer", "lung-cancer", "kidney-disease", "dyslipidaemia",
        "rheumatic-heart-disease", "sickle-cell-disease", "cancer-in-children", "the-top-10-causes-of-death",
    ],
    "Mental health": [
        "depression", "anxiety-disorders", "suicide", "mental-disorders", "bipolar-disorder", "schizophrenia",
        "post-traumatic-stress-disorder", "autism-spectrum-disorders", "mental-health-at-work",
        "mental-health-of-older-adults", "adolescent-mental-health", "mental-health-in-emergencies",
    ],
    "Nutrition": [
        "malnutrition", "obesity-and-overweight", "healthy-diet", "anaemia", "infant-and-young-child-feeding",
        "sodium-reduction", "trans-fat", "food-safety", "sugars-and-dental-caries",
    ],
    "Infectious diseases": [
        "hiv-aids", "tuberculosis", "malaria", "hepatitis-a", "hepatitis-b", "hepatitis-c", "hepatitis-d",
        "hepatitis-e", "dengue-and-severe-dengue", "cholera", "typhoid", "pneumonia", "influenza-(seasonal)",
        "influenza-(avian-and-other-zoonotic)", "coronavirus-disease-(covid-19)",
        "post-covid-19-condition-(long-covid)", "meningitis", "diarrhoeal-disease", "rabies", "chikungunya",
        "zika-virus", "ebola-disease", "mpox", "antimicrobial-resistance", "sepsis", "yellow-fever",
        "west-nile-virus", "vector-borne-diseases", "respiratory-syncytial-virus-(rsv)", "hiv-drug-resistance",
        "lymphatic-filariasis", "schistosomiasis", "soil-transmitted-helminth-infections",
        "listeriosis", "salmonella-(non-typhoidal)", "e-coli", "campylobacter", "legionellosis", "botulism",
    ],
    "Maternal and child health": [
        "maternal-mortality", "pre-eclampsia", "preterm-birth", "newborn-mortality", "newborns-reducing-mortality",
        "adolescent-pregnancy", "birth-defects", "child-mortality-under-5-years", "children-reducing-mortality",
        "child-maltreatment", "infertility",
    ],
    "Neurological disorders": [
        "epilepsy", "dementia", "parkinson-disease", "multiple-sclerosis", "headache-disorders", "spinal-cord-injury",
    ],
    "Eye health": ["blindness-and-visual-impairment", "trachoma"],
    "Oral health": ["oral-health", "noma"],
    "Environmental health": [
        "ambient-(outdoor)-air-quality-and-health", "household-air-pollution-and-health", "drinking-water",
        "sanitation", "lead-poisoning-and-health", "mercury-and-health", "arsenic", "asbestos", "radon-and-health",
        "ultraviolet-radiation", "climate-change-and-health", "climate-change-heat-and-health",
        "wildfires-and-health", "ionizing-radiation-and-health-effects", "health-care-waste",
    ],
    "Women's health": [
        "menopause", "menstrual-health", "endometriosis", "polycystic-ovary-syndrome", "family-planning-contraception",
        "emergency-contraception", "oral-contraceptives", "intrauterine-devices", "violence-against-women",
        "female-genital-mutilation", "human-papilloma-virus-and-cancer", "bacterial-vaginosis",
    ],
    "Healthy ageing": [
        "ageing-and-health", "falls", "fragility-fractures", "osteoarthritis", "abuse-of-older-people",
        "palliative-care", "low-back-pain", "musculoskeletal-conditions", "rheumatoid-arthritis",
    ],
    "Substance use": ["tobacco", "alcohol", "opioid-overdose", "gambling"],
    "Injuries and road safety": [
        "injuries-and-violence", "road-traffic-injuries", "burns", "drowning", "snakebite-envenoming",
        "animal-bites", "youth-violence",
    ],
    "Immunization": ["immunization-coverage", "measles", "poliomyelitis", "rubella", "tetanus", "diphtheria"],
    "Disability and rehabilitation": ["disability-and-health", "rehabilitation", "assistive-technology"],
    "Skin health": [
        "scabies", "ringworm-(tinea)", "leprosy", "buruli-ulcer-(mycobacterium-ulcerans-infection)",
        "candidiasis-(yeast-infection)", "tungiasis", "yaws", "mycetoma", "shingles-(herpes-zoster)",
    ],
    "Sexual health": [
        "sexually-transmitted-infections-(stis)", "chlamydia", "gonorrhoea-(neisseria-gonorrhoeae-infection)",
        "syphilis", "trichomoniasis", "herpes-simplex-virus", "condoms", "comprehensive-sexuality-education",
        "multi-drug-resistant-gonorrhoea",
    ],
    "Adolescent health": [
        "adolescents-health-risks-and-solutions", "older-children-and-young-adolescent-mortality-(5-to-14-years)",
    ],
    "Hearing health": ["deafness-and-hearing-loss"],
    "Health emergencies": ["refugee-and-migrant-health", "refugee-and-migrant-mental-health"],
    "Health promotion": ["physical-activity", "self-care-health-interventions", "health-literacy"],
}


def all_slugs() -> list[str]:
    """Every listed fact sheet once, in category order."""
    seen: dict[str, None] = {}
    for slugs in TOPICS.values():
        for slug in slugs:
            seen.setdefault(slug)
    return list(seen)


def _body_text(article_html: str) -> str:
    article_html = _THIRD_PARTY.sub("", article_html)
    article_html = _IMAGE.sub("", article_html)
    lines = html_to_text(article_html).split("\n")
    # The References list is third-party citations, not content: cut from its heading onward.
    for index in range(len(lines) - 1, -1, -1):
        if _REFERENCES_HEADING.match(lines[index].strip()):
            lines = lines[:index]
            break
    return "\n".join(lines).strip()


def _canonical_url(html: str, slug: str) -> str:
    match = _CANONICAL.search(html)
    if match:
        candidate = unescape(match.group(1)).strip()
        if candidate.startswith(f"https://{HOST}{PATH_PREFIX}"):
            return candidate
    return fact_sheet_url(slug)


def parse_fact_sheet(html: str, slug: str, retrieved_at: str) -> Document | None:
    """One Document for a saved fact sheet, or None when the page has no usable article text."""
    article = _ARTICLE.search(html)
    title_match = _TITLE.search(html)
    if article is None or title_match is None:
        return None
    title = re.sub(r"\s+", " ", unescape(title_match.group(1))).strip()
    text = _body_text(article.group(0))
    if not title or len(text) < MIN_TEXT_CHARS:
        return None
    return Document(
        doc_id=f"who-{re.sub(r'[^a-z0-9]+', '-', slug.lower()).strip('-')}",
        source_name=SOURCE_NAME,
        title=title,
        url=_canonical_url(html, slug),
        text=text,
        retrieved_at=retrieved_at,
        licence=LICENCE,
        attribution=ATTRIBUTION,
    )


def load_documents(directory: Path, retrieved_at: str) -> tuple[list[Document], list[str]]:
    """Parse every saved page in `directory`. Returns (documents, names of pages that were unusable)."""
    documents: list[Document] = []
    skipped: list[str] = []
    for path in sorted(Path(directory).glob("*.html")):
        document = parse_fact_sheet(path.read_text(encoding="utf-8"), path.stem, retrieved_at)
        if document is None:
            skipped.append(path.stem)
        else:
            documents.append(document)
    return documents, skipped
