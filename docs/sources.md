# VitalNest — Healthcare source terms review

Reviewed 2026-10-31, before any ingestion (plan risk 4 and decision D5). This is a practical engineering review from the sources' public pages, **not legal advice**. Some search results were archived copies, so re-check each source's live terms page before relying on it or going beyond a non-commercial prototype.

Rule from the plan: public access does not mean free reuse. A source whose terms do not allow our use is **dropped** (D5), not summarised.

## Summary

| Source | Status for ingestion | Access method | Licence / terms | Needs from you |
|---|---|---|---|---|
| **MedlinePlus** | ✅ **Approved** (health topic summaries only) | Official Health Topics XML download | U.S. government work, not copyrighted | Nothing |
| **CDC** | ✅ **Approved 2026-11-05** (reviewed page list, copyright pages skipped) | Individual cdc.gov pages, fetched politely and cached (`fetch-cdc`) | Mostly public domain; third-party items and logo excluded | Nothing |
| **NHS** | ⏳ Pending your action | NHS website content API (registration needed) | Standard NHS terms / Open Government Licence, with exclusions and separate syndication terms | Register for API access and read the syndication terms |
| **WHO** | ✅ **Approved 2026-11-05** (fact sheets from a reviewed list) | Fact-sheet pages, fetched politely and cached (`fetch-who`) | CC BY-NC-SA 3.0 IGO (non-commercial, attribution, share-alike) | Nothing |

MedlinePlus (T3), WHO and CDC (2026-11-05) are built locally. NHS still needs the owner's API registration.

## MedlinePlus (National Library of Medicine)

- **Terms:** federal government works are not copyrighted. This covers health topic summaries, in English and Spanish. Source: <https://medlineplus.gov/about/using/usingcontent/>
- **Excluded (copyrighted):** A.D.A.M. Medical Encyclopedia content, ASHP drug monographs, and most images. The ingestion reads **only** the `full-summary` of each English health topic, so none of these are included.
- **Not ingested:** `<site>` records (links to external organisations' pages). Those pages belong to other owners.
- **Attribution:** credit MedlinePlus, for example "Courtesy of MedlinePlus from the National Library of Medicine". Every chunk stores this text and the UI shows it with each citation.
- **Do not:** imply NLM endorsement, or present pages as if hosted under another domain.
- **Access:** the official XML file `https://medlineplus.gov/xml/mplus_topics_YYYY-MM-DD.xml`, generated Tuesday to Saturday. Source: <https://medlineplus.gov/xml.html>. The ingestion script looks back up to 7 days for the newest file and downloads it once; it does not crawl the website.
- **Structure used:** `health-topics` → `health-topic` (attributes `id`, `title`, `url`, `language`, `meta-desc`) with children `also-called` and `full-summary`. Reference: <https://medlineplus.gov/xmldescription.html>
- **Open point:** the reference page does not say whether `full-summary` is escaped HTML or raw markup. The parser accepts both.

## CDC

- **Terms found:** most CDC web content is public domain, but a government site can mix in copyright-protected material, which should carry its own copyright statement. CDC asks for credit as the source. The CDC logo is trademarked and must not be used. Public Health Image Library items have separate terms. Source: <https://www.cdc.gov/other/agencymaterials.html>
- **Syndication:** CDC's syndication conditions require that wording is not changed or distorted and links back to CDC stay intact (tools.cdc.gov). I found no current published API terms.
- **Concern:** RAG chunks are used as context for an AI-written answer, not displayed unchanged. Whether that counts as "altered" syndication is unclear.
- **Owner decision (2026-11-05):** approved the proposed approach: a reviewed set of CDC pages, skipping any page with a copyright notice, with the source URL and a CDC attribution on every chunk.
- **How the list was made:** from CDC's own sitemaps (`wcms-auto-sitemap-index.xml`), keeping patient-facing pages (about, symptoms, risk factors, prevention, treatment, testing...) for about 135 topic sections that follow the owner's WHO categories. Provider (hcp), public-health-program (php), Spanish, data and training pages are left out. The list is `ingestion/cdc_pages.txt`.
- **Copyright rule, enforced at build time:** a page whose main content contains a copyright sign, the word "copyright", or "used/reprinted with permission" is skipped and reported. Tables, figures, images, video and page furniture are dropped.
- **Politeness:** robots.txt is read and checked for every page and redirect, only `https://www.cdc.gov/<path>.html` is accepted, 2 seconds between requests, and pages are cached.
- **Syndication concern (unchanged):** chunks are verbatim extracts used as context for an AI-written answer; CDC's syndication wording says content must not be altered. Every answer shows the original CDC link.
- **Result of the first run:** 416 of 439 listed pages downloaded (the rest were retired pages, 404s or redirects to non-.html addresses, all refused or reported safely). Four pages were skipped at build time (three for a copyright/permission notice, one with too little text), giving 412 CDC pages.
- **Known limits:** eight sections matched nothing (nutrition, physical-activity, healthyweight, std, breastfeeding, e-cigarettes, handhygiene, health-literacy); a few chunks still contain tab labels such as "For Everyone".

## NHS (nhs.uk)

- **Terms found:** most nhs.uk content can be reused under its standard terms and conditions, and is available under the Open Government Licence, with exceptions. Some images, videos and other NHS sites (One You, Smokefree, Quit Now) are excluded. The API and widgets have separate syndication terms covering refresh rates. Sources: <https://www.nhs.uk/our-policies/terms-and-conditions/> and <https://www.nhs.uk/our-policies/terms-and-conditions/content-not-licensed-for-re-use/>
- **Not verified:** the current API registration process and whether storing content in a vector database fits the syndication terms.
- **Needed from you:** register for the NHS website content API, read the syndication terms, and tell me what the key and terms allow. I will not scrape nhs.uk pages around the API.

## WHO

- **Terms found:** WHO publications issued after 11 November 2016 are under CC BY-NC-SA 3.0 IGO. Reuse is allowed for **non-commercial** purposes with citation, and adaptations must use the same or an equivalent licence. Commercial use needs WHO's permission. Third-party images, tables and figures usually need separate permission, and older material is not covered by the licence. Source: <https://www.who.int/about/who-we-are/publishing-policies/copyright>
- **Impact:** fine for a non-commercial prototype with attribution. It would block any later commercial use. Chunks stay private in the vector database but are adaptations, so the share-alike condition applies if the dataset were ever shared.
- **Owner decisions (2026-11-05):** VitalNest is non-commercial; share-alike on adapted text is accepted; topics follow the owner's 21 categories (`vitalnest_ingest/who.py`, `TOPICS`).
- **What is ingested:** the article body of each listed fact sheet at `https://www.who.int/news-room/fact-sheets/detail/<name>`. Tables, figures, images and the References list are dropped (third-party material needs separate permission). Abortion, health-system and policy sheets are not on the list.
- **Politeness:** WHO's robots.txt is read and obeyed, the fetcher only accepts that URL path on `www.who.int` (also across redirects), waits 2 seconds between requests, and caches pages so repeat runs do not hit the site.
- **Attribution and licence on every chunk:** "Adapted from the World Health Organization" and "CC BY-NC-SA 3.0 IGO. Adapted by VitalNest from a World Health Organization fact sheet; not endorsed by WHO." The original link is shown with every citation.
- **Limits:** no WHO page on first aid or occupational health exists as a fact sheet, so those categories are covered only by related sheets (mental health at work, ionizing radiation, e-waste, and so on).

## Chunk metadata recorded for every source

`source_name`, `title`, `url`, `retrieved_at`, `licence`, `attribution`, plus `doc_id` and `chunk_id`. The UI reads `source_name`, `title`, `url` and `attribution` for citations.

## Ingestion etiquette (all sources)

- A descriptive `User-Agent` on every request.
- No crawling of site pages for MedlinePlus: one file download.
- For any page-based source added later: respect `robots.txt`, rate-limit requests, and cache raw downloads locally so repeat runs do not hit the site.
